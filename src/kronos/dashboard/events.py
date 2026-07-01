"""이벤트 트리거: 제목/공시명 키워드 매칭 기반 분류.

NLP 없이도 시장 영향 큰 이벤트의 대부분을 즉시 식별한다.
Phase 2 감성분석 진입 후에도 1차 필터로 계속 활용.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import psycopg

from kronos.dashboard.queries import query_df

# (event_code, 표시 라벨, 매칭 키워드 튜플, 영향 방향 hint)
# direction은 보수적 추정. 실제 시장 반응은 맥락에 따라 달라짐.
EVENT_RULES: list[tuple[str, str, tuple[str, ...], str]] = [
    # 주주환원·자본거래
    ("buyback", "자사주매입", ("자기주식취득", "자사주매입", "자사주 매입", "자기주식 취득"), "+"),
    ("buyback_trust", "자사주신탁", ("자기주식취득신탁", "자기주식신탁계약"), "+"),
    (
        "dividend",
        "배당",
        ("배당금지급", "현금ㆍ현물배당결정", "현금·현물배당", "주식배당결정"),
        "+",
    ),
    ("stock_split", "액면분할", ("주식분할", "액면분할"), "+"),
    ("paid_rights", "유상증자", ("유상증자결정",), "-"),
    ("free_rights", "무상증자", ("무상증자결정",), "+"),
    ("cb_issue", "전환사채발행", ("전환사채권발행", "신주인수권부사채발행"), "-"),
    ("conversion", "전환가액조정", ("전환가액조정", "전환가격조정"), "-"),
    # 경영변경·지배구조
    ("merger", "합병", ("회사합병결정", "분할합병결정"), "?"),
    ("split", "분할", ("회사분할결정",), "?"),
    ("acquire_stake", "타법인주식취득", ("타법인주식및출자증권취득", "주식양수도계약"), "?"),
    ("biz_transfer", "영업양수도", ("영업양수결정", "영업양도결정", "자산양수도결정"), "?"),
    ("major_holder", "최대주주변경", ("최대주주변경", "최대주주등소유주식변동"), "?"),
    ("ceo_change", "대표이사변경", ("대표이사 변경", "대표이사변경", "주요경영진변경"), "?"),
    # 실적·계약
    ("earnings", "실적공시", ("결산실적공시(잠정)", "잠정실적", "영업실적", "매출실적"), "?"),
    ("supply", "공급계약", ("단일판매ㆍ공급계약", "단일판매·공급계약"), "+"),
    # 거래소 조치
    ("halt", "거래정지", ("거래정지", "매매거래정지"), "-"),
    ("warn", "투자주의/경고", ("투자주의", "투자경고", "투자위험"), "-"),
    ("watchlist", "관리종목", ("관리종목지정",), "-"),
    ("delist", "상장폐지", ("상장폐지",), "-"),
    ("query", "조회공시", ("조회공시요구", "조회공시"), "?"),
    # 감사·법적
    ("audit_bad", "감사의견 변동", ("감사의견거절", "한정", "부적정", "감사범위제한"), "-"),
    ("lawsuit", "소송", ("소송 제기", "소송제기", "소송등의제기", "판결"), "-"),
    ("default", "채무불이행", ("채무불이행", "부도", "기업회생", "법정관리", "워크아웃"), "-"),
]


@dataclass(slots=True)
class EventHit:
    event_code: str
    label: str
    direction: str


def classify_event(text: str | None) -> EventHit | None:
    """텍스트에 가장 먼저 매칭되는 이벤트를 반환. 없으면 None."""
    if not text:
        return None
    for code, label, keywords, direction in EVENT_RULES:
        for kw in keywords:
            if kw in text:
                return EventHit(event_code=code, label=label, direction=direction)
    return None


# SQL 조각: 모든 이벤트 키워드를 OR 조건으로 묶는다. 캐시.
def _build_keyword_filter(column: str) -> tuple[str, list[str]]:
    likes: list[str] = []
    params: list[str] = []
    for _, _, keywords, _ in EVENT_RULES:
        for kw in keywords:
            likes.append(f"{column} LIKE %s")
            params.append(f"%{kw}%")
    return "(" + " OR ".join(likes) + ")", params


def recent_events(
    conn: psycopg.Connection,
    *,
    hours: int = 24,
    direction: str | None = None,
    ticker: str | None = None,
    event_codes: list[str] | None = None,
    limit: int = 200,
) -> pd.DataFrame:
    """최근 N시간 내 이벤트 키워드가 매칭된 공시·뉴스 통합 목록."""
    disc_kw, disc_params = _build_keyword_filter("report_nm")
    news_kw, news_params = _build_keyword_filter("title")

    extra_disc, extra_disc_params = [], []
    extra_news, extra_news_params = [], []
    if ticker:
        extra_disc.append("ticker = %s")
        extra_disc_params.append(ticker)
        extra_news.append("ticker = %s")
        extra_news_params.append(ticker)

    disc_extra_sql = " AND ".join(extra_disc) if extra_disc else "TRUE"
    news_extra_sql = " AND ".join(extra_news) if extra_news else "TRUE"

    sql = f"""
    SELECT 'dart'      AS source,
           rcept_dt    AS occurred_at,
           ticker,
           corp_name   AS entity,
           report_nm   AS title,
           source_url  AS url
      FROM disclosures
     WHERE rcept_dt >= now() - make_interval(hours => %s)
       AND {disc_kw}
       AND {disc_extra_sql}
    UNION ALL
    SELECT source       AS source,
           published_at AS occurred_at,
           ticker,
           publisher    AS entity,
           title,
           url
      FROM news
     WHERE published_at >= now() - make_interval(hours => %s)
       AND {news_kw}
       AND {news_extra_sql}
     ORDER BY occurred_at DESC
     LIMIT %s
    """
    params: list = [
        hours,
        *disc_params,
        *extra_disc_params,
        hours,
        *news_params,
        *extra_news_params,
        limit,
    ]
    df = query_df(conn, sql, params)

    if df.empty:
        return df

    # 분류 라벨 부여
    hits = df["title"].map(classify_event)
    df["event_code"] = [h.event_code if h else None for h in hits]
    df["event_label"] = [h.label if h else None for h in hits]
    df["direction"] = [h.direction if h else None for h in hits]

    if event_codes:
        df = df[df["event_code"].isin(event_codes)]
    if direction in {"+", "-", "?"}:
        df = df[df["direction"] == direction]

    return df.reset_index(drop=True)


def event_summary(conn: psycopg.Connection, *, hours: int = 24) -> pd.DataFrame:
    """최근 N시간 이벤트 카테고리별 빈도."""
    df = recent_events(conn, hours=hours, limit=10000)
    if df.empty:
        return pd.DataFrame(columns=["event_label", "direction", "n"])
    g = (
        df.groupby(["event_label", "direction"], dropna=True)
        .size()
        .reset_index(name="n")
        .sort_values("n", ascending=False)
    )
    return g


def event_codes_available() -> list[tuple[str, str]]:
    """필터 UI용. (event_code, label) 리스트."""
    return [(code, label) for code, label, _, _ in EVENT_RULES]
