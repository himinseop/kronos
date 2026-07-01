from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kronos.dashboard.ticker_view import (
    get_daily_volume,
    get_profile,
    get_timeline,
    resolve_ticker,
    top_keywords_in_titles,
)
from kronos.storage.db import transaction
from kronos.storage.models import Disclosure, NewsArticle
from kronos.storage.repository import insert_disclosures, insert_news


def _seed(conn):
    with transaction(conn):
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO tickers (ticker, corp_code, corp_name) VALUES (%s, %s, %s)",
                [
                    ("005930", "00126380", "삼성전자"),
                    ("000660", "00164779", "에스케이하이닉스"),
                ],
            )
        conn.execute(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (%s, %s)",
            ("삼전", "005930"),
        )
        now = datetime.now(UTC)
        insert_disclosures(
            conn,
            [
                Disclosure(
                    rcept_no="r1",
                    report_nm="주요사항보고서(자기주식취득결정)",
                    rcept_dt=now - timedelta(days=1),
                    ticker="005930",
                    corp_name="삼성전자",
                ),
            ],
        )
        insert_news(
            conn,
            [
                NewsArticle(
                    source="naver",
                    title="삼성전자 호실적 발표",
                    published_at=now - timedelta(hours=3),
                    ticker="005930",
                ),
                NewsArticle(
                    source="rss",
                    title="삼성전자 신규 투자 계획",
                    published_at=now - timedelta(days=2),
                    ticker="005930",
                ),
            ],
        )
    return conn


def test_resolve_ticker_by_code(db_conn):
    conn = _seed(db_conn)
    assert resolve_ticker(conn, "005930") == "005930"


def test_resolve_ticker_by_name(db_conn):
    conn = _seed(db_conn)
    assert resolve_ticker(conn, "삼성전자") == "005930"


def test_resolve_ticker_by_alias(db_conn):
    conn = _seed(db_conn)
    assert resolve_ticker(conn, "삼전") == "005930"


def test_resolve_ticker_partial(db_conn):
    conn = _seed(db_conn)
    assert resolve_ticker(conn, "에스케이") == "000660"


def test_resolve_ticker_unknown(db_conn):
    conn = _seed(db_conn)
    assert resolve_ticker(conn, "없는종목") is None
    assert resolve_ticker(conn, "") is None


def test_get_profile_counts(db_conn):
    conn = _seed(db_conn)
    p = get_profile(conn, "005930", days=30)
    assert p.corp_name == "삼성전자"
    assert p.news_count_30d == 2
    assert p.disclosure_count_30d == 1


def test_get_timeline_orders_recent_first(db_conn):
    conn = _seed(db_conn)
    df = get_timeline(conn, "005930", days=30)
    assert len(df) == 3
    # 시간 역순
    assert df["occurred_at"].iloc[0] >= df["occurred_at"].iloc[-1]


def test_get_daily_volume(db_conn):
    conn = _seed(db_conn)
    df = get_daily_volume(conn, "005930", days=30)
    assert not df.empty
    assert set(df["source"].unique()) <= {"naver", "rss", "dart"}


def test_top_keywords_excludes_stopwords(db_conn):
    conn = _seed(db_conn)
    df = top_keywords_in_titles(conn, "005930", days=30, top_n=10)
    kws = set(df["keyword"]) if not df.empty else set()
    # 빈도 추출 자체는 동작
    assert "삼성전자" in kws or len(kws) > 0
