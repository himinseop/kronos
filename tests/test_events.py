from __future__ import annotations

from datetime import UTC, datetime, timedelta

from kronos.dashboard.events import classify_event, recent_events
from kronos.storage.db import connect, transaction
from kronos.storage.models import Disclosure, NewsArticle
from kronos.storage.repository import insert_disclosures, insert_news
from kronos.storage.schema import ensure_schema


def test_classify_event_buyback():
    hit = classify_event("주요사항보고서(자기주식취득결정)")
    assert hit is not None
    assert hit.event_code == "buyback"
    assert hit.direction == "+"


def test_classify_event_dilution():
    hit = classify_event("[기재정정]주요사항보고서(유상증자결정)")
    assert hit is not None
    assert hit.event_code == "paid_rights"
    assert hit.direction == "-"


def test_classify_event_split():
    assert classify_event("주식분할결정").event_code == "stock_split"


def test_classify_event_no_match():
    assert classify_event("그냥 일반 보고서") is None
    assert classify_event(None) is None


def test_classify_event_supply_contract():
    hit = classify_event("단일판매ㆍ공급계약체결")
    assert hit is not None
    assert hit.event_code == "supply"
    assert hit.direction == "+"


def test_recent_events_filters_by_window_and_direction(tmp_path):
    conn = connect(tmp_path / "test.db")
    ensure_schema(conn)
    now = datetime.now(UTC)

    with transaction(conn):
        insert_disclosures(
            conn,
            [
                Disclosure(
                    rcept_no="20260601000001",
                    report_nm="주요사항보고서(자기주식취득결정)",
                    rcept_dt=now - timedelta(hours=1),
                    ticker="005930",
                    corp_name="삼성전자",
                ),
                Disclosure(
                    rcept_no="20260601000002",
                    report_nm="주요사항보고서(유상증자결정)",
                    rcept_dt=now - timedelta(hours=2),
                    ticker="000660",
                    corp_name="에스케이하이닉스",
                ),
                Disclosure(
                    rcept_no="20260520000001",
                    report_nm="주요사항보고서(자기주식취득결정)",
                    rcept_dt=now - timedelta(days=20),
                    ticker="035720",
                    corp_name="카카오",
                ),
            ],
        )
        insert_news(
            conn,
            [
                NewsArticle(
                    source="naver",
                    title="삼성전자 단일판매ㆍ공급계약체결",
                    published_at=now - timedelta(hours=3),
                    ticker="005930",
                ),
            ],
        )

    # 24시간 윈도우는 최근 3건만 잡힘 (20일 전 1건 제외)
    df = recent_events(conn, hours=24)
    assert len(df) == 3
    assert set(df["event_code"]) == {"buyback", "paid_rights", "supply"}

    # 긍정만
    df_pos = recent_events(conn, hours=24, direction="+")
    assert len(df_pos) == 2  # 자사주매입 + 공급계약
    assert set(df_pos["event_code"]) == {"buyback", "supply"}

    # 종목 필터
    df_sec = recent_events(conn, hours=24, ticker="005930")
    assert len(df_sec) == 2
