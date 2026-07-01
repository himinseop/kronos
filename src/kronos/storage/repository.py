from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

import psycopg

from kronos.storage.hashing import article_hash
from kronos.storage.models import Disclosure, NewsArticle


def _aware(dt: datetime) -> datetime:
    """naive datetime은 UTC로 간주. psycopg가 timestamptz로 어댑트."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


@dataclass(slots=True)
class InsertStats:
    fetched: int = 0
    inserted: int = 0
    duplicates: int = 0


def insert_news(conn: psycopg.Connection, items: Iterable[NewsArticle]) -> InsertStats:
    stats = InsertStats()
    for item in items:
        stats.fetched += 1
        h = article_hash(item.title, item.url)
        cur = conn.execute(
            """
            INSERT INTO news
              (source, ticker, title, body, publisher, url, published_at, hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (hash) DO NOTHING
            """,
            (
                item.source,
                item.ticker,
                item.title,
                item.body,
                item.publisher,
                item.url,
                _aware(item.published_at),
                h,
            ),
        )
        if cur.rowcount > 0:
            stats.inserted += 1
        else:
            stats.duplicates += 1
    return stats


def insert_disclosures(conn: psycopg.Connection, items: Iterable[Disclosure]) -> InsertStats:
    stats = InsertStats()
    for item in items:
        stats.fetched += 1
        cur = conn.execute(
            """
            INSERT INTO disclosures
              (rcept_no, corp_code, corp_name, ticker, report_nm, submitter, rcept_dt,
               source_url, pblntf_ty, pblntf_detail_ty)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (rcept_no) DO NOTHING
            """,
            (
                item.rcept_no,
                item.corp_code,
                item.corp_name,
                item.ticker,
                item.report_nm,
                item.submitter,
                _aware(item.rcept_dt),
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
    conn: psycopg.Connection,
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            source,
            _aware(started_at),
            _aware(finished_at),
            ok,
            fetched,
            inserted,
            duplicates,
            error,
        ),
    )
