"""
MoroAI Flywheel CLI Commands.

Provides commands to operate the continuous learning DPO feedback loop:
  moro flywheel status   — View pending production logs and epoch stats
  moro flywheel run      — Execute continuous learning cycle (extract DPO pairs)
  moro flywheel history  — View history of DPO learning epochs
  moro flywheel ingest   — Import raw chat logs into the production database
  moro flywheel serve    — Run the HTTP webhook receiver for chat UIs
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.core.project import find_project_root
from moro.flywheel.ingestors.sqlite_ingestor import SQLiteLogIngestor
from moro.flywheel.orchestrator import FlywheelConfig, MoroAIFlywheelOrchestrator
from moro.flywheel.storage.schema import get_db_stats, initialize_production_db

console = Console()
app = typer.Typer(
    name="flywheel",
    help="Continuous learning DPO flywheel operations.",
    no_args_is_help=True,
)


def _get_db_path(db_option: Path | None) -> Path:
    if db_option:
        return db_option
    root = find_project_root()
    if root:
        return root / "data" / "production_logs.db"
    return Path("data/production_logs.db")


@app.command("status")
def flywheel_status(
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to production logs SQLite database."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output stats as JSON."),
) -> None:
    """View production log queue and flywheel statistics."""
    try:
        resolved_db = _get_db_path(db_path)
        initialize_production_db(resolved_db)
        stats = get_db_stats(resolved_db)

        if json_output:
            typer.echo(json.dumps({"database_path": str(resolved_db), **stats}, indent=2))
            return

        console.print(
            Panel(
                f"[bold cyan]Database:[/bold cyan] {resolved_db}\n"
                f"[bold]Pending Unprocessed Logs:[/bold] [yellow]{stats['pending_logs']}[/yellow]\n"
                f"[bold]Processed Logs:[/bold] [green]{stats['processed_logs']}[/green]\n"
                f"[bold]Total Logs Ingested:[/bold] {stats['total_logs']}\n"
                f"[bold]Generated DPO Pairs:[/bold] [magenta]{stats['total_pairs']}[/magenta]\n"
                f"[bold]Completed Epochs:[/bold] {stats['total_epochs']}",
                title="MoroAI DPO Flywheel Status",
                border_style="cyan",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("ingest")
def flywheel_ingest(
    jsonl_path: Path = typer.Argument(
        ..., help="Path to raw JSONL file containing production logs.", exists=True
    ),
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to production logs SQLite database."
    ),
) -> None:
    """Import raw production logs into the SQLite database."""
    try:
        resolved_db = _get_db_path(db_path)
        initialize_production_db(resolved_db)
        ingestor = SQLiteLogIngestor(resolved_db)

        with console.status("[cyan]Ingesting production logs…[/cyan]"):
            count = ingestor.insert_logs_from_jsonl(jsonl_path)

        console.print(
            f"[bold green]✓[/bold green] Ingested [bold]{count}[/bold] production logs into {resolved_db}"
        )
    except Exception as exc:
        console.print(f"[bold red]Ingest error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("run")
def flywheel_run(
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to production logs SQLite database."
    ),
    min_pairs: int = typer.Option(
        1, "--min-pairs", help="Minimum pairs needed to generate an epoch."
    ),
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Directory to save DPO dataset."
    ),
    json_output: bool = typer.Option(False, "--json", help="Output execution summary as JSON."),
) -> None:
    """Execute a continuous learning cycle: extract preference pairs and compile DPO dataset."""
    try:
        root = find_project_root()
        resolved_db = _get_db_path(db_path)
        initialize_production_db(resolved_db)

        dpo_out = output_dir or (root / "data" / "dpo" if root else Path("data/dpo"))
        config = FlywheelConfig(
            min_pairs_per_epoch=min_pairs,
            output_dir=dpo_out,
        )
        ingestor = SQLiteLogIngestor(resolved_db)
        orchestrator = MoroAIFlywheelOrchestrator(config=config, ingestor=ingestor)

        with console.status("[cyan]Running DPO continuous learning cycle…[/cyan]"):
            summary = orchestrator.run_cycle()

        if json_output:
            typer.echo(json.dumps(summary.to_dict(), indent=2))
            return

        if summary.pairs_generated == 0:
            console.print(
                "[yellow]No eligible logs or feedback found to extract preference pairs.[/yellow]"
            )
            console.print(
                "Ingest logs with [bold]moro flywheel ingest[/bold] or run [bold]moro flywheel serve[/bold]."
            )
            return

        console.print(
            Panel(
                f"[bold green]✓ DPO Flywheel Cycle Completed[/bold green]\n\n"
                f"[bold]Epoch ID:[/bold] {summary.epoch_id}\n"
                f"[bold]Logs Processed:[/bold] {summary.logs_ingested}\n"
                f"[bold]Preference Pairs Generated:[/bold] [bold magenta]{summary.pairs_generated}[/bold magenta]\n"
                f"[bold]Dataset Written:[/bold] {summary.dataset_path}",
                title="Continuous Learning Cycle Success",
                border_style="green",
            )
        )

        table = Table(title="Generated Pairs by Signal Type", show_header=True)
        table.add_column("Feedback Type", style="cyan")
        table.add_column("Count", justify="right")
        for ftype, count in summary.pairs_by_type.items():
            table.add_row(ftype, str(count))
        console.print(table)

    except Exception as exc:
        console.print(f"[bold red]Flywheel error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("history")
def flywheel_history(
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to production logs SQLite database."
    ),
    limit: int = typer.Option(10, "--limit", help="Max epochs to display."),
    json_output: bool = typer.Option(False, "--json", help="Output history as JSON."),
) -> None:
    """View past continuous learning DPO epochs."""
    try:
        resolved_db = _get_db_path(db_path)
        initialize_production_db(resolved_db)
        ingestor = SQLiteLogIngestor(resolved_db)
        epochs = ingestor.list_epochs(limit=limit)

        if json_output:
            typer.echo(json.dumps(epochs, indent=2))
            return

        if not epochs:
            console.print("[dim]No DPO learning epochs recorded yet.[/dim]")
            return

        table = Table(title="DPO Learning Epochs", show_header=True)
        table.add_column("Epoch ID", style="cyan")
        table.add_column("Status", justify="center")
        table.add_column("Pairs", justify="right")
        table.add_column("Started At", style="dim")

        for ep in epochs:
            table.add_row(
                ep["epoch_id"],
                ep["status"],
                str(ep["pair_count"]),
                ep["started_at"] or "",
            )
        console.print(table)
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("serve")
def flywheel_serve(
    host: str = typer.Option("127.0.0.1", "--host", help="Host address."),
    port: int = typer.Option(8001, "--port", help="Port number."),
    api_key: str | None = typer.Option(
        None, "--api-key", help="Optional API key for webhook auth."
    ),
    db_path: Path | None = typer.Option(
        None, "--db", help="Path to production logs SQLite database."
    ),
) -> None:
    """Start the FastAPI webhook receiver for production chat UIs."""
    try:
        resolved_db = _get_db_path(db_path)
        initialize_production_db(resolved_db)

        console.print(
            Panel(
                f"[bold cyan]Starting MoroAI Flywheel Webhook Receiver[/bold cyan]\n\n"
                f"Endpoint: http://{host}:{port}/webhook/ingest\n"
                f"Stats:    http://{host}:{port}/webhook/stats\n"
                f"Database: {resolved_db}\n"
                f"Auth:     {'API Key required' if api_key else 'Public (no auth)'}\n\n"
                "Press Ctrl+C to terminate.",
                border_style="cyan",
            )
        )
        from moro.flywheel.webhook.receiver import start_webhook_receiver

        start_webhook_receiver(host=host, port=port, api_key=api_key, db_path=resolved_db)
    except KeyboardInterrupt:
        console.print("\n[yellow]Webhook server stopped.[/yellow]")
    except Exception as exc:
        console.print(f"[bold red]Server error:[/bold red] {exc}")
        raise typer.Exit(code=1)
