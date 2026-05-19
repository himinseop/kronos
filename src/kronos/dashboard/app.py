"""Streamlit 대시보드 — Phase 1-B 수집 모니터링."""

from __future__ import annotations

import altair as alt
import streamlit as st

from kronos.config import get_settings
from kronos.dashboard import queries as q

st.set_page_config(page_title="Kronos · 수집 모니터링", layout="wide")

settings = get_settings()
DB_PATH = settings.data_dir / "kronos.db"

if not DB_PATH.exists():
    st.error(f"DB 파일이 없습니다: {DB_PATH}\n\n먼저 `uv run kronos collect dart`를 실행해 주세요.")
    st.stop()

conn = q.open_db(DB_PATH)

st.title("Kronos · 수집 모니터링")
st.caption(f"DB: `{DB_PATH}`")

tab_overview, tab_health, tab_feed, tab_disc_types, tab_quality, tab_viewer = st.tabs(
    ["개요", "소스 헬스", "최근 피드", "공시 유형", "중복·매칭 품질", "원본 뷰어"]
)

# ───────── 개요 ─────────
with tab_overview:
    st.subheader("오늘 수집 합계")
    totals = q.totals_today(conn)
    if totals.empty:
        st.info("오늘 수집된 데이터가 없습니다.")
    else:
        cols = st.columns(len(totals))
        for col, (_, row) in zip(cols, totals.iterrows(), strict=False):
            col.metric(row["source"], int(row["n"]))

    st.subheader("시간대별 수집 추세 (최근 24시간)")
    hourly = q.collected_counts_by_hour(conn, hours=24)
    if hourly.empty:
        st.info("최근 24시간 데이터가 없습니다.")
    else:
        chart = (
            alt.Chart(hourly)
            .mark_bar()
            .encode(
                x=alt.X("hour:N", title="시각 (UTC)"),
                y=alt.Y("n:Q", title="건수"),
                color="source:N",
                tooltip=["hour", "source", "n"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)

# ───────── 소스 헬스 ─────────
with tab_health:
    st.subheader("소스별 최근 실행 상태 (24h)")
    health = q.source_health(conn)
    if health.empty:
        st.info("최근 실행 기록이 없습니다.")
    else:
        st.dataframe(health, use_container_width=True, hide_index=True)

    st.subheader("최근 실행 로그")
    runs = q.recent_runs(conn, limit=30)
    if runs.empty:
        st.info("실행 로그가 없습니다.")
    else:
        st.dataframe(runs, use_container_width=True, hide_index=True)

# ───────── 최근 피드 ─────────
with tab_feed:
    st.subheader("최근 뉴스·공시 피드")
    c1, c2, c3, c4 = st.columns([2, 2, 3, 1])
    with c1:
        sources = st.multiselect(
            "소스",
            options=["dart", "naver", "rss"],
            default=["dart", "naver", "rss"],
        )
    with c2:
        ticker = st.text_input("종목코드 필터", placeholder="예: 005930")
    with c3:
        keyword = st.text_input("키워드 (제목/본문)", placeholder="예: 자사주")
    with c4:
        limit = st.number_input("표시 건수", min_value=10, max_value=1000, value=200, step=10)

    feed = q.recent_feed(
        conn,
        sources=sources or None,
        ticker=ticker.strip() or None,
        keyword=keyword.strip() or None,
        limit=int(limit),
    )
    if feed.empty:
        st.info("조건에 맞는 결과가 없습니다.")
    else:
        st.caption(f"{len(feed):,}건")
        st.dataframe(
            feed,
            use_container_width=True,
            hide_index=True,
            column_config={"url": st.column_config.LinkColumn("url")},
        )

# ───────── 공시 유형 분포 ─────────
with tab_disc_types:
    st.subheader("DART 공시 유형 분포")
    days = st.slider("기간 (일)", min_value=1, max_value=30, value=7)
    dist = q.disclosure_type_distribution(conn, days=days)
    if dist.empty:
        st.info("최근 공시 데이터가 없습니다.")
    else:
        chart = (
            alt.Chart(dist)
            .mark_bar()
            .encode(
                x=alt.X("pblntf_ty:N", sort="-y", title="공시 유형 코드"),
                y=alt.Y("n:Q", title="건수"),
                tooltip=["pblntf_ty", "n"],
            )
            .properties(height=300)
        )
        st.altair_chart(chart, use_container_width=True)
        st.dataframe(dist, use_container_width=True, hide_index=True)

# ───────── 중복·매칭 품질 ─────────
with tab_quality:
    st.subheader("품질 지표")
    metrics = q.quality_metrics(conn)
    c1, c2, c3 = st.columns(3)
    c1.metric("news 총건수", f"{metrics['news_total']:,}")
    c2.metric("종목 매칭률", f"{metrics['news_match_rate']:.1%}")
    c3.metric("수집 중복률", f"{metrics['fetch_dedup_rate']:.1%}")

    st.subheader("매칭 실패 샘플 (최근)")
    samples = q.unmatched_samples(conn, limit=30)
    if samples.empty:
        st.info("매칭 실패 뉴스가 없습니다.")
    else:
        st.dataframe(samples, use_container_width=True, hide_index=True)

# ───────── 원본 뷰어 ─────────
with tab_viewer:
    st.subheader("뉴스 원본")
    news_id = st.number_input("news.id", min_value=1, step=1)
    if st.button("조회", key="load_news"):
        item = q.get_news_by_id(conn, int(news_id))
        if item is None:
            st.warning("해당 id의 뉴스가 없습니다.")
        else:
            st.json(item)

    st.subheader("공시 원본")
    rcept_no = st.text_input("rcept_no", placeholder="예: 20260519000001")
    if st.button("조회", key="load_disc") and rcept_no:
        item = q.get_disclosure(conn, rcept_no.strip())
        if item is None:
            st.warning("해당 접수번호의 공시가 없습니다.")
        else:
            st.json(item)
