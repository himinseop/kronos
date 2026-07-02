"""카테고리 분류(자체 LLM) 대시보드용 읽기 전용 쿼리 (PostgreSQL)."""

from __future__ import annotations

import pandas as pd
import psycopg

from kronos.analysis.classify import CATEGORIES
from kronos.dashboard.queries import query_df

MODEL_LIKE = "cat:%"  # 카테고리 분류 행 식별 (model='cat:<모델명>')

# 한국어 라벨 (표시용)
CATEGORY_LABELS: dict[str, str] = {
    "earnings": "실적",
    "contract": "수주·계약",
    "ma": "인수합병·지분",
    "financing": "자금조달",
    "regulation": "규제·정책",
    "product": "신제품·기술",
    "legal": "소송·사건",
    "management": "경영·인사",
    "market": "시황·수급",
    "other": "기타",
}

assert set(CATEGORY_LABELS) == set(CATEGORIES)  # 정의 동기화 보장


def coverage(conn: psycopg.Connection) -> dict:
    """분류 진행률 (대상 = 종목 매칭 뉴스)."""
    target = (
        conn.execute("SELECT COUNT(*) AS n FROM news WHERE ticker IS NOT NULL").fetchone()["n"] or 0
    )
    classified = (
        conn.execute(
            "SELECT COUNT(*) AS n FROM sentiments WHERE target_type='news' AND model LIKE %s",
            (MODEL_LIKE,),
        ).fetchone()["n"]
        or 0
    )
    return {
        "target": target,
        "classified": classified,
        "pending": target - classified,
        "coverage": (classified / target) if target else 0.0,
    }


def category_distribution(conn: psycopg.Connection, *, days: int = 7) -> pd.DataFrame:
    """최근 N일 뉴스의 카테고리 분포 (한국어 라벨 포함)."""
    sql = """
    SELECT s.category, COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
     WHERE s.target_type='news' AND s.model LIKE %s
       AND n.published_at >= now() - make_interval(days => %s)
     GROUP BY s.category
     ORDER BY n DESC
    """
    df = query_df(conn, sql, [MODEL_LIKE, days])
    if not df.empty:
        df["label"] = df["category"].map(CATEGORY_LABELS).fillna(df["category"])
    return df


def daily_category_trend(conn: psycopg.Connection, *, days: int = 30) -> pd.DataFrame:
    """일별 카테고리별 건수 (스택 영역 차트용)."""
    sql = """
    SELECT n.published_at::date AS day, s.category, COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
     WHERE s.target_type='news' AND s.model LIKE %s
       AND n.published_at >= now() - make_interval(days => %s)
     GROUP BY day, s.category
     ORDER BY day
    """
    df = query_df(conn, sql, [MODEL_LIKE, days])
    if not df.empty:
        df["label"] = df["category"].map(CATEGORY_LABELS).fillna(df["category"])
    return df


def top_tickers_by_category(
    conn: psycopg.Connection, *, category: str, days: int = 30, limit: int = 20
) -> pd.DataFrame:
    """특정 카테고리 뉴스가 많은 종목."""
    sql = """
    SELECT n.ticker,
           t.corp_name,
           COUNT(*) AS n
      FROM sentiments s
      JOIN news n ON n.id = s.target_id::bigint
      LEFT JOIN tickers t ON t.ticker = n.ticker
     WHERE s.target_type='news' AND s.model LIKE %s
       AND s.category = %s
       AND n.published_at >= now() - make_interval(days => %s)
     GROUP BY n.ticker, t.corp_name
     ORDER BY n DESC
     LIMIT %s
    """
    return query_df(conn, sql, [MODEL_LIKE, category, days, limit])


def recent_classified_feed(
    conn: psycopg.Connection,
    *,
    category: str | None = None,
    ticker: str | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    """카테고리가 붙은 최근 뉴스 피드."""
    conds = ["s.target_type='news'", "s.model LIKE %s"]
    params: list = [MODEL_LIKE]
    if category:
        conds.append("s.category=%s")
        params.append(category)
    if ticker:
        conds.append("n.ticker=%s")
        params.append(ticker)
    where = " AND ".join(conds)
    sql = f"""
    SELECT n.published_at AS occurred_at,
           s.category,
           round(s.confidence::numeric, 2) AS confidence,
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
    df = query_df(conn, sql, params)
    if not df.empty:
        df["category_ko"] = df["category"].map(CATEGORY_LABELS).fillna(df["category"])
    return df
