from __future__ import annotations

from datetime import UTC, datetime

from kronos.analysis.classify import (
    ClassificationResult,
    build_batch_user_prompt,
    model_id_for,
    normalize_category,
    parse_batch_response,
    parse_response,
)
from kronos.analysis.classify_run import (
    classify_news,
    pending_classify_count,
)
from kronos.storage.db import transaction
from kronos.storage.models import NewsArticle
from kronos.storage.repository import insert_news

MODEL = "test-model"


# ---- 순수 로직 ----


def test_normalize_category_exact_and_partial():
    assert normalize_category("earnings") == "earnings"
    assert normalize_category("category: contract") == "contract"
    assert normalize_category("MA") == "ma"  # 대소문자


def test_normalize_category_korean_fallback():
    assert normalize_category("실적 발표") == "earnings"
    assert normalize_category("유상증자") == "financing"
    assert normalize_category("규제") == "regulation"


def test_normalize_category_unknown_is_other():
    assert normalize_category("무언가이상한값") == "other"
    assert normalize_category("") == "other"
    assert normalize_category(None) == "other"


def test_parse_response_valid_json():
    r = parse_response('{"category": "earnings", "confidence": 0.9, "rationale": "실적"}')
    assert r.category == "earnings"
    assert r.confidence == 0.9
    assert r.rationale == "실적"


def test_parse_response_json_embedded_in_text():
    r = parse_response('설명... {"category":"ma","confidence":0.7,"rationale":"인수"} 끝')
    assert r.category == "ma"
    assert r.confidence == 0.7


def test_parse_response_confidence_clamped():
    r = parse_response('{"category":"earnings","confidence":5,"rationale":"x"}')
    assert r.confidence == 1.0


def test_parse_response_fallback_on_garbage():
    r = parse_response("실적 관련 뉴스입니다")  # JSON 아님
    assert r.category == "earnings"  # 한국어 폴백
    assert r.confidence == 0.0


def test_parse_batch_response_ordered():
    text = (
        '{"results": ['
        '{"i": 1, "category": "earnings", "confidence": 0.9, "rationale": "a"},'
        '{"i": 2, "category": "contract", "confidence": 0.8, "rationale": "b"}'
        "]}"
    )
    out = parse_batch_response(text, 2)
    assert out is not None
    assert [r.category for r in out] == ["earnings", "contract"]


def test_parse_batch_response_reorders_by_index():
    # 순서가 뒤섞여 와도 i 기준으로 정렬
    text = (
        '{"results": ['
        '{"i": 2, "category": "contract", "confidence": 0.8, "rationale": "b"},'
        '{"i": 1, "category": "earnings", "confidence": 0.9, "rationale": "a"}'
        "]}"
    )
    out = parse_batch_response(text, 2)
    assert out is not None
    assert [r.category for r in out] == ["earnings", "contract"]


def test_parse_batch_response_length_mismatch_returns_none():
    text = '{"results": [{"i":1,"category":"earnings","confidence":0.9,"rationale":"a"}]}'
    assert parse_batch_response(text, 3) is None  # 3개 기대했는데 1개


def test_parse_batch_response_garbage_returns_none():
    assert parse_batch_response("not json", 2) is None


def test_build_batch_user_prompt_numbers_titles():
    p = build_batch_user_prompt(["제목A", "제목B"])
    assert "1. 제목A" in p
    assert "2. 제목B" in p


def test_model_id_for():
    assert model_id_for("qwen2.5:3b-instruct") == "cat:qwen2.5:3b-instruct"


# ---- 워커 (DB) ----


class FakeClassifier:
    """'계약'→contract, '실적'→earnings, 그 외 other."""

    def classify(self, titles: list[str]) -> list[ClassificationResult]:
        out = []
        for t in titles:
            if "계약" in t or "수주" in t:
                out.append(ClassificationResult("contract", 0.9, "수주"))
            elif "실적" in t or "영업이익" in t:
                out.append(ClassificationResult("earnings", 0.95, "실적"))
            else:
                out.append(ClassificationResult("other", 0.5, ""))
        return out


def _seed(conn):
    now = datetime(2026, 7, 1, 9, 0, tzinfo=UTC)
    with transaction(conn):
        insert_news(
            conn,
            [
                # 종목 매칭됨 → 분류 대상
                NewsArticle(
                    source="naver",
                    title="삼성전자 대규모 수주 계약",
                    published_at=now,
                    ticker="005930",
                ),
                NewsArticle(
                    source="naver",
                    title="SK 3분기 영업이익 급증",
                    published_at=now,
                    ticker="000660",
                ),
                # 종목 미매칭 → 분류 제외
                NewsArticle(source="rss", title="일반 시장 뉴스", published_at=now, ticker=None),
            ],
        )


def test_classify_only_ticker_matched(db_conn, test_dsn):
    _seed(db_conn)
    assert pending_classify_count(model_name=MODEL, dsn=test_dsn) == 2  # 미매칭 제외

    stats = classify_news(FakeClassifier(), model_name=MODEL, limit=100, chunk_size=5, dsn=test_dsn)
    assert stats.scanned == 2
    assert stats.classified == 2
    assert pending_classify_count(model_name=MODEL, dsn=test_dsn) == 0

    rows = db_conn.execute(
        "SELECT category, COUNT(*) AS n FROM sentiments WHERE model=%s GROUP BY category ORDER BY category",
        (model_id_for(MODEL),),
    ).fetchall()
    counts = {r["category"]: r["n"] for r in rows}
    assert counts == {"contract": 1, "earnings": 1}


def test_classify_is_idempotent(db_conn, test_dsn):
    _seed(db_conn)
    classify_news(FakeClassifier(), model_name=MODEL, limit=100, dsn=test_dsn)
    stats2 = classify_news(FakeClassifier(), model_name=MODEL, limit=100, dsn=test_dsn)
    assert stats2.scanned == 0
    assert stats2.classified == 0
    total = db_conn.execute(
        "SELECT COUNT(*) AS n FROM sentiments WHERE model=%s", (model_id_for(MODEL),)
    ).fetchone()["n"]
    assert total == 2


def test_classify_coexists_with_sentiment(db_conn, test_dsn):
    """같은 뉴스에 감성(kr-finbert)과 카테고리(cat:) 행이 공존."""
    _seed(db_conn)
    # 감성 행 하나 수동 삽입
    nid = db_conn.execute("SELECT id FROM news WHERE ticker='005930'").fetchone()["id"]
    db_conn.execute(
        """INSERT INTO sentiments (target_type, target_id, model, score, label, confidence)
           VALUES ('news', %s, 'kr-finbert-sc', 0.5, 'positive', 0.8)""",
        (str(nid),),
    )
    classify_news(FakeClassifier(), model_name=MODEL, limit=100, dsn=test_dsn)
    rows = db_conn.execute(
        "SELECT model, category FROM sentiments WHERE target_id=%s ORDER BY model", (str(nid),)
    ).fetchall()
    models = {r["model"] for r in rows}
    assert models == {"kr-finbert-sc", model_id_for(MODEL)}
