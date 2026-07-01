from __future__ import annotations

from datetime import UTC, datetime

from kronos.analysis.run import analyze_news_sentiment, pending_count
from kronos.analysis.sentiment import (
    SentimentResult,
    normalize_label,
    result_from_probs,
)
from kronos.storage.db import connect, transaction
from kronos.storage.models import NewsArticle
from kronos.storage.repository import insert_news
from kronos.storage.schema import ensure_schema


def test_normalize_label_variants():
    assert normalize_label("positive") == "positive"
    assert normalize_label("LABEL_positive") == "positive"
    assert normalize_label("긍정") == "positive"
    assert normalize_label("negative") == "negative"
    assert normalize_label("부정") == "negative"
    assert normalize_label("neutral") == "neutral"
    assert normalize_label("중립") == "neutral"
    assert normalize_label("something") == "neutral"


def test_result_from_probs_positive():
    r = result_from_probs(["negative", "neutral", "positive"], [0.1, 0.2, 0.7])
    assert r.label == "positive"
    assert r.score == round(0.7 - 0.1, 4)
    assert r.confidence == 0.7


def test_result_from_probs_negative():
    r = result_from_probs(["negative", "neutral", "positive"], [0.8, 0.15, 0.05])
    assert r.label == "negative"
    assert r.score == round(0.05 - 0.8, 4)
    assert r.confidence == 0.8


class FakeModel:
    """제목에 '호실적'이 있으면 positive, '손실'이면 negative, 아니면 neutral."""

    def predict(self, texts: list[str]) -> list[SentimentResult]:
        out = []
        for t in texts:
            if "호실적" in t:
                out.append(SentimentResult("positive", 0.9, 0.95))
            elif "손실" in t:
                out.append(SentimentResult("negative", -0.8, 0.9))
            else:
                out.append(SentimentResult("neutral", 0.0, 0.6))
        return out


def _seed_news(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema(conn)
    now = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    with transaction(conn):
        insert_news(
            conn,
            [
                NewsArticle(source="naver", title="삼성전자 호실적 발표", published_at=now),
                NewsArticle(source="naver", title="LG 대규모 손실 기록", published_at=now),
                NewsArticle(source="rss", title="일반적인 시장 소식", published_at=now),
            ],
        )
    conn.close()
    return tmp_path / "test.db"


def test_analyze_news_sentiment_scores_all(tmp_path):
    db = _seed_news(tmp_path)
    assert pending_count(db) == 3

    stats = analyze_news_sentiment(db, FakeModel(), limit=100, batch_size=2)
    assert stats.scanned == 3
    assert stats.scored == 3
    assert pending_count(db) == 0

    conn = connect(db)
    rows = conn.execute(
        "SELECT label, COUNT(*) FROM sentiments GROUP BY label ORDER BY label"
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    assert counts == {"negative": 1, "neutral": 1, "positive": 1}


def test_analyze_is_idempotent(tmp_path):
    db = _seed_news(tmp_path)
    analyze_news_sentiment(db, FakeModel(), limit=100)
    # 두 번째 실행: 이미 다 분석됨 → 신규 0
    stats2 = analyze_news_sentiment(db, FakeModel(), limit=100)
    assert stats2.scanned == 0
    assert stats2.scored == 0

    conn = connect(db)
    total = conn.execute("SELECT COUNT(*) FROM sentiments").fetchone()[0]
    assert total == 3  # 중복 적재 없음


def test_analyze_respects_limit(tmp_path):
    db = _seed_news(tmp_path)
    stats = analyze_news_sentiment(db, FakeModel(), limit=2)
    assert stats.scanned == 2
    assert stats.scored == 2
    assert pending_count(db) == 1
