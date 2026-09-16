import json

import typer
from rich.console import Console
from rich.table import Table

from moro.core.errors import ConfigError, ProjectError
from moro.core.project import load_project_config, require_project_root

console = Console()


def status_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output status as JSON.",
    ),
) -> None:
    """Show current MoroAI project status."""
    try:
        root = require_project_root()
        config = load_project_config()

        # Resolve dataset source path
        dataset_source = config.dataset.source
        if not dataset_source.is_absolute():
            dataset_source = root / dataset_source
        dataset_source_exists = dataset_source.exists()

        # Check for SQLite DB
        db_path = root / ".moro" / "db.sqlite"
        db_exists = db_path.exists()

        # Latest run / dataset version (attempt DB read if available)
        latest_dataset_version = "none"
        latest_run = "none"
        if db_exists:
            try:
                from moro.storage import db as storage_db

                conn = storage_db.get_connection(root)
                row = conn.execute(
                    "SELECT id, version FROM dataset_versions ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if row:
                    latest_dataset_version = f"{row['version']} ({row['id']})"

                run_row = conn.execute(
                    "SELECT id, status FROM runs ORDER BY created_at DESC LIMIT 1"
                ).fetchone()
                if run_row:
                    latest_run = f"{run_row['id']} ({run_row['status']})"
                conn.close()
            except Exception:
                pass

        payload = {
            "project_root": str(root),
            "project_name": config.project.name,
            "privacy_mode": config.project.privacy_mode,
            "config_valid": True,
            "model": config.model.name,
            "quantization": config.model.quantization,
            "dataset_source": str(dataset_source),
            "dataset_source_exists": dataset_source_exists,
            "eval_suites": len(config.eval.suites),
            "latest_dataset_version": latest_dataset_version,
            "latest_run": latest_run,
        }

        if json_output:
            typer.echo(json.dumps(payload, indent=2))
            return

        table = Table(title="MoroAI Project Status", show_header=True)
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Project", config.project.name)
        table.add_row("Root", str(root))
        table.add_row("Privacy mode", config.project.privacy_mode)
        table.add_row("Model", config.model.name)
        table.add_row("Quantization", config.model.quantization)
        table.add_row(
            "Dataset source",
            f"{dataset_source} "
            f"{'[green]✓[/green]' if dataset_source_exists else '[red]✗ not found[/red]'}",
        )
        table.add_row("Eval suites", str(len(config.eval.suites)))
        table.add_row("Latest dataset version", latest_dataset_version)
        table.add_row("Latest run", latest_run)

        console.print(table)

    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ConfigError as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
