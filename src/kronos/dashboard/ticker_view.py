"""종목 페이지: 한 종목의 최근 공시·뉴스 통합 뷰."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

import pandas as pd


@dataclass(slots=True)
class TickerProfile:
    ticker: str
    corp_name: str | None
    market: str | None
    news_count_30d: int
    disclosure_count_30d: int
    last_news_at: str | None
    last_disclosure_at: str | None


def resolve_ticker(conn: sqlite3.Connection, query: str) -> str | None:
    """입력이 종목코드(6자리) 또는 종목명·별칭일 때 ticker로 정규화."""
    q = query.strip()
    if not q:
        return None
    # 숫자 6자리면 ticker 그대로
    if q.isdigit() and len(q) == 6:
        row = conn.execute("SELECT ticker FROM tickers WHERE ticker = ?", (q,)).fetchone()
        return row[0] if row else None
    # 정확한 corp_name 매칭
    row = conn.execute("SELECT ticker FROM tickers WHERE corp_name = ?", (q,)).fetchone()
    if row:
        return row[0]
    # 별칭
    row = conn.execute("SELECT ticker FROM ticker_aliases WHERE alias = ?", (q,)).fetchone()
    if row:
        return row[0]
    # 부분 매칭 (가장 짧은 이름 먼저)
    row = conn.execute(
        "SELECT ticker FROM tickers WHERE corp_name LIKE ? ORDER BY length(corp_name) LIMIT 1",
        (f"%{q}%",),
    ).fetchone()
    return row[0] if row else None


def get_profile(conn: sqlite3.Connection, ticker: str, *, days: int = 30) -> TickerProfile:
    row = conn.execute(
        "SELECT corp_name, market FROM tickers WHERE ticker = ?", (ticker,)
    ).fetchone()
    corp_name = row[0] if row else None
    market = row[1] if row else None

    n_news = conn.execute(
        f"SELECT COUNT(*) FROM news WHERE ticker = ? AND published_at >= datetime('now', '-{int(days)} day')",
        (ticker,),
    ).fetchone()[0]

    n_disc = conn.execute(
        f"SELECT COUNT(*) FROM disclosures WHERE ticker = ? AND rcept_dt >= datetime('now', '-{int(days)} day')",
        (ticker,),
    ).fetchone()[0]

    last_news = conn.execute(
        "SELECT MAX(published_at) FROM news WHERE ticker = ?", (ticker,)
    ).fetchone()[0]
    last_disc = conn.execute(
        "SELECT MAX(rcept_dt) FROM disclosures WHERE ticker = ?", (ticker,)
    ).fetchone()[0]

    return TickerProfile(
        ticker=ticker,
        corp_name=corp_name,
        market=market,
        news_count_30d=n_news,
        disclosure_count_30d=n_disc,
        last_news_at=last_news,
        last_disclosure_at=last_disc,
    )


def get_timeline(conn: sqlite3.Connection, ticker: str, *, days: int = 30) -> pd.DataFrame:
    """공시·뉴스 통합 시간 역순 타임라인."""
    sql = """
    SELECT 'dart' AS source, rcept_dt AS occurred_at, report_nm AS title,
           corp_name AS entity, source_url AS url, pblntf_ty AS extra
      FROM disclosures
     WHERE ticker = ? AND rcept_dt >= datetime('now', ?)
    UNION ALL
    SELECT source, published_at, title, publisher, url, NULL
      FROM news
     WHERE ticker = ? AND published_at >= datetime('now', ?)
     ORDER BY occurred_at DESC
    """
    win = f"-{int(days)} day"
    return pd.read_sql_query(sql, conn, params=[ticker, win, ticker, win])


def get_daily_volume(conn: sqlite3.Connection, ticker: str, *, days: int = 30) -> pd.DataFrame:
    """종목별 일일 공시·뉴스 건수 (스파크라인용)."""
    sql = """
    SELECT day, source, SUM(n) AS n FROM (
      SELECT date(published_at) AS day, source, COUNT(*) AS n
        FROM news
       WHERE ticker = ? AND published_at >= datetime('now', ?)
       GROUP BY day, source
      UNION ALL
      SELECT date(rcept_dt) AS day, 'dart' AS source, COUNT(*) AS n
        FROM disclosures
       WHERE ticker = ? AND rcept_dt >= datetime('now', ?)
       GROUP BY day
    ) GROUP BY day, source ORDER BY day
    """
    win = f"-{int(days)} day"
    return pd.read_sql_query(sql, conn, params=[ticker, win, ticker, win])


def top_keywords_in_titles(
    conn: sqlite3.Connection, ticker: str, *, days: int = 30, top_n: int = 15
) -> pd.DataFrame:
    """간단한 단어 빈도. 형태소 분석 없이 공백·구두점 기반."""
    import re
    from collections import Counter

    rows = conn.execute(
        f"""
        SELECT title FROM news
         WHERE ticker = ? AND published_at >= datetime('now', '-{int(days)} day')
        UNION ALL
        SELECT report_nm FROM disclosures
         WHERE ticker = ? AND rcept_dt >= datetime('now', '-{int(days)} day')
        """,
        (ticker, ticker),
    ).fetchall()

    word_re = re.compile(r"[가-힣A-Za-z0-9]{2,}")
    stopwords = {"기업", "회사", "주식", "회장", "사장", "대표", "발표", "공시", "보고서"}
    counter: Counter[str] = Counter()
    for (text,) in rows:
        if not text:
            continue
        for w in word_re.findall(text):
            if w in stopwords or w.isdigit():
                continue
            counter[w] += 1

    items = counter.most_common(top_n)
    return pd.DataFrame(items, columns=["keyword", "count"])
