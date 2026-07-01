from __future__ import annotations

import psycopg

# PostgreSQL DDL. 각 문장을 개별 실행(psycopg는 execute당 단일 문장).
SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS news (
        id            BIGSERIAL   PRIMARY KEY,
        source        TEXT        NOT NULL,
        ticker        TEXT,
        title         TEXT        NOT NULL,
        body          TEXT,
        publisher     TEXT,
        url           TEXT,
        published_at  TIMESTAMPTZ NOT NULL,
        hash          TEXT        NOT NULL UNIQUE,
        collected_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_news_ticker_pubat ON news(ticker, published_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_news_source_pubat ON news(source, published_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_news_collected    ON news(collected_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS disclosures (
        rcept_no         TEXT        PRIMARY KEY,
        corp_code        TEXT,
        corp_name        TEXT,
        ticker           TEXT,
        report_nm        TEXT        NOT NULL,
        submitter        TEXT,
        rcept_dt         TIMESTAMPTZ NOT NULL,
        source_url       TEXT,
        pblntf_ty        TEXT,
        pblntf_detail_ty TEXT,
        collected_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_disclosures_ticker_dt ON disclosures(ticker, rcept_dt DESC)",
    "CREATE INDEX IF NOT EXISTS idx_disclosures_collected ON disclosures(collected_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_disclosures_type      ON disclosures(pblntf_ty)",
    """
    CREATE TABLE IF NOT EXISTS tickers (
        ticker     TEXT PRIMARY KEY,
        corp_code  TEXT,
        corp_name  TEXT        NOT NULL,
        market     TEXT,
        synced_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tickers_name ON tickers(corp_name)",
    """
    CREATE TABLE IF NOT EXISTS ticker_aliases (
        alias   TEXT PRIMARY KEY,
        ticker  TEXT NOT NULL REFERENCES tickers(ticker)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_aliases_ticker ON ticker_aliases(ticker)",
    """
    CREATE TABLE IF NOT EXISTS collector_runs (
        id           BIGSERIAL PRIMARY KEY,
        source       TEXT        NOT NULL,
        started_at   TIMESTAMPTZ NOT NULL,
        finished_at  TIMESTAMPTZ,
        ok           BOOLEAN     NOT NULL DEFAULT false,
        fetched      INTEGER     NOT NULL DEFAULT 0,
        inserted     INTEGER     NOT NULL DEFAULT 0,
        duplicates   INTEGER     NOT NULL DEFAULT 0,
        error        TEXT
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_runs_source_started ON collector_runs(source, started_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS sentiments (
        id           BIGSERIAL   PRIMARY KEY,
        target_type  TEXT        NOT NULL,
        target_id    TEXT        NOT NULL,
        model        TEXT        NOT NULL,
        score        REAL        NOT NULL,
        label        TEXT        NOT NULL,
        confidence   REAL,
        category     TEXT,
        rationale    TEXT,
        analyzed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
        UNIQUE (target_type, target_id, model)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_sentiments_target ON sentiments(target_type, target_id)",
    "CREATE INDEX IF NOT EXISTS idx_sentiments_model  ON sentiments(model, analyzed_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_sentiments_label  ON sentiments(label)",
)


def ensure_schema(conn: psycopg.Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
