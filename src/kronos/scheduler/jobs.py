from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from kronos.collectors.rss import DEFAULT_FEEDS
from kronos.collectors.run import collect_dart, collect_naver, collect_rss
from kronos.logging_setup import get_logger

KST = ZoneInfo("Asia/Seoul")
log = get_logger(__name__)


@dataclass(slots=True)
class JobConfig:
    dart_api_key: str | None
    naver_client_id: str | None
    naver_client_secret: str | None
    naver_queries: list[str] = field(default_factory=list)
    rss_feeds: list[str] = field(default_factory=lambda: list(DEFAULT_FEEDS))
    dart_interval_seconds: int = 30
    news_interval_seconds: int = 300  # 5분
    dsn: str | None = None  # None이면 설정(DATABASE_URL) 사용


def _safe(name: str, fn, *args, **kwargs):
    """잡 실행 중 예외가 다른 잡에 영향 가지 않도록 격리 + 로그."""
    try:
        fn(*args, **kwargs)
    except Exception as exc:
        log.error("job.failed", name=name, error=repr(exc))


def _run_dart(cfg: JobConfig):
    if not cfg.dart_api_key:
        return
    today = date.today()
    collect_dart(cfg.dart_api_key, bgn_de=today, end_de=today, dsn=cfg.dsn)


def _run_naver(cfg: JobConfig):
    if not (cfg.naver_client_id and cfg.naver_client_secret and cfg.naver_queries):
        return
    collect_naver(
        cfg.naver_client_id,
        cfg.naver_client_secret,
        cfg.naver_queries,
        display=30,
        dsn=cfg.dsn,
    )


def _run_rss(cfg: JobConfig):
    if not cfg.rss_feeds:
        return
    collect_rss(cfg.rss_feeds, dsn=cfg.dsn)


def build_scheduler(cfg: JobConfig) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=KST)

    # DART: 짧은 주기. 장중·장후 모두 동일 주기 (24h 공시 발생 가능).
    scheduler.add_job(
        _safe,
        IntervalTrigger(seconds=cfg.dart_interval_seconds, timezone=KST),
        id="dart_poll",
        args=("dart_poll", _run_dart, cfg),
        next_run_time=datetime.now(KST),  # 시작 즉시 1회
        coalesce=True,
        max_instances=1,
    )

    # 네이버 뉴스: 5분 주기
    scheduler.add_job(
        _safe,
        IntervalTrigger(seconds=cfg.news_interval_seconds, timezone=KST),
        id="naver_poll",
        args=("naver_poll", _run_naver, cfg),
        next_run_time=datetime.now(KST),
        coalesce=True,
        max_instances=1,
    )

    # RSS: 5분 주기
    scheduler.add_job(
        _safe,
        IntervalTrigger(seconds=cfg.news_interval_seconds, timezone=KST),
        id="rss_poll",
        args=("rss_poll", _run_rss, cfg),
        next_run_time=datetime.now(KST),
        coalesce=True,
        max_instances=1,
    )

    # ticker 사전 일 1회 갱신 (KST 06:00, DART 신규 상장 반영)
    # 현재는 구체적 잡 미구성 — Phase 1.5에서 추가 예정
    _ = CronTrigger  # 사용처 표시용

    return scheduler
