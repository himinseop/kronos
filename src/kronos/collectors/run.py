from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

from kronos.collectors import dart, naver
from kronos.logging_setup import get_logger
from kronos.storage.db import connect, transaction
from kronos.storage.repository import (
    InsertStats,
    insert_disclosures,
    insert_news,
    record_run,
)
from kronos.storage.schema import ensure_schema

log = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def collect_dart(db_path: Path, api_key: str, *, bgn_de: date, end_de: date) -> InsertStats:
    """DART 공시를 조회해 SQLite에 적재."""
    conn = connect(db_path)
    ensure_schema(conn)

    started = _utcnow()
    stats = InsertStats()
    error: str | None = None
    ok = True

    log.info("dart.collect.start", bgn_de=bgn_de.isoformat(), end_de=end_de.isoformat())
    try:
        with transaction(conn):
            for batch_idx, item in enumerate(
                dart.iter_disclosures(api_key, bgn_de=bgn_de, end_de=end_de), start=1
            ):
                s = insert_disclosures(conn, [item])
                stats.fetched += s.fetched
                stats.inserted += s.inserted
                stats.duplicates += s.duplicates
                if batch_idx % 100 == 0:
                    log.info("dart.collect.progress", fetched=stats.fetched)
    except Exception as exc:
        ok = False
        error = repr(exc)
        log.error("dart.collect.failed", error=error)
    finally:
        finished = _utcnow()
        with transaction(conn):
            record_run(
                conn,
                source="dart",
                started_at=started,
                finished_at=finished,
                ok=ok,
                fetched=stats.fetched,
                inserted=stats.inserted,
                duplicates=stats.duplicates,
                error=error,
            )
        conn.close()

    log.info(
        "dart.collect.done",
        ok=ok,
        fetched=stats.fetched,
        inserted=stats.inserted,
        duplicates=stats.duplicates,
    )
    if not ok:
        assert error is not None
        raise RuntimeError(error)
    return stats


def collect_naver(
    db_path: Path,
    client_id: str,
    client_secret: str,
    queries: Iterable[str],
    *,
    display: int = 100,
) -> InsertStats:
    """네이버 뉴스 검색 API로 키워드별 결과를 가져와 news 테이블에 적재."""
    conn = connect(db_path)
    ensure_schema(conn)

    started = _utcnow()
    stats = InsertStats()
    error: str | None = None
    ok = True

    queries = list(queries)
    log.info("naver.collect.start", n_queries=len(queries))
    try:
        with transaction(conn):
            for q in queries:
                articles = naver.search(client_id, client_secret, q, display=display)
                s = insert_news(conn, articles)
                stats.fetched += s.fetched
                stats.inserted += s.inserted
                stats.duplicates += s.duplicates
                log.info(
                    "naver.collect.query",
                    query=q,
                    fetched=s.fetched,
                    inserted=s.inserted,
                    duplicates=s.duplicates,
                )
    except Exception as exc:
        ok = False
        error = repr(exc)
        log.error("naver.collect.failed", error=error)
    finally:
        finished = _utcnow()
        with transaction(conn):
            record_run(
                conn,
                source="naver",
                started_at=started,
                finished_at=finished,
                ok=ok,
                fetched=stats.fetched,
                inserted=stats.inserted,
                duplicates=stats.duplicates,
                error=error,
            )
        conn.close()

    log.info(
        "naver.collect.done",
        ok=ok,
        fetched=stats.fetched,
        inserted=stats.inserted,
        duplicates=stats.duplicates,
    )
    if not ok:
        assert error is not None
        raise RuntimeError(error)
    return stats
