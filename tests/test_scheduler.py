from __future__ import annotations

from kronos.scheduler.jobs import JobConfig, build_scheduler


def test_build_scheduler_registers_all_jobs():
    cfg = JobConfig(
        dart_api_key="k",
        naver_client_id="i",
        naver_client_secret="s",
        naver_queries=["삼성전자"],
    )
    scheduler = build_scheduler(cfg)
    try:
        ids = {j.id for j in scheduler.get_jobs()}
        assert ids == {"dart_poll", "naver_poll", "rss_poll"}
    finally:
        if scheduler.running:
            scheduler.shutdown(wait=False)


def test_jobconfig_defaults():
    cfg = JobConfig(
        dart_api_key=None,
        naver_client_id=None,
        naver_client_secret=None,
    )
    assert cfg.dart_interval_seconds == 30
    assert cfg.news_interval_seconds == 300
    assert len(cfg.rss_feeds) >= 1
    assert cfg.dsn is None
