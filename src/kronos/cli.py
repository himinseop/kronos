from __future__ import annotations

from datetime import date, timedelta

import typer
from rich.console import Console
from rich.table import Table

from kronos import __version__
from kronos.collectors import dart, naver
from kronos.collectors.run import collect_dart, collect_naver
from kronos.config import get_settings
from kronos.logging_setup import configure_logging

DEFAULT_NAVER_QUERIES = ("삼성전자", "SK하이닉스", "현대차", "LG에너지솔루션")

app = typer.Typer(add_completion=False, help="Kronos CLI")
collect_app = typer.Typer(help="데이터 수집 명령 (Phase 1)")
app.add_typer(collect_app, name="collect")
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

    db_path = settings.data_dir / "kronos.db"
    stats = collect_dart(
        db_path,
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
    console.print(f"[dim]DB: {db_path}[/dim]")


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

    db_path = settings.data_dir / "kronos.db"
    stats = collect_naver(
        db_path,
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
    console.print(f"[dim]DB: {db_path}[/dim]")


if __name__ == "__main__":
    app()
