"""Streamlit 대시보드 — Phase 1-B 수집 모니터링."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from kronos.config import get_settings
from kronos.dashboard import events as ev
from kronos.dashboard import queries as q
from kronos.dashboard import sentiment_view as sv
from kronos.dashboard import ticker_view as tv

st.set_page_config(page_title="Kronos · 수집 모니터링", layout="wide")

settings = get_settings()
DB_PATH = settings.data_dir / "kronos.db"

if not DB_PATH.exists():
    st.error(f"DB 파일이 없습니다: {DB_PATH}\n\n먼저 `uv run kronos collect dart`를 실행해 주세요.")
    st.stop()

conn = q.open_db(DB_PATH)

st.title("Kronos · 수집 모니터링")
st.caption(f"DB: `{DB_PATH}`")

(
    tab_overview,
    tab_sentiment,
    tab_events,
    tab_ticker,
    tab_health,
    tab_feed,
    tab_disc_types,
    tab_quality,
    tab_viewer,
) = st.tabs(
    [
        "개요",
        "감성",
        "이벤트 트리거",
        "종목 페이지",
        "소스 헬스",
        "최근 피드",
        "공시 유형",
        "중복·매칭 품질",
        "원본 뷰어",
    ]
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

# ───────── 감성 ─────────
with tab_sentiment:
    st.subheader("감성 분석 (KR-FinBERT)")
    cov = sv.coverage(conn)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("분석 완료", f"{cov['scored']:,}")
    m2.metric("미분석", f"{cov['pending']:,}")
    m3.metric("커버리지", f"{cov['coverage']:.1%}")
    m4.metric("뉴스 총계", f"{cov['news_total']:,}")

    sc1, sc2 = st.columns([1, 1])
    with sc1:
        s_days = st.slider("기간 (일)", 1, 30, 7, key="s_days")
    with sc2:
        s_ticker = st.text_input("종목코드 (추세용, 선택)", placeholder="005930", key="s_ticker")

    dist = sv.label_distribution(conn, days=int(s_days))
    if dist.empty:
        st.info("해당 기간 감성 데이터가 없습니다.")
    else:
        dcol, tcol = st.columns([1, 2])
        with dcol:
            st.markdown("**라벨 분포**")
            chart = (
                alt.Chart(dist)
                .mark_arc()
                .encode(
                    theta="n:Q",
                    color=alt.Color(
                        "label:N",
                        scale=alt.Scale(
                            domain=["positive", "neutral", "negative"],
                            range=["#22c55e", "#94a3b8", "#ef4444"],
                        ),
                    ),
                    tooltip=["label", "n"],
                )
                .properties(height=240)
            )
            st.altair_chart(chart, use_container_width=True)
        with tcol:
            st.markdown("**일별 평균 감성 추세**" + (f" — {s_ticker}" if s_ticker else " (전체)"))
            trend = sv.daily_sentiment_trend(
                conn, ticker=s_ticker.strip() or None, days=int(s_days)
            )
            if trend.empty:
                st.info("추세 데이터 없음")
            else:
                line = (
                    alt.Chart(trend)
                    .mark_line(point=True)
                    .encode(
                        x=alt.X("day:T", title="날짜"),
                        y=alt.Y("avg_score:Q", title="평균 감성", scale=alt.Scale(domain=[-1, 1])),
                        tooltip=["day", "avg_score", "n"],
                    )
                    .properties(height=240)
                )
                zero = (
                    alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color="#cbd5e1").encode(y="y:Q")
                )
                st.altair_chart(zero + line, use_container_width=True)

    st.divider()
    tp, tn = st.columns(2)
    with tp:
        st.markdown("**긍정 상위 종목 (최근 3일)**")
        pos = sv.top_by_sentiment(conn, positive=True, days=3)
        if pos.empty:
            st.caption("데이터 부족")
        else:
            st.dataframe(pos, use_container_width=True, hide_index=True)
    with tn:
        st.markdown("**부정 상위 종목 (최근 3일)**")
        neg = sv.top_by_sentiment(conn, positive=False, days=3)
        if neg.empty:
            st.caption("데이터 부족")
        else:
            st.dataframe(neg, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**감성 점수가 붙은 최근 뉴스**")
    fc1, fc2 = st.columns([1, 1])
    with fc1:
        f_label = st.selectbox(
            "라벨", options=["전체", "positive", "negative", "neutral"], key="s_flabel"
        )
    with fc2:
        f_ticker = st.text_input("종목코드", placeholder="005930", key="s_fticker")
    feed = sv.recent_scored_feed(
        conn,
        label=None if f_label == "전체" else f_label,
        ticker=f_ticker.strip() or None,
        limit=200,
    )
    if feed.empty:
        st.info("조건에 맞는 결과가 없습니다.")
    else:
        st.dataframe(
            feed,
            use_container_width=True,
            hide_index=True,
            column_config={"url": st.column_config.LinkColumn("url")},
        )

# ───────── 이벤트 트리거 ─────────
with tab_events:
    st.subheader("이벤트 트리거 (룰 기반)")
    st.caption(
        "제목·공시명 키워드 매칭으로 시장 영향이 큰 이벤트를 즉시 노출. "
        "방향(+/-/?)은 보수적 추정이며 맥락에 따라 다를 수 있음."
    )

    ec1, ec2, ec3, ec4 = st.columns([1, 2, 2, 1])
    with ec1:
        ev_hours = st.number_input(
            "기간 (시간)", min_value=1, max_value=24 * 30, value=24, step=1, key="ev_hours"
        )
    with ec2:
        ev_direction = st.selectbox(
            "방향",
            options=[("전체", None), ("긍정 +", "+"), ("부정 -", "-"), ("중립/혼합 ?", "?")],
            format_func=lambda x: x[0],
            index=0,
            key="ev_dir",
        )
    with ec3:
        ev_choices = ev.event_codes_available()
        ev_picked = st.multiselect(
            "이벤트 종류 (미선택=전체)",
            options=[c for c, _ in ev_choices],
            format_func=lambda c: dict(ev_choices).get(c, c),
            key="ev_picked",
        )
    with ec4:
        ev_ticker = st.text_input("종목코드", placeholder="005930", key="ev_ticker")

    summary = ev.event_summary(conn, hours=int(ev_hours))
    if not summary.empty:
        scol1, scol2 = st.columns([2, 3])
        with scol1:
            st.markdown("**이벤트 카테고리 분포**")
            st.dataframe(summary, use_container_width=True, hide_index=True)
        with scol2:
            chart = (
                alt.Chart(summary)
                .mark_bar()
                .encode(
                    x=alt.X("n:Q", title="건수"),
                    y=alt.Y("event_label:N", sort="-x", title=None),
                    color=alt.Color(
                        "direction:N",
                        scale=alt.Scale(
                            domain=["+", "-", "?"], range=["#22c55e", "#ef4444", "#94a3b8"]
                        ),
                        legend=alt.Legend(title="방향"),
                    ),
                    tooltip=["event_label", "direction", "n"],
                )
                .properties(height=300)
            )
            st.altair_chart(chart, use_container_width=True)

    events = ev.recent_events(
        conn,
        hours=int(ev_hours),
        direction=ev_direction[1] if ev_direction else None,
        event_codes=ev_picked or None,
        ticker=ev_ticker.strip() or None,
        limit=500,
    )
    if events.empty:
        st.info("조건에 맞는 이벤트가 없습니다.")
    else:
        st.caption(f"이벤트 매칭 {len(events):,}건")
        st.dataframe(
            events[
                [
                    "occurred_at",
                    "source",
                    "event_label",
                    "direction",
                    "ticker",
                    "entity",
                    "title",
                    "url",
                ]
            ],
            use_container_width=True,
            hide_index=True,
            column_config={"url": st.column_config.LinkColumn("url")},
        )

# ───────── 종목 페이지 ─────────
with tab_ticker:
    st.subheader("종목 페이지")
    tc1, tc2 = st.columns([3, 1])
    with tc1:
        tq = st.text_input(
            "종목 (종목코드 6자리 또는 회사명/별칭)",
            placeholder="005930 또는 삼성전자",
            key="tq",
        )
    with tc2:
        tdays = st.selectbox("기간", options=[30, 60, 90], index=0, key="tdays")

    if tq:
        ticker = tv.resolve_ticker(conn, tq)
        if ticker is None:
            st.warning(f"매칭되는 종목을 찾지 못했습니다: {tq}")
        else:
            profile = tv.get_profile(conn, ticker, days=int(tdays))
            tcA, tcB, tcC, tcD = st.columns(4)
            tcA.metric("종목", f"{profile.ticker}")
            tcB.metric("회사명", profile.corp_name or "-")
            tcC.metric(f"{tdays}일 뉴스", f"{profile.news_count_30d:,}")
            tcD.metric(f"{tdays}일 공시", f"{profile.disclosure_count_30d:,}")
            st.caption(
                f"최근 뉴스: {profile.last_news_at or '없음'} · "
                f"최근 공시: {profile.last_disclosure_at or '없음'}"
            )

            volume = tv.get_daily_volume(conn, ticker, days=int(tdays))
            if not volume.empty:
                chart = (
                    alt.Chart(volume)
                    .mark_bar()
                    .encode(
                        x=alt.X("day:T", title="날짜"),
                        y=alt.Y("n:Q", title="건수"),
                        color="source:N",
                        tooltip=["day", "source", "n"],
                    )
                    .properties(height=240)
                )
                st.altair_chart(chart, use_container_width=True)

            kw_col, tl_col = st.columns([1, 3])
            with kw_col:
                st.markdown("**자주 등장하는 단어**")
                kws = tv.top_keywords_in_titles(conn, ticker, days=int(tdays), top_n=15)
                if kws.empty:
                    st.info("데이터 부족")
                else:
                    st.dataframe(kws, use_container_width=True, hide_index=True)
            with tl_col:
                st.markdown("**통합 타임라인**")
                timeline = tv.get_timeline(conn, ticker, days=int(tdays))
                if timeline.empty:
                    st.info("해당 기간 데이터가 없습니다.")
                else:
                    st.dataframe(
                        timeline,
                        use_container_width=True,
                        hide_index=True,
                        column_config={"url": st.column_config.LinkColumn("url")},
                    )

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
