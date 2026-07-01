"""감성 분석 워커: 미분석 news를 KR-FinBERT로 점수화해 sentiments 테이블에 적재."""

from __future__ import annotations

from dataclasses import dataclass

from kronos.analysis.sentiment import MODEL_ID, SentimentModel
from kronos.logging_setup import get_logger
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

log = get_logger(__name__)


@dataclass(slots=True)
class SentimentStats:
    scanned: int = 0
    scored: int = 0


def _fetch_unscored_news(conn, model_id: str, limit: int) -> list[tuple[int, str]]:
    rows = conn.execute(
        """
        SELECT n.id, n.title
          FROM news n
          LEFT JOIN sentiments s
            ON s.target_type = 'news'
           AND s.target_id = n.id::text
           AND s.model = %s
         WHERE s.id IS NULL
         ORDER BY n.id DESC
         LIMIT %s
        """,
        (model_id, limit),
    ).fetchall()
    return [(r["id"], r["title"]) for r in rows]


def analyze_news_sentiment(
    model: SentimentModel,
    *,
    model_id: str = MODEL_ID,
    limit: int = 1000,
    batch_size: int = 64,
    dsn: str | None = None,
) -> SentimentStats:
    """미분석 news를 최대 limit건 점수화. 한 번 호출 = 한 배치 사이클."""
    conn = connect(dsn)
    ensure_schema(conn)

    stats = SentimentStats()
    pending = _fetch_unscored_news(conn, model_id, limit)
    stats.scanned = len(pending)
    if not pending:
        conn.close()
        return stats

    log.info("sentiment.start", pending=len(pending), model=model_id)

    for i in range(0, len(pending), batch_size):
        chunk = pending[i : i + batch_size]
        texts = [title for _, title in chunk]
        results = model.predict(texts)
        with transaction(conn):
            for (news_id, _), res in zip(chunk, results, strict=True):
                conn.execute(
                    """
                    INSERT INTO sentiments
                      (target_type, target_id, model, score, label, confidence)
                    VALUES ('news', %s, %s, %s, %s, %s)
                    ON CONFLICT (target_type, target_id, model) DO NOTHING
                    """,
                    (str(news_id), model_id, res.score, res.label, res.confidence),
                )
                stats.scored += 1
        log.info("sentiment.batch", done=stats.scored, total=len(pending))

    conn.close()
    log.info("sentiment.done", scanned=stats.scanned, scored=stats.scored)
    return stats


def run_sentiment_forever(
    model: SentimentModel,
    *,
    interval_seconds: int = 300,
    batch_size: int = 64,
    limit_per_cycle: int = 2000,
    dsn: str | None = None,
) -> None:
    """sentiment 컨테이너 엔트리포인트. 미분석분을 주기적으로 처리, SIGTERM에서 종료."""
    import signal
    import threading

    stop = threading.Event()

    def _handle(signum, _frame):
        log.info("sentiment.signal", signum=signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    log.info("sentiment.loop.start", interval=interval_seconds)
    while not stop.is_set():
        drained_full = False
        try:
            stats = analyze_news_sentiment(
                model, limit=limit_per_cycle, batch_size=batch_size, dsn=dsn
            )
            # 한 사이클에서 상한만큼 처리했다면 백로그가 남았다는 뜻 → 즉시 다음 사이클
            drained_full = stats.scanned >= limit_per_cycle
        except Exception as exc:
            log.error("sentiment.loop.error", error=repr(exc))
        # 백로그 소진 중이면 짧게, 따라잡았으면 정규 주기로 대기
        stop.wait(timeout=2 if drained_full else interval_seconds)
    log.info("sentiment.loop.stopped")


def pending_count(*, model_id: str = MODEL_ID, dsn: str | None = None) -> int:
    conn = connect(dsn)
    ensure_schema(conn)
    row = conn.execute(
        """
        SELECT COUNT(*) AS n
          FROM news n
          LEFT JOIN sentiments s
            ON s.target_type = 'news'
           AND s.target_id = n.id::text
           AND s.model = %s
         WHERE s.id IS NULL
        """,
        (model_id,),
    ).fetchone()
    conn.close()
    return row["n"]
