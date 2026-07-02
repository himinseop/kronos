"""카테고리 분류 워커: 종목 매칭된 미분류 news를 자체 LLM으로 분류해
sentiments 테이블(model='cat:...')에 category/rationale과 함께 적재.

감성분석 워커(run.py)와 동일한 구조·저장소를 재사용한다. sentiments
테이블은 UNIQUE(target_type, target_id, model)로 감성/카테고리를 model
값으로 구분한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from kronos.analysis.classify import CategoryModel, model_id_for
from kronos.logging_setup import get_logger
from kronos.storage.db import connect, transaction
from kronos.storage.schema import ensure_schema

log = get_logger(__name__)


@dataclass(slots=True)
class ClassifyStats:
    scanned: int = 0
    classified: int = 0


def _fetch_unclassified(conn, model_id: str, limit: int) -> list[tuple[int, str]]:
    """종목 매칭된(ticker IS NOT NULL) 미분류 뉴스를 최신순으로."""
    rows = conn.execute(
        """
        SELECT n.id, n.title
          FROM news n
          LEFT JOIN sentiments s
            ON s.target_type = 'news'
           AND s.target_id = n.id::text
           AND s.model = %s
         WHERE s.id IS NULL
           AND n.ticker IS NOT NULL
         ORDER BY n.id DESC
         LIMIT %s
        """,
        (model_id, limit),
    ).fetchall()
    return [(r["id"], r["title"]) for r in rows]


def classify_news(
    model: CategoryModel,
    *,
    model_name: str,
    limit: int = 1000,
    chunk_size: int = 15,
    dsn: str | None = None,
) -> ClassifyStats:
    """미분류 종목뉴스를 최대 limit건 분류. 한 번 호출 = 한 사이클."""
    model_id = model_id_for(model_name)
    conn = connect(dsn)
    ensure_schema(conn)

    stats = ClassifyStats()
    pending = _fetch_unclassified(conn, model_id, limit)
    stats.scanned = len(pending)
    if not pending:
        conn.close()
        return stats

    log.info("classify.start", pending=len(pending), model=model_id)

    # LLM 호출 단위(chunk)로 끊어 처리하고, 청크마다 커밋해 진행분을 보존
    for i in range(0, len(pending), chunk_size):
        chunk = pending[i : i + chunk_size]
        titles = [title for _, title in chunk]
        results = model.classify(titles)
        with transaction(conn):
            for (news_id, _), res in zip(chunk, results, strict=True):
                conn.execute(
                    """
                    INSERT INTO sentiments
                      (target_type, target_id, model, score, label,
                       confidence, category, rationale)
                    VALUES ('news', %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (target_type, target_id, model) DO NOTHING
                    """,
                    (
                        str(news_id),
                        model_id,
                        res.confidence,  # score 컬럼(NOT NULL)엔 confidence 저장
                        res.category,  # label 컬럼(NOT NULL)엔 category 저장
                        res.confidence,
                        res.category,
                        res.rationale,
                    ),
                )
                stats.classified += 1
        log.info("classify.batch", done=stats.classified, total=len(pending))

    conn.close()
    log.info("classify.done", scanned=stats.scanned, classified=stats.classified)
    return stats


def pending_classify_count(*, model_name: str, dsn: str | None = None) -> int:
    model_id = model_id_for(model_name)
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
           AND n.ticker IS NOT NULL
        """,
        (model_id,),
    ).fetchone()
    conn.close()
    return row["n"]


def run_classify_forever(
    model: CategoryModel,
    *,
    model_name: str,
    interval_seconds: int = 300,
    chunk_size: int = 15,
    limit_per_cycle: int = 1500,
    dsn: str | None = None,
) -> None:
    """분류 루프 엔트리포인트. 미분류분을 주기적으로 처리, SIGTERM에서 종료."""
    import signal
    import threading

    stop = threading.Event()

    def _handle(signum, _frame):
        log.info("classify.signal", signum=signum)
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    log.info("classify.loop.start", interval=interval_seconds, model=model_name)
    while not stop.is_set():
        drained_full = False
        try:
            stats = classify_news(
                model,
                model_name=model_name,
                limit=limit_per_cycle,
                chunk_size=chunk_size,
                dsn=dsn,
            )
            drained_full = stats.scanned >= limit_per_cycle
        except Exception as exc:
            log.error("classify.loop.error", error=repr(exc))
        stop.wait(timeout=2 if drained_full else interval_seconds)
    log.info("classify.loop.stopped")
