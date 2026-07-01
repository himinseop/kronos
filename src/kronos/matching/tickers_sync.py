from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from xml.etree import ElementTree

import httpx
import psycopg

from kronos.logging_setup import get_logger
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

DART_CORPCODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"

# 자주 쓰이는 줄임말 / 별칭. 사용자가 알아내거나 늘릴 수 있도록 데이터로 분리.
DEFAULT_ALIASES: dict[str, str] = {
    "삼전": "005930",
    "삼성전자우": "005935",
    "SK하닉": "000660",
    "하이닉스": "000660",
    "LG엔솔": "373220",
    "엘앤에프": "066970",
    "현대차": "005380",
    "기아차": "000270",
}

log = get_logger(__name__)


@dataclass(slots=True)
class SyncStats:
    fetched: int = 0
    listed: int = 0
    inserted_or_updated: int = 0
    aliases_seeded: int = 0


def fetch_corpcode_xml(api_key: str, *, timeout: float = 30.0) -> bytes:
    """DART corpCode ZIP을 받아 내부 XML 바이트 반환."""
    resp = httpx.get(DART_CORPCODE_URL, params={"crtfc_key": api_key}, timeout=timeout)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = zf.namelist()
        if not names:
            raise RuntimeError("corpCode ZIP에 파일이 없습니다")
        with zf.open(names[0]) as f:
            return f.read()


def parse_corpcode(xml_bytes: bytes):
    """corpCode XML에서 상장사(stock_code 있음)만 (ticker, corp_code, corp_name) 추출."""
    root = ElementTree.fromstring(xml_bytes)
    for node in root.findall("list"):
        stock = (node.findtext("stock_code") or "").strip()
        if not stock:
            continue
        yield (
            stock,
            (node.findtext("corp_code") or "").strip() or None,
            (node.findtext("corp_name") or "").strip(),
        )


def sync_tickers(api_key: str, *, dsn: str | None = None) -> SyncStats:
    xml_bytes = fetch_corpcode_xml(api_key)
    conn = connect(dsn)
    ensure_schema(conn)

    stats = SyncStats(fetched=len(xml_bytes))

    with transaction(conn):
        for ticker, corp_code, corp_name in parse_corpcode(xml_bytes):
            stats.listed += 1
            cur = conn.execute(
                """
                INSERT INTO tickers (ticker, corp_code, corp_name, synced_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (ticker) DO UPDATE SET
                  corp_code = excluded.corp_code,
                  corp_name = excluded.corp_name,
                  synced_at = excluded.synced_at
                """,
                (ticker, corp_code, corp_name),
            )
            stats.inserted_or_updated += cur.rowcount

        for alias, ticker in DEFAULT_ALIASES.items():
            cur = conn.execute(
                """
                INSERT INTO ticker_aliases (alias, ticker)
                SELECT %s, %s WHERE EXISTS (SELECT 1 FROM tickers WHERE ticker = %s)
                ON CONFLICT (alias) DO NOTHING
                """,
                (alias, ticker, ticker),
            )
            stats.aliases_seeded += cur.rowcount

    conn.close()
    log.info(
        "tickers.sync.done",
        listed=stats.listed,
        inserted_or_updated=stats.inserted_or_updated,
        aliases_seeded=stats.aliases_seeded,
    )
    return stats


def db_has_tickers(conn: psycopg.Connection) -> bool:
    row = conn.execute("SELECT 1 FROM tickers LIMIT 1").fetchone()
    return row is not None
