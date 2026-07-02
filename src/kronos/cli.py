from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from importlib.resources import files as _resource_files
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kronos import __version__
from kronos.collectors import dart, naver
from kronos.collectors.rss import DEFAULT_FEEDS
from kronos.collectors.run import collect_dart, collect_naver, collect_rss
from kronos.config import get_settings
from kronos.logging_setup import configure_logging
from kronos.matching.backfill import backfill_news_tickers
from kronos.matching.tickers_sync import sync_tickers
from kronos.scheduler.jobs import JobConfig
from kronos.scheduler.runner import run_forever

DEFAULT_NAVER_QUERIES = ("삼성전자", "SK하이닉스", "현대차", "LG에너지솔루션")

app = typer.Typer(add_completion=False, help="Kronos CLI")
collect_app = typer.Typer(help="데이터 수집 명령 (Phase 1)")
tickers_app = typer.Typer(help="종목 사전 관리")
match_app = typer.Typer(help="종목 매칭 백필")
disclosures_app = typer.Typer(help="공시 데이터 관리")
analyze_app = typer.Typer(help="분석 명령 (Phase 2)")
app.add_typer(collect_app, name="collect")
app.add_typer(tickers_app, name="tickers")
app.add_typer(match_app, name="match")
app.add_typer(disclosures_app, name="disclosures")
app.add_typer(analyze_app, name="analyze")
console = Console()


@app.callback()
def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)


@app.command()
def version() -> None:
    """현재 버전 출력."""
    console.print(f"kronos {__version__}")


@app.command()
def status() -> None:
    """외부 API 연결 점검 (Phase 0 범위: DART · 네이버)."""
    settings = get_settings()

    table = Table(title="External API Status")
    table.add_column("Source")
    table.add_column("Configured")
    table.add_column("Result")
    table.add_column("Detail", overflow="fold")

    overall_ok = True

    # DART
    if settings.dart_api_key is None:
        table.add_row("DART", "[red]no[/red]", "-", "DART_API_KEY 미설정")
        overall_ok = False
    else:
        result = dart.ping(settings.dart_api_key.get_secret_value())
        mark = "[green]OK[/green]" if result.ok else "[red]FAIL[/red]"
        detail = f"status={result.dart_status} {result.message}".strip()
        table.add_row("DART", "yes", mark, detail)
        if not result.ok:
            overall_ok = False

    # Naver
    if settings.naver_client_id is None or settings.naver_client_secret is None:
        table.add_row("Naver", "[red]no[/red]", "-", "NAVER_CLIENT_ID/SECRET 미설정")
        overall_ok = False
    else:
        result = naver.ping(
            settings.naver_client_id.get_secret_value(),
            settings.naver_client_secret.get_secret_value(),
        )
        mark = "[green]OK[/green]" if result.ok else "[red]FAIL[/red]"
        table.add_row("Naver", "yes", mark, result.message)
        if not result.ok:
            overall_ok = False

    console.print(table)

    if not overall_ok:
        raise typer.Exit(code=1)


@collect_app.command("dart")
def collect_dart_cmd(
    days: int = typer.Option(0, help="오늘로부터 며칠 전까지 수집할지 (0이면 당일만)"),
    bgn: str | None = typer.Option(None, help="시작일 YYYY-MM-DD (지정 시 --days 무시)"),
    end: str | None = typer.Option(None, help="종료일 YYYY-MM-DD"),
) -> None:
    """DART 공시를 수집해 SQLite에 적재."""
    settings = get_settings()
    if settings.dart_api_key is None:
        console.print("[red]DART_API_KEY 미설정. .env를 확인하세요.[/red]")
        raise typer.Exit(code=1)

    if bgn or end:
        bgn_de = date.fromisoformat(bgn) if bgn else date.today()
        end_de = date.fromisoformat(end) if end else date.today()
    else:
        end_de = date.today()
        bgn_de = end_de - timedelta(days=days)

    stats = collect_dart(
        settings.dart_api_key.get_secret_value(),
        bgn_de=bgn_de,
        end_de=end_de,
    )

    table = Table(title=f"DART 수집 결과 ({bgn_de} ~ {end_de})")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Fetched", str(stats.fetched))
    table.add_row("Inserted", str(stats.inserted))
    table.add_row("Duplicates", str(stats.duplicates))
    console.print(table)


@collect_app.command("naver")
def collect_naver_cmd(
    queries: list[str] = typer.Argument(None, help="검색 키워드. 미지정 시 기본 워치리스트 사용."),
    display: int = typer.Option(100, help="키워드당 가져올 건수 (최대 100)"),
) -> None:
    """네이버 뉴스 검색 API로 키워드별 뉴스를 수집해 SQLite에 적재."""
    settings = get_settings()
    if settings.naver_client_id is None or settings.naver_client_secret is None:
        console.print("[red]NAVER_CLIENT_ID/SECRET 미설정. .env를 확인하세요.[/red]")
        raise typer.Exit(code=1)

    queries = queries or list(DEFAULT_NAVER_QUERIES)

    stats = collect_naver(
        settings.naver_client_id.get_secret_value(),
        settings.naver_client_secret.get_secret_value(),
        queries,
        display=display,
    )

    table = Table(title=f"Naver 수집 결과 ({len(queries)}개 키워드)")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Fetched", str(stats.fetched))
    table.add_row("Inserted", str(stats.inserted))
    table.add_row("Duplicates", str(stats.duplicates))
    console.print(table)


