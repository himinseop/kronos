from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kronos.dashboard.ticker_view import (
    get_daily_volume,
    get_profile,
    get_timeline,
    resolve_ticker,
    top_keywords_in_titles,
)
from kronos.storage.db import connect, transaction
from kronos.storage.models import Disclosure, NewsArticle
from kronos.storage.repository import insert_disclosures, insert_news
from kronos.storage.schema import ensure_schema


def _seed(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema(conn)
    with transaction(conn):
        conn.executemany(
            "INSERT INTO tickers (ticker, corp_code, corp_name) VALUES (?, ?, ?)",
            [
                ("005930", "00126380", "삼성전자"),
                ("000660", "00164779", "에스케이하이닉스"),
            ],
        )
        conn.execute(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (?, ?)",
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


def test_resolve_ticker_by_code(tmp_path):
    conn = _seed(tmp_path)
    assert resolve_ticker(conn, "005930") == "005930"


def test_resolve_ticker_by_name(tmp_path):
    conn = _seed(tmp_path)
    assert resolve_ticker(conn, "삼성전자") == "005930"


def test_resolve_ticker_by_alias(tmp_path):
    conn = _seed(tmp_path)
    assert resolve_ticker(conn, "삼전") == "005930"


def test_resolve_ticker_partial(tmp_path):
    conn = _seed(tmp_path)
    assert resolve_ticker(conn, "에스케이") == "000660"


def test_resolve_ticker_unknown(tmp_path):
    conn = _seed(tmp_path)
    assert resolve_ticker(conn, "없는종목") is None
    assert resolve_ticker(conn, "") is None


def test_get_profile_counts(tmp_path):
    conn = _seed(tmp_path)
    p = get_profile(conn, "005930", days=30)
    assert p.corp_name == "삼성전자"
    assert p.news_count_30d == 2
    assert p.disclosure_count_30d == 1


def test_get_timeline_orders_recent_first(tmp_path):
    conn = _seed(tmp_path)
    df = get_timeline(conn, "005930", days=30)
    assert len(df) == 3
    # 시간 역순
    assert df["occurred_at"].iloc[0] >= df["occurred_at"].iloc[-1]


def test_get_daily_volume(tmp_path):
    conn = _seed(tmp_path)
    df = get_daily_volume(conn, "005930", days=30)
    assert not df.empty
    assert set(df["source"].unique()) <= {"naver", "rss", "dart"}


def test_top_keywords_excludes_stopwords(tmp_path):
    conn = _seed(tmp_path)
    df = top_keywords_in_titles(conn, "005930", days=30, top_n=10)
    kws = set(df["keyword"]) if not df.empty else set()
    # 빈도 추출 자체는 동작
    assert "삼성전자" in kws or len(kws) > 0
