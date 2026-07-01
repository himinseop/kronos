"""기존 disclosures 행에 pblntf_ty를 룰 기반으로 채우는 백필."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.collectors.dart import infer_pblntf_ty
from kronos.logging_setup import get_logger
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

log = get_logger(__name__)


@dataclass(slots=True)
class ReclassifyStats:
    scanned: int = 0
    updated: int = 0
    distribution: dict[str, int] | None = None


def reclassify_disclosures(*, only_null: bool = True, dsn: str | None = None) -> ReclassifyStats:
    conn = connect(dsn)
    ensure_schema(conn)

    where = "WHERE pblntf_ty IS NULL" if only_null else ""
    rows = conn.execute(f"SELECT rcept_no, report_nm FROM disclosures {where}").fetchall()

    dist: dict[str, int] = {}
    stats = ReclassifyStats(distribution=dist)

    with transaction(conn):
        for row in rows:
            stats.scanned += 1
            code = infer_pblntf_ty(row["report_nm"])
            if code is None:
                continue
            dist[code] = dist.get(code, 0) + 1
            conn.execute(
                "UPDATE disclosures SET pblntf_ty = %s WHERE rcept_no = %s",
                (code, row["rcept_no"]),
            )
            stats.updated += 1

    conn.close()
    log.info("disclosures.reclassify.done", scanned=stats.scanned, updated=stats.updated)
    return stats
