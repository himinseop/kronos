"""복구된 SQLite(data/kronos.db) → PostgreSQL 일괄 이관.

사용:
    uv run python scripts/migrate_sqlite_to_pg.py [--sqlite data/kronos.db]

- SQLite의 ISO 텍스트 timestamp를 파싱해 timestamptz로 적재
- 전 테이블(tickers → 나머지 순서, FK 고려) 이관
- ON CONFLICT DO NOTHING으로 재실행 안전(idempotent)
- 이관 후 양쪽 건수 비교 출력
"""

from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from kronos.config import get_settings
from kronos.storage.schema import ensure_schema
from psycopg.rows import dict_row


def parse_ts(val: str | None) -> datetime | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    # SQLite 저장 포맷: 'YYYY-MM-DDTHH:MM:SS.ffffffZ' 또는 'YYYY-MM-DD HH:MM:SS'
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        # 'YYYY-MM-DD HH:MM:SS' 등
        dt = datetime.fromisoformat(s.replace(" ", "T"))
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# (테이블, 컬럼목록, timestamp컬럼집합, 충돌키)
TABLES = [
    (
        "tickers",
        ["ticker", "corp_code", "corp_name", "market", "synced_at"],
        {"synced_at"},
        "ticker",
    ),
    ("ticker_aliases", ["alias", "ticker"], set(), "alias"),
    (
        "news",
        [
            "id",
            "source",
            "ticker",
            "title",
            "body",
            "publisher",
            "url",
            "published_at",
            "hash",
            "collected_at",
        ],
        {"published_at", "collected_at"},
        "id",
    ),
    (
        "disclosures",
        [
            "rcept_no",
            "corp_code",
            "corp_name",
            "ticker",
            "report_nm",
            "submitter",
            "rcept_dt",
            "source_url",
            "pblntf_ty",
            "pblntf_detail_ty",
            "collected_at",
        ],
        {"rcept_dt", "collected_at"},
        "rcept_no",
    ),
    (
        "collector_runs",
        [
            "id",
            "source",
            "started_at",
            "finished_at",
            "ok",
            "fetched",
            "inserted",
            "duplicates",
            "error",
        ],
        {"started_at", "finished_at"},
        "id",
    ),
    (
        "sentiments",
        [
            "id",
            "target_type",
            "target_id",
            "model",
            "score",
            "label",
            "confidence",
            "category",
            "rationale",
            "analyzed_at",
        ],
        {"analyzed_at"},
        "id",
    ),
]

BOOL_COLS = {"ok"}


def migrate(sqlite_path: Path, pg_dsn: str, batch: int = 2000) -> None:
    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row
    pg = psycopg.connect(pg_dsn, row_factory=dict_row, autocommit=False)
    ensure_schema(pg)
    pg.commit()

    for table, cols, ts_cols, conflict in TABLES:
        try:
            total = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            print(f"  {table}: (SQLite에 없음, 건너뜀)")
            continue

        placeholders = ", ".join(["%s"] * len(cols))
        collist = ", ".join(cols)
        insert = (
            f"INSERT INTO {table} ({collist}) VALUES ({placeholders}) "
            f"ON CONFLICT ({conflict}) DO NOTHING"
        )

        migrated = 0
        cur = src.execute(f"SELECT {collist} FROM {table}")
        while True:
            rows = cur.fetchmany(batch)
            if not rows:
                break
            payload = []
            for r in rows:
                values = []
                for c in cols:
                    v = r[c]
                    if c in ts_cols:
                        v = parse_ts(v)
                    elif c in BOOL_COLS:
                        v = bool(v)
                    values.append(v)
                payload.append(values)
            with pg.cursor() as pc:
                pc.executemany(insert, payload)
            pg.commit()
            migrated += len(rows)
            print(f"  {table}: {migrated}/{total}", end="\r")
        print(f"  {table}: {migrated}/{total}  완료")

        # 시퀀스 보정 (id 기반 테이블)
        if "id" in cols:
            pg.execute(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
            pg.commit()

    # 검증
    print("\n=== 건수 검증 (SQLite → PG) ===")
    for table, _cols, _ts, _c in TABLES:
        try:
            s = src.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except sqlite3.OperationalError:
            continue
        p = pg.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        mark = "OK" if s == p else "DIFF"
        print(f"  {table:16s} {s:>8} → {p:>8}  [{mark}]")

    src.close()
    pg.close()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", default="data/kronos.db")
    ap.add_argument("--dsn", default=None, help="기본: 설정의 DATABASE_URL")
    args = ap.parse_args()

    dsn = args.dsn or get_settings().database_url
    print(f"SQLite: {args.sqlite}")
    print(f"PG DSN host: {dsn.rsplit('@', 1)[-1]}")
    migrate(Path(args.sqlite), dsn)


if __name__ == "__main__":
    main()