@collect_app.command("rss")
def collect_rss_cmd(
    feeds: list[str] = typer.Argument(None, help="RSS 피드 URL. 미지정 시 기본 피드 사용."),
) -> None:
    """언론사 RSS 피드에서 뉴스를 수집해 PostgreSQL에 적재."""
    feeds = feeds or list(DEFAULT_FEEDS)

    stats = collect_rss(feeds)

    table = Table(title=f"RSS 수집 결과 ({len(feeds)}개 피드)")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Fetched", str(stats.fetched))
    table.add_row("Inserted", str(stats.inserted))
    table.add_row("Duplicates", str(stats.duplicates))
    console.print(table)


@tickers_app.command("sync")
def tickers_sync_cmd() -> None:
    """DART corpCode를 다운로드해 tickers 사전을 갱신."""
    settings = get_settings()
    if settings.dart_api_key is None:
        console.print("[red]DART_API_KEY 미설정. .env를 확인하세요.[/red]")
        raise typer.Exit(code=1)
    stats = sync_tickers(settings.dart_api_key.get_secret_value())
    table = Table(title="Ticker Sync 결과")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Listed (상장사)", str(stats.listed))
    table.add_row("Upserted", str(stats.inserted_or_updated))
    table.add_row("Aliases seeded", str(stats.aliases_seeded))
    console.print(table)


@app.command("dashboard")
def dashboard_cmd(
    port: int = typer.Option(8501, help="Streamlit 포트"),
) -> None:
    """Streamlit 대시보드를 로컬에서 실행 (127.0.0.1 바인딩)."""
    import os

    app_path = _resource_files("kronos.dashboard").joinpath("app.py")

    # Streamlit 첫 실행 시 이메일 프롬프트가 stdin을 잡아 멈추는 것을 방지
    cred_dir = Path.home() / ".streamlit"
    cred_dir.mkdir(parents=True, exist_ok=True)
    cred_file = cred_dir / "credentials.toml"
    if not cred_file.exists():
        cred_file.write_text('[general]\nemail = ""\n', encoding="utf-8")

    env = dict(os.environ)
    env["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"

    console.print(f"[green]Dashboard 시작[/green] — http://127.0.0.1:{port}")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            "--server.address",
            "127.0.0.1",
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--browser.gatherUsageStats",
            "false",
        ],
        check=False,
        env=env,
    )


@app.command("run")
def run_cmd(
    dart_interval: int = typer.Option(30, help="DART 폴링 주기 (초)"),
    news_interval: int = typer.Option(300, help="네이버/RSS 폴링 주기 (초)"),
    queries: list[str] = typer.Option(None, "--query", "-q", help="네이버 검색 키워드 (반복 가능)"),
) -> None:
    """스케줄러를 포그라운드에서 실행. Ctrl+C로 정상 종료."""
    settings = get_settings()
    cfg = JobConfig(
        dart_api_key=(settings.dart_api_key.get_secret_value() if settings.dart_api_key else None),
        naver_client_id=(
            settings.naver_client_id.get_secret_value() if settings.naver_client_id else None
        ),
        naver_client_secret=(
            settings.naver_client_secret.get_secret_value()
            if settings.naver_client_secret
            else None
        ),
        naver_queries=list(queries) if queries else list(DEFAULT_NAVER_QUERIES),
        dart_interval_seconds=dart_interval,
        news_interval_seconds=news_interval,
    )
    console.print(
        f"[green]Scheduler 시작[/green] — DART {dart_interval}s / 뉴스 {news_interval}s. "
        "Ctrl+C로 정상 종료."
    )
    run_forever(cfg)


@match_app.command("backfill")
def match_backfill_cmd(
    only_null: bool = typer.Option(True, help="ticker가 NULL인 행만 대상"),
) -> None:
    """기존 news 행에 종목 매칭을 적용해 ticker 컬럼을 채움."""
    stats = backfill_news_tickers(only_null=only_null)
    table = Table(title="News Ticker Backfill 결과")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Scanned", str(stats.scanned))
    table.add_row("Updated", str(stats.updated))
    console.print(table)


@disclosures_app.command("reclassify")
def disclosures_reclassify_cmd(
    only_null: bool = typer.Option(True, help="pblntf_ty가 NULL인 행만 대상"),
) -> None:
    """report_nm 패턴 룰로 disclosures.pblntf_ty를 채움."""
    from kronos.storage.reclassify import reclassify_disclosures

    stats = reclassify_disclosures(only_null=only_null)
    table = Table(title="Disclosures Reclassify 결과")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Scanned", str(stats.scanned))
    table.add_row("Updated", str(stats.updated))
    console.print(table)

    if stats.distribution:
        dist_table = Table(title="공시 유형 분포")
        dist_table.add_column("pblntf_ty")
        dist_table.add_column("count", justify="right")
        for code, n in sorted(stats.distribution.items(), key=lambda x: -x[1]):
            dist_table.add_row(code, str(n))
        console.print(dist_table)


