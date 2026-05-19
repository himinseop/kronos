from __future__ import annotations

import signal
import threading

from kronos.logging_setup import get_logger
from kronos.scheduler.jobs import JobConfig, build_scheduler

log = get_logger(__name__)


def run_forever(cfg: JobConfig) -> None:
    """포그라운드에서 스케줄러를 실행하고 SIGINT/SIGTERM에서 정상 종료."""
    stop_event = threading.Event()

    def _handle_signal(signum, _frame):
        log.info("scheduler.signal", signum=signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    scheduler = build_scheduler(cfg)
    scheduler.start()
    log.info(
        "scheduler.started",
        jobs=[j.id for j in scheduler.get_jobs()],
        dart_interval=cfg.dart_interval_seconds,
        news_interval=cfg.news_interval_seconds,
    )
    try:
        while not stop_event.is_set():
            stop_event.wait(timeout=1.0)
    finally:
        scheduler.shutdown(wait=True)
        log.info("scheduler.stopped")
