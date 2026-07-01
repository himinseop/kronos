from __future__ import annotations

from datetime import UTC, datetime

from kronos.storage.db import transaction
from kronos.storage.hashing import article_hash, normalize_title
from kronos.storage.models import Disclosure, NewsArticle
from kronos.storage.repository import insert_disclosures, insert_news, record_run


def test_normalize_title_strips_punct_and_case():
    a = normalize_title("[속보] 삼성전자, 사상최대 실적!")
    b = normalize_title("  [속보]   삼성전자  사상최대  실적  ")
    assert a == b


def test_article_hash_is_deterministic_and_dedupes():
    h1 = article_hash("삼성전자, 호실적!", "https://example.com/a")
    h2 = article_hash("삼성전자 호실적", "https://example.com/a")
    assert h1 == h2


def test_news_insert_dedupes(db_conn):
    items = [
        NewsArticle(
            source="naver",
            title="삼성전자 호실적",
            url="https://e.com/a",
            published_at=datetime(2026, 5, 19, 9, 0, tzinfo=UTC),
            publisher="한경",
        ),
        NewsArticle(
            source="naver",
            title="삼성전자, 호실적!",
            url="https://e.com/a",
            published_at=datetime(2026, 5, 19, 9, 1, tzinfo=UTC),
            publisher="매경",
        ),
    ]
    with transaction(db_conn):
        stats = insert_news(db_conn, items)
    assert stats.fetched == 2
    assert stats.inserted == 1
    assert stats.duplicates == 1
    assert db_conn.execute("SELECT COUNT(*) AS n FROM news").fetchone()["n"] == 1


def test_disclosures_insert_dedupes_by_rcept_no(db_conn):
    item = Disclosure(
        rcept_no="20260519000001",
        report_nm="주요사항보고서(자기주식취득결정)",
        rcept_dt=datetime(2026, 5, 19, 9, 0, tzinfo=UTC),
        corp_code="00126380",
        corp_name="삼성전자",
        ticker="005930",
        pblntf_ty="B",
    )
    with transaction(db_conn):
        insert_disclosures(db_conn, [item, item])
    assert db_conn.execute("SELECT COUNT(*) AS n FROM disclosures").fetchone()["n"] == 1


def test_collector_runs_recorded(db_conn):
    started = datetime(2026, 5, 19, 9, 0, tzinfo=UTC)
    finished = datetime(2026, 5, 19, 9, 0, 5, tzinfo=UTC)
    with transaction(db_conn):
        record_run(
            db_conn,
            source="dart",
            started_at=started,
            finished_at=finished,
            ok=True,
            fetched=3,
            inserted=2,
            duplicates=1,
        )
    row = db_conn.execute("SELECT source, ok, fetched, inserted FROM collector_runs").fetchone()
    assert row["source"] == "dart"
    assert row["ok"] is True
    assert row["fetched"] == 3
    assert row["inserted"] == 2
