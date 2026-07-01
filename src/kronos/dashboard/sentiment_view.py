"""감성 분석 대시보드용 읽기 전용 쿼리."""

from __future__ import annotations

import sqlite3

import pandas as pd

MODEL_ID = "kr-finbert-sc"


def coverage(conn: sqlite3.Connection, *, model_id: str = MODEL_ID) -> dict:
    """분석 진행률."""
    total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0] or 0
    scored = (
        conn.execute(
            "SELECT COUNT(*) FROM sentiments WHERE target_type='news' AND model=?",
            (model_id,),
        ).fetchone()[0]
        or 0
    )
    return {
        "news_total": total,
        "scored": scored,
        "pending": total - scored,
        "coverage": (scored / total) if total else 0.0,
    }


def label_distribution(
    conn: sqlite3.Connection, *, days: int = 7, model_id: str = MODEL_ID
) -> pd.DataFrame:
    """최근 N일 수집된 뉴스의 감성 라벨 분포."""
    sql = """
    SELECT s.label, COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = CAST(s.target_id AS INTEGER)
     WHERE s.target_type='news' AND s.model=?
       AND n.published_at >= datetime('now', ?)
     GROUP BY s.label
    """
    return pd.read_sql_query(sql, conn, params=[model_id, f"-{int(days)} day"])


def daily_sentiment_trend(
    conn: sqlite3.Connection,
    *,
    ticker: str | None = None,
    days: int = 30,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """일별 평균 감성 점수 + 건수. ticker 지정 시 해당 종목만."""
    where_ticker = "AND n.ticker = ?" if ticker else ""
    sql = f"""
    SELECT date(n.published_at) AS day,
           AVG(s.score) AS avg_score,
           COUNT(*)     AS n
      FROM sentiments s
      JOIN news n ON n.id = CAST(s.target_id AS INTEGER)
     WHERE s.target_type='news' AND s.model=?
       AND n.published_at >= datetime('now', ?)
       {where_ticker}
     GROUP BY day
     ORDER BY day
    """
    params = [model_id, f"-{int(days)} day"]
    if ticker:
        params.append(ticker)
    return pd.read_sql_query(sql, conn, params=params)


def top_by_sentiment(
    conn: sqlite3.Connection,
    *,
    positive: bool,
    days: int = 3,
    min_count: int = 3,
    limit: int = 15,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """최근 N일 종목별 평균 감성 상/하위. 최소 건수 이상만."""
    order = "DESC" if positive else "ASC"
    sql = f"""
    SELECT n.ticker,
           t.corp_name,
           printf('%.3f', AVG(s.score)) AS avg_score,
           COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = CAST(s.target_id AS INTEGER)
      LEFT JOIN tickers t ON t.ticker = n.ticker
     WHERE s.target_type='news' AND s.model=?
       AND n.published_at >= datetime('now', ?)
       AND n.ticker IS NOT NULL
     GROUP BY n.ticker
     HAVING COUNT(*) >= ?
     ORDER BY AVG(s.score) {order}
     LIMIT ?
    """
    return pd.read_sql_query(sql, conn, params=[model_id, f"-{int(days)} day", min_count, limit])


def recent_scored_feed(
    conn: sqlite3.Connection,
    *,
    label: str | None = None,
    ticker: str | None = None,
    limit: int = 200,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """감성 점수가 붙은 최근 뉴스 피드."""
    conds = ["s.target_type='news'", "s.model=?"]
    params: list = [model_id]
    if label:
        conds.append("s.label=?")
        params.append(label)
    if ticker:
        conds.append("n.ticker=?")
        params.append(ticker)
    where = " AND ".join(conds)
    sql = f"""
    SELECT n.published_at AS occurred_at,
           s.label,
           printf('%+.2f', s.score) AS score,
           n.ticker,
           n.title,
           n.publisher,
           n.url
      FROM sentiments s
      JOIN news n ON n.id = CAST(s.target_id AS INTEGER)
     WHERE {where}
     ORDER BY n.published_at DESC
     LIMIT ?
    """
    params.append(limit)
    return pd.read_sql_query(sql, conn, params=params)
