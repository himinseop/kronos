"""테스트 공통 fixture.

DB 통합 테스트는 dockerized PostgreSQL의 별도 데이터베이스(kronos_test)를 사용한다.
PostgreSQL이 없으면 해당 테스트는 skip (순수 로직 테스트는 계속 실행).
"""

from __future__ import annotations

import psycopg
import pytest
from kronos.config import get_settings
from kronos.storage.schema import ensure_schema
from psycopg.rows import dict_row

_TABLES = "news, disclosures, collector_runs, sentiments, ticker_aliases, tickers"


def _dsn_parts() -> tuple[str, str]:
    """(admin_dsn, test_dsn) — 같은 서버의 postgres DB와 kronos_test DB."""
    base = get_settings().database_url
    head, _, _db = base.rpartition("/")
    return f"{head}/postgres", f"{head}/kronos_test"


@pytest.fixture(scope="session")
def test_dsn() -> str:
    admin, dsn = _dsn_parts()
    try:
        with psycopg.connect(admin, autocommit=True, connect_timeout=3) as c:
            exists = c.execute("SELECT 1 FROM pg_database WHERE datname = 'kronos_test'").fetchone()
            if not exists:
                c.execute("CREATE DATABASE kronos_test")
    except Exception as exc:
        pytest.skip(f"PostgreSQL 사용 불가 (DB 통합 테스트 skip): {exc}")
    with psycopg.connect(dsn, autocommit=True) as c:
        ensure_schema(c)
    return dsn


@pytest.fixture
def db_conn(test_dsn: str):
    """스키마 보장 + 전 테이블 TRUNCATE된 깨끗한 연결."""
    conn = psycopg.connect(test_dsn, row_factory=dict_row, autocommit=True)
    ensure_schema(conn)
    conn.execute(f"TRUNCATE {_TABLES} RESTART IDENTITY CASCADE")
    yield conn
    conn.close()
