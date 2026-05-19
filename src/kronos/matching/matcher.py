from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(slots=True)
class TickerEntry:
    ticker: str
    name: str  # 매칭에 사용된 이름(또는 별칭)


def _load_entries(conn: sqlite3.Connection) -> list[TickerEntry]:
    rows = conn.execute("SELECT ticker, corp_name FROM tickers").fetchall()
    aliases = conn.execute("SELECT alias, ticker FROM ticker_aliases").fetchall()
    entries = [TickerEntry(ticker=r[0], name=r[1]) for r in rows]
    entries.extend(TickerEntry(ticker=r[1], name=r[0]) for r in aliases)
    # 긴 이름부터 검색 (부분문자열 충돌 회피: "삼성전자" 가 "삼성"보다 먼저)
    entries.sort(key=lambda e: len(e.name), reverse=True)
    return entries


class TickerMatcher:
    """SQLite의 tickers + ticker_aliases를 메모리에 올려놓고 본문 매칭."""

    def __init__(self, conn: sqlite3.Connection):
        self._entries = _load_entries(conn)

    def match(self, text: str | None) -> str | None:
        """첫 번째로 발견된(가장 긴) 종목명/별칭의 ticker를 반환. 없으면 None."""
        if not text:
            return None
        for entry in self._entries:
            if entry.name and entry.name in text:
                return entry.ticker
        return None

    def match_all(self, text: str | None) -> list[str]:
        """본문에 등장한 모든 종목코드를 등장 순서대로 (중복 제거) 반환."""
        if not text:
            return []
        seen: list[str] = []
        for entry in self._entries:
            if entry.name and entry.name in text and entry.ticker not in seen:
                seen.append(entry.ticker)
        return seen
