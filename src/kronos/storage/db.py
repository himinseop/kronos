from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

from kronos.config import get_settings


def connect(dsn: str | None = None) -> psycopg.Connection:
    """PostgreSQL 연결. dsn 미지정 시 설정(DATABASE_URL) 사용.

    row_factory=dict_row → 결과 행을 dict로 반환(row["col"]).
    autocommit=True → 단발 read/write는 즉시 커밋, 명시적 트랜잭션은 transaction() 사용.
    """
    dsn = dsn or get_settings().database_url
    return psycopg.connect(dsn, row_factory=dict_row, autocommit=True)


@contextmanager
def transaction(conn: psycopg.Connection) -> Iterator[psycopg.Connection]:
    """명시적 트랜잭션 블록. 예외 시 롤백, 정상 시 커밋."""
    with conn.transaction():
        yield conn
