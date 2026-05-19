from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kronos.logging_setup import get_logger
from kronos.matching.matcher import TickerMatcher
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

log = get_logger(__name__)


@dataclass(slots=True)
class BackfillStats:
    scanned: int = 0
    updated: int = 0


def backfill_news_tickers(db_path: Path, *, only_null: bool = True) -> BackfillStats:
    """news.ticker가 NULL인 행을 대상으로 제목+본문 매칭 후 업데이트."""
    conn = connect(db_path)
    ensure_schema(conn)
    matcher = TickerMatcher(conn)
    stats = BackfillStats()

    where = "WHERE ticker IS NULL" if only_null else ""
    rows = conn.execute(f"SELECT id, title, body FROM news {where}").fetchall()

    with transaction(conn):
        for row in rows:
            stats.scanned += 1
            text = f"{row['title']} {row['body'] or ''}"
            ticker = matcher.match(text)
            if ticker is None:
                continue
            conn.execute("UPDATE news SET ticker = ? WHERE id = ?", (ticker, row["id"]))
            stats.updated += 1

    conn.close()
    log.info("backfill.news.done", scanned=stats.scanned, updated=stats.updated)
    return stats
