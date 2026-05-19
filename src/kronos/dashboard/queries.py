"""대시보드용 읽기 전용 SQL 헬퍼."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd


def open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _utc_iso(dt: datetime) -> str:
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def collected_counts_by_hour(conn: sqlite3.Connection, hours: int = 24) -> pd.DataFrame:
    since = _utc_iso(datetime.now(UTC) - timedelta(hours=hours))
    # news (source 컬럼 사용), disclosures(source='dart')를 union
    sql = """
    SELECT strftime('%Y-%m-%d %H:00', collected_at) AS hour, source, COUNT(*) AS n
      FROM news
     WHERE collected_at >= ?
     GROUP BY hour, source
    UNION ALL
    SELECT strftime('%Y-%m-%d %H:00', collected_at) AS hour, 'dart' AS source, COUNT(*) AS n
      FROM disclosures
     WHERE collected_at >= ?
     GROUP BY hour
    """
    return pd.read_sql_query(sql, conn, params=[since, since])


def totals_today(conn: sqlite3.Connection) -> pd.DataFrame:
    now = datetime.now(UTC)
    start = datetime(now.year, now.month, now.day, tzinfo=UTC)
    since = _utc_iso(start)
    sql = """
    SELECT source, COUNT(*) AS n
      FROM news WHERE collected_at >= ? GROUP BY source
    UNION ALL
    SELECT 'dart' AS source, COUNT(*) AS n
      FROM disclosures WHERE collected_at >= ?
    """
    return pd.read_sql_query(sql, conn, params=[since, since])


def source_health(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
    SELECT source,
           MAX(CASE WHEN ok = 1 THEN finished_at END) AS last_success_at,
           MAX(finished_at)                          AS last_run_at,
           SUM(CASE WHEN ok = 0 THEN 1 ELSE 0 END)   AS recent_failures
      FROM collector_runs
     WHERE started_at >= datetime('now', '-1 day')
     GROUP BY source
    """
    return pd.read_sql_query(sql, conn)


def recent_runs(conn: sqlite3.Connection, limit: int = 20) -> pd.DataFrame:
    sql = """
    SELECT source, started_at, finished_at, ok, fetched, inserted, duplicates, error
      FROM collector_runs
     ORDER BY id DESC
     LIMIT ?
    """
    return pd.read_sql_query(sql, conn, params=[limit])


def recent_feed(
    conn: sqlite3.Connection,
    *,
    sources: list[str] | None = None,
    ticker: str | None = None,
    keyword: str | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    # news + disclosures를 통합 뷰처럼 노출
    where_news = []
    where_disc = []
    params_news: list = []
    params_disc: list = []

    if sources:
        # 'dart'를 sources에 포함하면 disclosures 포함, 아니면 제외
        news_sources = [s for s in sources if s != "dart"]
        if news_sources:
            where_news.append(f"source IN ({','.join('?' for _ in news_sources)})")
            params_news.extend(news_sources)
        else:
            where_news.append("1=0")
        if "dart" not in sources:
            where_disc.append("1=0")

    if ticker:
        where_news.append("ticker = ?")
        params_news.append(ticker)
        where_disc.append("ticker = ?")
        params_disc.append(ticker)

    if keyword:
        like = f"%{keyword}%"
        where_news.append("(title LIKE ? OR body LIKE ?)")
        params_news.extend([like, like])
        where_disc.append("(report_nm LIKE ? OR corp_name LIKE ?)")
        params_disc.extend([like, like])

    news_where = " AND ".join(where_news) or "1=1"
    disc_where = " AND ".join(where_disc) or "1=1"

    sql = f"""
    SELECT published_at  AS occurred_at,
           source,
           ticker,
           title,
           publisher       AS source_detail,
           url,
           collected_at
      FROM news
     WHERE {news_where}
    UNION ALL
    SELECT rcept_dt       AS occurred_at,
           'dart'         AS source,
           ticker,
           report_nm      AS title,
           corp_name      AS source_detail,
           source_url     AS url,
           collected_at
      FROM disclosures
     WHERE {disc_where}
     ORDER BY occurred_at DESC
     LIMIT ?
    """
    return pd.read_sql_query(sql, conn, params=[*params_news, *params_disc, limit])


def disclosure_type_distribution(conn: sqlite3.Connection, days: int = 1) -> pd.DataFrame:
    sql = """
    SELECT COALESCE(pblntf_ty, '?') AS pblntf_ty, COUNT(*) AS n
      FROM disclosures
     WHERE collected_at >= datetime('now', ?)
     GROUP BY pblntf_ty
     ORDER BY n DESC
    """
    return pd.read_sql_query(sql, conn, params=[f"-{days} day"])


def quality_metrics(conn: sqlite3.Connection) -> dict:
    # 매칭 성공률 (news.ticker NOT NULL / 전체)
    news_total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] or 0
    news_matched = (
        conn.execute("SELECT COUNT(*) FROM news WHERE ticker IS NOT NULL").fetchone()[0] or 0
    )
    # 중복률 추정: collector_runs 합산
    agg = conn.execute(
        "SELECT COALESCE(SUM(fetched),0), COALESCE(SUM(duplicates),0) FROM collector_runs"
    ).fetchone()
    fetched_total, dup_total = agg
    return {
        "news_total": news_total,
        "news_match_rate": (news_matched / news_total) if news_total else 0.0,
        "fetch_dedup_rate": (dup_total / fetched_total) if fetched_total else 0.0,
    }


def unmatched_samples(conn: sqlite3.Connection, limit: int = 20) -> pd.DataFrame:
    sql = """
    SELECT id, source, title, publisher, published_at
      FROM news
     WHERE ticker IS NULL
     ORDER BY published_at DESC
     LIMIT ?
    """
    return pd.read_sql_query(sql, conn, params=[limit])


def get_news_by_id(conn: sqlite3.Connection, news_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM news WHERE id = ?", (news_id,)).fetchone()
    return dict(row) if row else None


def get_disclosure(conn: sqlite3.Connection, rcept_no: str) -> dict | None:
    row = conn.execute("SELECT * FROM disclosures WHERE rcept_no = ?", (rcept_no,)).fetchone()
    return dict(row) if row else None
