from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from kronos.storage.hashing import article_hash
from kronos.storage.models import Disclosure, NewsArticle


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


@dataclass(slots=True)
class InsertStats:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0


def insert_news(conn: sqlite3.Connection, items: Iterable[NewsArticle]) -> InsertStats:
    stats = InsertStats()
    for item in items:
        stats.fetched += 1
        h = article_hash(item.title, item.url)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO news
              (source, ticker, title, body, publisher, url, published_at, hash)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.source,
                item.ticker,
                item.title,
                item.body,
                item.publisher,
                item.url,
                _iso(item.published_at),
                h,
            ),
        )
        if cur.rowcount > 0:
            stats.inserted += 1
        else:
            stats.duplicates += 1
    return stats


def insert_disclosures(conn: sqlite3.Connection, items: Iterable[Disclosure]) -> InsertStats:
    stats = InsertStats()
    for item in items:
        stats.fetched += 1
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO disclosures
              (rcept_no, corp_code, corp_name, ticker, report_nm, submitter, rcept_dt,
               source_url, pblntf_ty, pblntf_detail_ty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item.rcept_no,
                item.corp_code,
                item.corp_name,
                item.ticker,
                item.report_nm,
                item.submitter,
                _iso(item.rcept_dt),
                item.source_url,
                item.pblntf_ty,
                item.pblntf_detail_ty,
            ),
        )
        if cur.rowcount > 0:
            stats.inserted += 1
        else:
            stats.duplicates += 1
    return stats


def record_run(
    conn: sqlite3.Connection,
    *,
    source: str,
    started_at: datetime,
    finished_at: datetime,
    ok: bool,
    fetched: int,
    inserted: int,
    duplicates: int,
    error: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO collector_runs
          (source, started_at, finished_at, ok, fetched, inserted, duplicates, error)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source,
            _iso(started_at),
            _iso(finished_at),
            1 if ok else 0,
            fetched,
            inserted,
            duplicates,
            error,
        ),
    )
