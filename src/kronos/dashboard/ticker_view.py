"""종목 페이지: 한 종목의 최근 공시·뉴스 통합 뷰 (PostgreSQL)."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import psycopg

from kronos.dashboard.queries import query_df


@dataclass(slots=True)
class TickerProfile:
    ticker: str
    corp_name: str | None
    market: str | None
    news_count_30d: int
    disclosure_count_30d: int
    last_news_at: str | None
    last_disclosure_at: str | None


def resolve_ticker(conn: psycopg.Connection, query: str) -> str | None:
    """입력이 종목코드(6자리) 또는 종목명·별칭일 때 ticker로 정규화."""
    q = query.strip()
    if not q:
        return None
    if q.isdigit() and len(q) == 6:
        row = conn.execute("SELECT ticker FROM tickers WHERE ticker = %s", (q,)).fetchone()
        return row["ticker"] if row else None
    row = conn.execute("SELECT ticker FROM tickers WHERE corp_name = %s", (q,)).fetchone()
    if row:
        return row["ticker"]
    row = conn.execute("SELECT ticker FROM ticker_aliases WHERE alias = %s", (q,)).fetchone()
    if row:
        return row["ticker"]
    row = conn.execute(
        "SELECT ticker FROM tickers WHERE corp_name LIKE %s ORDER BY length(corp_name) LIMIT 1",
        (f"%{q}%",),
    ).fetchone()
    return row["ticker"] if row else None


def get_profile(conn: psycopg.Connection, ticker: str, *, days: int = 30) -> TickerProfile:
    row = conn.execute(
        "SELECT corp_name, market FROM tickers WHERE ticker = %s", (ticker,)
    ).fetchone()
    corp_name = row["corp_name"] if row else None
    market = row["market"] if row else None

    n_news = conn.execute(
        "SELECT COUNT(*) AS n FROM news "
        "WHERE ticker = %s AND published_at >= now() - make_interval(days => %s)",
        (ticker, days),
    ).fetchone()["n"]

    n_disc = conn.execute(
        "SELECT COUNT(*) AS n FROM disclosures "
        "WHERE ticker = %s AND rcept_dt >= now() - make_interval(days => %s)",
        (ticker, days),
    ).fetchone()["n"]

    last_news = conn.execute(
        "SELECT MAX(published_at) AS m FROM news WHERE ticker = %s", (ticker,)
    ).fetchone()["m"]
    last_disc = conn.execute(
        "SELECT MAX(rcept_dt) AS m FROM disclosures WHERE ticker = %s", (ticker,)
    ).fetchone()["m"]

    return TickerProfile(
        ticker=ticker,
        corp_name=corp_name,
        market=market,
        news_count_30d=n_news,
        disclosure_count_30d=n_disc,
        last_news_at=str(last_news) if last_news else None,
        last_disclosure_at=str(last_disc) if last_disc else None,
    )


def get_timeline(conn: psycopg.Connection, ticker: str, *, days: int = 30) -> pd.DataFrame:
    """공시·뉴스 통합 시간 역순 타임라인."""
    sql = """
    SELECT 'dart' AS source, rcept_dt AS occurred_at, report_nm AS title,
           corp_name AS entity, source_url AS url, pblntf_ty AS extra
      FROM disclosures
     WHERE ticker = %s AND rcept_dt >= now() - make_interval(days => %s)
    UNION ALL
    SELECT source, published_at, title, publisher, url, NULL
      FROM news
     WHERE ticker = %s AND published_at >= now() - make_interval(days => %s)
     ORDER BY occurred_at DESC
    """
    return query_df(conn, sql, [ticker, days, ticker, days])


def get_daily_volume(conn: psycopg.Connection, ticker: str, *, days: int = 30) -> pd.DataFrame:
    """종목별 일일 공시·뉴스 건수 (스파크라인용)."""
    sql = """
    SELECT day, source, SUM(n) AS n FROM (
      SELECT published_at::date AS day, source, COUNT(*) AS n
        FROM news
       WHERE ticker = %s AND published_at >= now() - make_interval(days => %s)
       GROUP BY day, source
      UNION ALL
      SELECT rcept_dt::date AS day, 'dart' AS source, COUNT(*) AS n
        FROM disclosures
       WHERE ticker = %s AND rcept_dt >= now() - make_interval(days => %s)
       GROUP BY day
    ) t GROUP BY day, source ORDER BY day
    """
    return query_df(conn, sql, [ticker, days, ticker, days])


def top_keywords_in_titles(
    conn: psycopg.Connection, ticker: str, *, days: int = 30, top_n: int = 15
) -> pd.DataFrame:
    """간단한 단어 빈도. 형태소 분석 없이 공백·구두점 기반."""
    import re
    from collections import Counter

    rows = conn.execute(
        """
        SELECT title AS t FROM news
         WHERE ticker = %s AND published_at >= now() - make_interval(days => %s)
        UNION ALL
        SELECT report_nm AS t FROM disclosures
         WHERE ticker = %s AND rcept_dt >= now() - make_interval(days => %s)
        """,
        (ticker, days, ticker, days),
    ).fetchall()

    word_re = re.compile(r"[가-힣A-Za-z0-9]{2,}")
    stopwords = {"기업", "회사", "주식", "회장", "사장", "대표", "발표", "공시", "보고서"}
    counter: Counter[str] = Counter()
    for row in rows:
        text = row["t"]
        if not text:
            continue
        for w in word_re.findall(text):
            if w in stopwords or w.isdigit():
                continue
            counter[w] += 1

    items = counter.most_common(top_n)
    return pd.DataFrame(items, columns=["keyword", "count"])
