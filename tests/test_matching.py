from __future__ import annotations

from kronos.matching.matcher import TickerMatcher
from kronos.matching.tickers_sync import parse_corpcode
from kronos.storage.db import transaction

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


def _seed_tickers(conn):
    with transaction(conn), conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO tickers (ticker, corp_code, corp_name) VALUES (%s, %s, %s)",
            [
                ("005930", "00126380", "삼성전자"),
                ("000660", "00164779", "에스케이하이닉스"),
            ],
        )
        cur.executemany(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (%s, %s)",
            [
                ("삼전", "005930"),
                ("SK하이닉스", "000660"),
            ],
        )
    return conn


def test_matcher_finds_corp_name(db_conn):
    matcher = TickerMatcher(_seed_tickers(db_conn))
    assert matcher.match("오늘 삼성전자 호실적 발표") == "005930"


def test_matcher_finds_alias(db_conn):
    matcher = TickerMatcher(_seed_tickers(db_conn))
    assert matcher.match("삼전 매수 추천") == "005930"
    assert matcher.match("SK하이닉스 신고가") == "000660"


def test_matcher_prefers_longest_name(db_conn):
    _seed_tickers(db_conn)
    with transaction(db_conn):
        db_conn.execute(
            "INSERT INTO ticker_aliases (alias, ticker) VALUES (%s, %s)",
            ("삼성", "005930"),
        )
    matcher = TickerMatcher(db_conn)
    # '삼성전자'(긴 이름)가 '삼성'(짧은 별칭)보다 우선
    assert matcher.match("삼성전자 발표") == "005930"


def test_matcher_returns_none_when_no_match(db_conn):
    matcher = TickerMatcher(_seed_tickers(db_conn))
    assert matcher.match("관련 종목 없는 일반 기사") is None
    assert matcher.match(None) is None


def test_match_all_returns_multiple_in_order(db_conn):
    matcher = TickerMatcher(_seed_tickers(db_conn))
    result = matcher.match_all("삼성전자와 에스케이하이닉스가 동반 상승")
    assert set(result) == {"005930", "000660"}
