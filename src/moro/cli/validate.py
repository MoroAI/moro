"""
MoroAI Pre-Flight Validation CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from moro.config.loader import load_config
from moro.core.errors import ConfigError
from moro.core.paths import CONFIG_FILE, find_project_root
from moro.validation.engine import validate_project

console = Console()


def validate_command(
    config_path: Path | None = typer.Option(None, "--config", "-c", help="Explicit path to moro.yaml."),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Run pre-flight validation on the project configuration and environment."""
    root = find_project_root()
    if not root and not config_path:
        console.print("[bold red]Error:[/bold red] No moro.yaml found. Run [bold]moro init[/bold] first.")
        raise typer.Exit(code=1)

    resolved_root = root or config_path.parent  # type: ignore
    resolved_cfg_file = config_path or (resolved_root / CONFIG_FILE)

    if not resolved_cfg_file.exists():
        console.print(f"[bold red]Error:[/bold red] Configuration file not found: {resolved_cfg_file}")
        raise typer.Exit(code=1)

    try:
        config = load_config(resolved_cfg_file)
    except ConfigError as exc:
        console.print(f"[bold red]Configuration schema error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Error reading config:[/bold red] {exc}")
        raise typer.Exit(code=1)

    with console.status("[cyan]Running pre-flight checks…[/cyan]"):
        report = validate_project(config, resolved_root)

    if json_output:
        typer.echo(json.dumps(report.to_dict(), indent=2))
        if not report.passed:
            raise typer.Exit(code=1)
        return

    table = Table(title="MoroAI Pre-Flight Validation Report", show_header=True)
    table.add_column("Pre-Flight Check", style="bold")
    table.add_column("Status", justify="center")
    table.add_column("Details", style="dim")

    for c in report.checks:
        status_badge = {
            "pass": "[green]✓ PASS[/green]",
            "warn": "[yellow]⚠ WARN[/yellow]",
            "fail": "[red]✗ FAIL[/red]",
        }.get(c.status, c.status)
        table.add_row(c.name, status_badge, c.message)

    console.print(table)

    if report.passed:
        if report.warning_count > 0:
            console.print(f"\n[green]✓ Project ready with [yellow]{report.warning_count} non-blocking warnings[/yellow].[/green]")
        else:
            console.print("\n[bold green]✓ All pre-flight checks passed! Project is 100% ready for training and release.[/bold green]")
    else:
        console.print(f"\n[bold red]✗ Pre-flight validation failed with {report.error_count} errors.[/bold red]")
        raise typer.Exit(code=1)
