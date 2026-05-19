from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from kronos import __version__
from kronos.collectors import dart, naver
from kronos.config import get_settings
from kronos.logging_setup import configure_logging

app = typer.Typer(add_completion=False, help="Kronos CLI")
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


if __name__ == "__main__":
    app()
