from __future__ import annotations

import sqlite3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS news (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    ticker        TEXT,
    title         TEXT    NOT NULL,
    body          TEXT,
    publisher     TEXT,
    url           TEXT,
    published_at  TEXT    NOT NULL,
    hash          TEXT    NOT NULL UNIQUE,
    collected_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_news_ticker_pubat   ON news(ticker, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_source_pubat   ON news(source, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_news_collected      ON news(collected_at DESC);

CREATE TABLE IF NOT EXISTS disclosures (
    rcept_no      TEXT    PRIMARY KEY,
    corp_code     TEXT,
    corp_name     TEXT,
    ticker        TEXT,
    report_nm     TEXT    NOT NULL,
    submitter     TEXT,
    rcept_dt      TEXT    NOT NULL,
    source_url    TEXT,
    pblntf_ty     TEXT,
    pblntf_detail_ty TEXT,
    collected_at  TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_disclosures_ticker_dt ON disclosures(ticker, rcept_dt DESC);
CREATE INDEX IF NOT EXISTS idx_disclosures_collected ON disclosures(collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_disclosures_type      ON disclosures(pblntf_ty);

CREATE TABLE IF NOT EXISTS tickers (
    ticker        TEXT PRIMARY KEY,
    corp_code     TEXT,
    corp_name     TEXT NOT NULL,
    market        TEXT,
    synced_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_tickers_name ON tickers(corp_name);

CREATE TABLE IF NOT EXISTS ticker_aliases (
    alias         TEXT PRIMARY KEY,
    ticker        TEXT NOT NULL REFERENCES tickers(ticker)
);
CREATE INDEX IF NOT EXISTS idx_aliases_ticker ON ticker_aliases(ticker);

CREATE TABLE IF NOT EXISTS collector_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT    NOT NULL,
    started_at    TEXT    NOT NULL,
    finished_at   TEXT,
    ok            INTEGER NOT NULL DEFAULT 0,
    fetched       INTEGER NOT NULL DEFAULT 0,
    inserted      INTEGER NOT NULL DEFAULT 0,
    duplicates    INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_source_started ON collector_runs(source, started_at DESC);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_SQL)
