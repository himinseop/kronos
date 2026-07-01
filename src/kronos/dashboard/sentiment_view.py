"""감성 분석 대시보드용 읽기 전용 쿼리 (PostgreSQL)."""

from __future__ import annotations

import pandas as pd
import psycopg

from kronos.dashboard.queries import query_df

MODEL_ID = "kr-finbert-sc"


def coverage(conn: psycopg.Connection, *, model_id: str = MODEL_ID) -> dict:
    """분석 진행률."""
    total = conn.execute("SELECT COUNT(*) AS n FROM news").fetchone()["n"] or 0
    scored = (
        conn.execute(
            "SELECT COUNT(*) AS n FROM sentiments WHERE target_type='news' AND model=%s",
            (model_id,),
        ).fetchone()["n"]
        or 0
    )
    return {
        "news_total": total,
        "scored": scored,
        "pending": total - scored,
        "coverage": (scored / total) if total else 0.0,
    }


def label_distribution(
    conn: psycopg.Connection, *, days: int = 7, model_id: str = MODEL_ID
) -> pd.DataFrame:
    """최근 N일 수집된 뉴스의 감성 라벨 분포."""
    sql = """
    SELECT s.label, COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
     WHERE s.target_type='news' AND s.model=%s
       AND n.published_at >= now() - make_interval(days => %s)
     GROUP BY s.label
    """
    return query_df(conn, sql, [model_id, days])


def daily_sentiment_trend(
    conn: psycopg.Connection,
    *,
    ticker: str | None = None,
    days: int = 30,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """일별 평균 감성 점수 + 건수. ticker 지정 시 해당 종목만."""
    where_ticker = "AND n.ticker = %s" if ticker else ""
    sql = f"""
    SELECT n.published_at::date AS day,
           AVG(s.score) AS avg_score,
           COUNT(*)     AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
     WHERE s.target_type='news' AND s.model=%s
       AND n.published_at >= now() - make_interval(days => %s)
       {where_ticker}
     GROUP BY day
     ORDER BY day
    """
    params = [model_id, days]
    if ticker:
        params.append(ticker)
    return query_df(conn, sql, params)


def top_by_sentiment(
    conn: psycopg.Connection,
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
           round(AVG(s.score)::numeric, 3) AS avg_score,
           COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
      LEFT JOIN tickers t ON t.ticker = n.ticker
     WHERE s.target_type='news' AND s.model=%s
       AND n.published_at >= now() - make_interval(days => %s)
       AND n.ticker IS NOT NULL
     GROUP BY n.ticker, t.corp_name
     HAVING COUNT(*) >= %s
     ORDER BY AVG(s.score) {order}
     LIMIT %s
    """
    return query_df(conn, sql, [model_id, days, min_count, limit])


def recent_scored_feed(
    conn: psycopg.Connection,
    *,
    label: str | None = None,
    ticker: str | None = None,
    limit: int = 200,
    model_id: str = MODEL_ID,
) -> pd.DataFrame:
    """감성 점수가 붙은 최근 뉴스 피드."""
    conds = ["s.target_type='news'", "s.model=%s"]
    params: list = [model_id]
    if label:
        conds.append("s.label=%s")
        params.append(label)
    if ticker:
        conds.append("n.ticker=%s")
        params.append(ticker)
    where = " AND ".join(conds)
    sql = f"""
    SELECT n.published_at AS occurred_at,
           s.label,
           round(s.score::numeric, 2) AS score,
           n.ticker,
           n.title,
           n.publisher,
           n.url
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
     WHERE {where}
     ORDER BY n.published_at DESC
     LIMIT %s
    """
    params.append(limit)
    return query_df(conn, sql, params)