@analyze_app.command("sentiment")
def analyze_sentiment_cmd(
    limit: int = typer.Option(1000, help="이번 실행에서 점수화할 최대 건수"),
    batch_size: int = typer.Option(64, help="모델 추론 배치 크기"),
    all_pending: bool = typer.Option(False, "--all", help="미분석분 전량 처리 (반복 실행)"),
) -> None:
    """미분석 뉴스를 KR-FinBERT로 감성 점수화 (torch/transformers 필요)."""
    from kronos.analysis.run import analyze_news_sentiment, pending_count
    from kronos.analysis.sentiment import KrFinBertModel

    pending = pending_count()
    console.print(f"미분석 뉴스: {pending:,}건")
    if pending == 0:
        return

    model = KrFinBertModel()
    total_scored = 0
    while True:
        stats = analyze_news_sentiment(model, limit=limit, batch_size=batch_size)
        total_scored += stats.scored
        console.print(f"  ... {total_scored:,}건 점수화")
        if not all_pending or stats.scanned == 0:
            break

    table = Table(title="감성 분석 결과")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Scored", str(total_scored))
    table.add_row("Remaining", str(pending_count()))
    console.print(table)


@analyze_app.command("run")
def analyze_run_cmd(
    interval: int = typer.Option(300, help="사이클 간 대기 (초)"),
    batch_size: int = typer.Option(64, help="모델 추론 배치 크기"),
    limit_per_cycle: int = typer.Option(2000, help="사이클당 최대 처리 건수"),
) -> None:
    """감성 분석 루프 (sentiment 컨테이너 엔트리포인트). Ctrl+C로 종료."""
    from kronos.analysis.run import run_sentiment_forever
    from kronos.analysis.sentiment import KrFinBertModel

    console.print(f"[green]감성 분석 루프 시작[/green] — {interval}s 주기")
    run_sentiment_forever(
        KrFinBertModel(),
        interval_seconds=interval,
        batch_size=batch_size,
        limit_per_cycle=limit_per_cycle,
    )


def _build_classifier(chunk_size: int):
    """설정 기반 LLM 분류기 생성."""
    from kronos.analysis.classify import LlmCategoryClassifier

    settings = get_settings()
    return LlmCategoryClassifier(
        settings.llm_base_url,
        settings.llm_model,
        api_key=(settings.llm_api_key.get_secret_value() if settings.llm_api_key else None),
        timeout=settings.llm_timeout_seconds,
        chunk_size=chunk_size,
    ), settings.llm_model


@analyze_app.command("category")
def analyze_category_cmd(
    limit: int = typer.Option(1000, help="이번 실행에서 분류할 최대 건수"),
    chunk_size: int = typer.Option(15, help="LLM 호출당 묶을 제목 수"),
    all_pending: bool = typer.Option(False, "--all", help="미분류분 전량 처리 (반복 실행)"),
) -> None:
    """종목 매칭된 미분류 뉴스를 자체 LLM으로 카테고리 분류 (Ollama 필요)."""
    from kronos.analysis.classify_run import classify_news, pending_classify_count

    classifier, model_name = _build_classifier(chunk_size)
    pending = pending_classify_count(model_name=model_name)
    console.print(f"미분류 종목뉴스: {pending:,}건 (모델 {model_name})")
    if pending == 0:
        return

    total = 0
    while True:
        stats = classify_news(classifier, model_name=model_name, limit=limit, chunk_size=chunk_size)
        total += stats.classified
        console.print(f"  ... {total:,}건 분류")
        if not all_pending or stats.scanned == 0:
            break

    table = Table(title="카테고리 분류 결과")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Classified", str(total))
    table.add_row("Remaining", str(pending_classify_count(model_name=model_name)))
    console.print(table)


@analyze_app.command("classify-run")
def analyze_classify_run_cmd(
    interval: int = typer.Option(300, help="사이클 간 대기 (초)"),
    chunk_size: int = typer.Option(15, help="LLM 호출당 묶을 제목 수"),
    limit_per_cycle: int = typer.Option(1500, help="사이클당 최대 처리 건수"),
) -> None:
    """카테고리 분류 루프 (백로그 자동 소진). Ctrl+C로 종료."""
    from kronos.analysis.classify_run import run_classify_forever

    classifier, model_name = _build_classifier(chunk_size)
    console.print(f"[green]카테고리 분류 루프 시작[/green] — {interval}s 주기, 모델 {model_name}")
    run_classify_forever(
        classifier,
        model_name=model_name,
        interval_seconds=interval,
        chunk_size=chunk_size,
        limit_per_cycle=limit_per_cycle,
    )


if __name__ == "__main__":
    app()
