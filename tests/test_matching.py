from __future__ import annotations

from kronos.matching.matcher import TickerMatcher
from kronos.matching.tickers_sync import parse_corpcode
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<result>
  <list>
    <corp_code>00126380</corp_code>
    <corp_name>삼성전자</corp_name>
    <stock_code>005930</stock_code>
    <modify_date>20240101</modify_date>
  </list>
  <list>
    <corp_code>00164779</corp_code>
    <corp_name>에스케이하이닉스</corp_name>
    <stock_code>000660</stock_code>
    <modify_date>20240101</modify_date>
  </list>
  <list>
    <corp_code>99999999</corp_code>
    <corp_name>비상장사</corp_name>
    <stock_code></stock_code>
    <modify_date>20240101</modify_date>
  </list>
</result>
""".encode()


def test_parse_corpcode_filters_non_listed():
    rows = list(parse_corpcode(SAMPLE_XML))
    assert len(rows) == 2
    tickers = {r[0] for r in rows}
    assert tickers == {"005930", "000660"}


def _seed_tickers(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema(conn)
    with transaction(conn):
        conn.executemany(
            "INSERT INTO tickers (ticker, corp_code, corp_name) VALUES (?, ?, ?)",
            [
                ("005930", "00126380", "삼성전자"),
                ("000660", "00164779", "에스케이하이닉스"),
            ],
        )
        conn.executemany(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (?, ?)",
            [
                ("삼전", "005930"),
                ("SK하이닉스", "000660"),
            ],
        )
    return conn


def test_matcher_finds_corp_name(tmp_path):
    conn = _seed_tickers(tmp_path)
    matcher = TickerMatcher(conn)
    assert matcher.match("오늘 삼성전자 호실적 발표") == "005930"


def test_matcher_finds_alias(tmp_path):
    conn = _seed_tickers(tmp_path)
    matcher = TickerMatcher(conn)
    assert matcher.match("삼전 매수 추천") == "005930"
    assert matcher.match("SK하이닉스 신고가") == "000660"


def test_matcher_prefers_longest_name(tmp_path):
    conn = _seed_tickers(tmp_path)
    # 별칭에 '삼성' 같은 짧은 이름도 추가했다고 가정
    with transaction(conn):
        conn.execute(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (?, ?)",
            ("삼성", "005930"),
        )
    matcher = TickerMatcher(conn)
    # '삼성전자'(긴 이름)가 '삼성'(짧은 별칭)보다 우선
    assert matcher.match("삼성전자 발표") == "005930"


def test_matcher_returns_none_when_no_match(tmp_path):
    conn = _seed_tickers(tmp_path)
    matcher = TickerMatcher(conn)
    assert matcher.match("관련 종목 없는 일반 기사") is None
    assert matcher.match(None) is None


def test_match_all_returns_multiple_in_order(tmp_path):
    conn = _seed_tickers(tmp_path)
    matcher = TickerMatcher(conn)
    result = matcher.match_all("삼성전자와 에스케이하이닉스가 동반 상승")
    assert set(result) == {"005930", "000660"}
