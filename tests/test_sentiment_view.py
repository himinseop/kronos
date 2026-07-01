from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kronos.dashboard import sentiment_view as sv
from kronos.storage.db import transaction
from kronos.storage.models import NewsArticle
from kronos.storage.repository import insert_news

MODEL = "kr-finbert-sc"


def _seed(conn):
    now = datetime.now(UTC)
    with transaction(conn):
        conn.execute(
            "INSERT INTO tickers (ticker, corp_code, corp_name) VALUES ('005930','x','삼성전자')"
        )
        insert_news(
            conn,
            [
                NewsArticle(
                    source="naver", title="삼성전자 호실적", published_at=now, ticker="005930"
                ),
                NewsArticle(
                    source="naver", title="삼성전자 신제품", published_at=now, ticker="005930"
                ),
                NewsArticle(source="rss", title="시장 소식", published_at=now - timedelta(days=1)),
            ],
        )
        # 뉴스 id 조회 후 감성 삽입
        ids = [r["id"] for r in conn.execute("SELECT id FROM news ORDER BY id").fetchall()]
        rows = [
            (str(ids[0]), MODEL, 0.9, "positive", 0.95),
            (str(ids[1]), MODEL, 0.1, "neutral", 0.6),
            (str(ids[2]), MODEL, -0.8, "negative", 0.9),
        ]
        with conn.cursor() as cur:
            cur.executemany(
                """INSERT INTO sentiments
                   (target_type, target_id, model, score, label, confidence)
                   VALUES ('news', %s, %s, %s, %s, %s)""",
                rows,
            )
    return conn


def test_coverage(db_conn):
    cov = sv.coverage(_seed(db_conn))
    assert cov["news_total"] == 3
    assert cov["scored"] == 3
    assert cov["pending"] == 0
    assert cov["coverage"] == 1.0


def test_label_distribution(db_conn):
    dist = sv.label_distribution(_seed(db_conn), days=7)
    counts = {r.label: r.n for r in dist.itertuples()}
    assert counts.get("positive") == 1
    assert counts.get("neutral") == 1
    assert counts.get("negative") == 1


def test_daily_trend_and_ticker_filter(db_conn):
    conn = _seed(db_conn)
    allt = sv.daily_sentiment_trend(conn, days=30)
    assert not allt.empty
    only = sv.daily_sentiment_trend(conn, ticker="005930", days=30)
    # 삼성전자 뉴스 2건만 → 평균 (0.9+0.1)/2 = 0.5
    assert round(float(only["avg_score"].iloc[0]), 2) == 0.5


def test_recent_scored_feed_label_filter(db_conn):
    pos = sv.recent_scored_feed(_seed(db_conn), label="positive")
    assert len(pos) == 1
    assert pos["ticker"].iloc[0] == "005930"
