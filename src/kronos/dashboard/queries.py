"""대시보드용 읽기 전용 SQL 헬퍼 (PostgreSQL)."""

from __future__ import annotations

import pandas as pd
import psycopg

from kronos.storage.db import connect


def open_db(dsn: str | None = None) -> psycopg.Connection:
    return connect(dsn)


def query_df(
    conn: psycopg.Connection, sql: str, params: list | tuple | None = None
) -> pd.DataFrame:
    """psycopg dict_row 결과를 DataFrame으로. (pd.read_sql_query는 dict_row와 오동작)."""
    rows = conn.execute(sql, params or ()).fetchall()
    return pd.DataFrame(rows)


def collected_counts_by_hour(conn: psycopg.Connection, hours: int = 24) -> pd.DataFrame:
    sql = """
    SELECT to_char(collected_at, 'YYYY-MM-DD HH24:00') AS hour, source, COUNT(*) AS n
      FROM news
     WHERE collected_at >= now() - make_interval(hours => %s)
     GROUP BY hour, source
    UNION ALL
    SELECT to_char(collected_at, 'YYYY-MM-DD HH24:00') AS hour, 'dart' AS source, COUNT(*) AS n
      FROM disclosures
     WHERE collected_at >= now() - make_interval(hours => %s)
     GROUP BY hour
    """
    return query_df(conn, sql, [hours, hours])


def totals_today(conn: psycopg.Connection) -> pd.DataFrame:
    sql = """
    SELECT source, COUNT(*) AS n
      FROM news WHERE collected_at >= date_trunc('day', now()) GROUP BY source
    UNION ALL
    SELECT 'dart' AS source, COUNT(*) AS n
      FROM disclosures WHERE collected_at >= date_trunc('day', now())
    """
    return query_df(conn, sql)


def source_health(conn: psycopg.Connection) -> pd.DataFrame:
    sql = """
    SELECT source,
           MAX(finished_at) FILTER (WHERE ok) AS last_success_at,
           MAX(finished_at)                   AS last_run_at,
           SUM(CASE WHEN NOT ok THEN 1 ELSE 0 END) AS recent_failures
      FROM collector_runs
     WHERE started_at >= now() - interval '1 day'
     GROUP BY source
    """
    return query_df(conn, sql)


def recent_runs(conn: psycopg.Connection, limit: int = 20) -> pd.DataFrame:
    sql = """
    SELECT source, started_at, finished_at, ok, fetched, inserted, duplicates, error
      FROM collector_runs
     ORDER BY id DESC
     LIMIT %s
    """
    return query_df(conn, sql, [limit])


def recent_feed(
    conn: psycopg.Connection,
    *,
    sources: list[str] | None = None,
    ticker: str | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    where_news = []
    where_disc = []
    params_news: list = []
    params_disc: list = []

    if sources:
        news_sources = [s for s in sources if s != "dart"]
        if news_sources:
            where_news.append(f"source IN ({','.join(['%s'] * len(news_sources))})")
            params_news.extend(news_sources)
        else:
            where_news.append("FALSE")
        if "dart" not in sources:
            where_disc.append("FALSE")

    if ticker:
        where_news.append("ticker = %s")
        params_news.append(ticker)
        where_disc.append("ticker = %s")
        params_disc.append(ticker)

    if keyword:
        like = f"%{keyword}%"
        where_news.append("(title ILIKE %s OR body ILIKE %s)")
        params_news.extend([like, like])
        where_disc.append("(report_nm ILIKE %s OR corp_name ILIKE %s)")
        params_disc.extend([like, like])

    news_where = " AND ".join(where_news) or "TRUE"
    disc_where = " AND ".join(where_disc) or "TRUE"

    sql = f"""
    SELECT published_at AS occurred_at, source, ticker, title,
           publisher AS source_detail, url, collected_at
      FROM news
     WHERE {news_where}
    UNION ALL
    SELECT rcept_dt AS occurred_at, 'dart' AS source, ticker, report_nm AS title,
           corp_name AS source_detail, source_url AS url, collected_at
      FROM disclosures
     WHERE {disc_where}
     ORDER BY occurred_at DESC
     LIMIT %s
    """
    return query_df(conn, sql, [*params_news, *params_disc, limit])


def disclosure_type_distribution(conn: psycopg.Connection, days: int = 1) -> pd.DataFrame:
    sql = """
    SELECT COALESCE(pblntf_ty, '?') AS pblntf_ty, COUNT(*) AS n
      FROM disclosures
     WHERE collected_at >= now() - make_interval(days => %s)
     GROUP BY pblntf_ty
     ORDER BY n DESC
    """
    return query_df(conn, sql, [days])


def quality_metrics(conn: psycopg.Connection) -> dict:
    news_total = conn.execute("SELECT COUNT(*) AS n FROM news").fetchone()["n"] or 0
    news_matched = (
        conn.execute("SELECT COUNT(*) AS n FROM news WHERE ticker IS NOT NULL").fetchone()["n"] or 0
    )
    agg = conn.execute(
        "SELECT COALESCE(SUM(fetched),0) AS f, COALESCE(SUM(duplicates),0) AS d FROM collector_runs"
    ).fetchone()
    fetched_total, dup_total = agg["f"], agg["d"]
    return {
        "news_total": news_total,
        "news_match_rate": (news_matched / news_total) if news_total else 0.0,
        "fetch_dedup_rate": (dup_total / fetched_total) if fetched_total else 0.0,
    }


def unmatched_samples(conn: psycopg.Connection, limit: int = 20) -> pd.DataFrame:
    sql = """
    SELECT id, source, title, publisher, published_at
      FROM news
     WHERE ticker IS NULL
     ORDER BY published_at DESC
     LIMIT %s
    """
    return query_df(conn, sql, [limit])


def get_news_by_id(conn: psycopg.Connection, news_id: int) -> dict | None:
    return conn.execute("SELECT * FROM news WHERE id = %s", (news_id,)).fetchone()


def get_disclosure(conn: psycopg.Connection, rcept_no: str) -> dict | None:
    return conn.execute("SELECT * FROM disclosures WHERE rcept_no = %s", (rcept_no,)).fetchone()
