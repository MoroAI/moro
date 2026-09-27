"""Run inspection commands; comparisons describe metrics, not model quality."""

import json
from datetime import datetime

import typer
from rich.console import Console
from rich.table import Table

from moro.core.project import load_project_config, require_project_root
from moro.storage import db

app = typer.Typer(help="Inspect recorded training runs.")
console = Console()


def project_runs(limit: int = 100):
    root, cfg = require_project_root(), load_project_config()
    conn = db.get_connection(root)
    try:
        return [
            dict(r)
            for r in conn.execute(
                "SELECT r.* FROM runs r JOIN projects p ON p.id=r.project_id WHERE p.name=? "
                "ORDER BY r.created_at DESC, r.id DESC LIMIT ?",
                (cfg.project.name, limit),
            ).fetchall()
        ]
    finally:
        conn.close()


def _format_dt(iso: str | None) -> str:
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso[:16]


def _status_color(status: str) -> str:
    return {
        "completed": "green",
        "running": "cyan",
        "failed": "red",
        "cancelled": "yellow",
        "pending": "dim",
    }.get(status, "white")


@app.command("list")
def list_command(
    limit: int = typer.Option(20, "--limit", min=1, help="Maximum runs to display."),
    json_output: bool = typer.Option(False, "--json"),
    status: str | None = typer.Option(None, "--status", help="Filter by status."),
) -> None:
    """List recorded training runs with metrics."""
    rows = project_runs(limit=limit * 2)  # fetch extra in case status filter
    if status:
        rows = [r for r in rows if r["status"] == status]
    rows = rows[:limit]

    if json_output:
        typer.echo(json.dumps(rows, indent=2, default=str))
        return

    if not rows:
        console.print("[yellow]No recorded runs for this project.[/yellow]")
        return

    table = Table(title="Training Runs", show_header=True, header_style="bold cyan")
    table.add_column("Run ID", style="cyan", no_wrap=True, max_width=24)
    table.add_column("Name", no_wrap=True, max_width=20)
    table.add_column("Status", justify="center")
    table.add_column("Model", max_width=36)
    table.add_column("Train Loss", justify="right")
    table.add_column("Val Loss", justify="right")
    table.add_column("VRAM GB", justify="right")
    table.add_column("tok/s", justify="right")
    table.add_column("Finished", no_wrap=True)

    for r in rows:
        status_str = r["status"]
        color = _status_color(status_str)
        table.add_row(
            r["id"],
            r.get("run_name") or "—",
            f"[{color}]{status_str}[/{color}]",
            r.get("model_name", "?"),
            f"{r['train_loss']:.4f}" if r.get("train_loss") is not None else "—",
            f"{r['validation_loss']:.4f}" if r.get("validation_loss") is not None else "—",
            f"{r['peak_vram_gb']:.1f}" if r.get("peak_vram_gb") is not None else "—",
            f"{r['tokens_per_sec']:.0f}" if r.get("tokens_per_sec") is not None else "—",
            _format_dt(r.get("finished_at")),
        )

    console.print(table)

    failed = [r for r in rows if r["status"] == "failed"]
    if failed:
        console.print(
            f"\n[dim]{len(failed)} failed run(s). "
            "Run [bold]moro diagnose[/bold] to see recommendations.[/dim]"
        )


@app.command("show")
def show_command(
    run_id: str = typer.Argument(..., help="Run ID to show details for."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show full details for a specific run."""
    root = require_project_root()
    conn = db.get_connection(root)
    try:
        row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        console.print(f"[red]Run not found: {run_id}[/red]")
        raise typer.Exit(code=1)

    row_dict = dict(row)

    if json_output:
        typer.echo(json.dumps(row_dict, indent=2, default=str))
        return

    color = _status_color(row_dict["status"])
    console.print(f"\n[bold]Run:[/bold] {row_dict['id']}")
    if row_dict.get("run_name"):
        console.print(f"[bold]Name:[/bold] {row_dict['run_name']}")
    console.print(f"[bold]Status:[/bold] [{color}]{row_dict['status']}[/{color}]")
    console.print(f"[bold]Model:[/bold] {row_dict['model_name']}")
    console.print(f"[bold]Quantization:[/bold] {row_dict['quantization']}")
    console.print(f"[bold]Created:[/bold] {_format_dt(row_dict.get('created_at'))}")
    console.print(f"[bold]Finished:[/bold] {_format_dt(row_dict.get('finished_at'))}")
    console.print(f"[bold]Output dir:[/bold] {row_dict.get('output_dir', '—')}")

    if row_dict.get("train_loss") is not None:
        console.print(f"[bold]Train loss:[/bold] {row_dict['train_loss']:.4f}")
    if row_dict.get("validation_loss") is not None:
        console.print(f"[bold]Val loss:[/bold] {row_dict['validation_loss']:.4f}")
    if row_dict.get("peak_vram_gb") is not None:
        console.print(f"[bold]Peak VRAM:[/bold] {row_dict['peak_vram_gb']:.2f} GB")
    if row_dict.get("tokens_per_sec") is not None:
        console.print(f"[bold]Throughput:[/bold] {row_dict['tokens_per_sec']:.0f} tok/s")
    if row_dict.get("dataset_version_id"):
        console.print(f"[bold]Dataset version:[/bold] {row_dict['dataset_version_id']}")
    if row_dict.get("error"):
        console.print(f"\n[bold red]Error:[/bold red] {row_dict['error'][:500]}")
        console.print("[dim]Run [bold]moro diagnose[/bold] for suggestions.[/dim]")


@app.command("compare")
def compare_command(
    first: str = typer.Argument(..., help="First run ID."),
    second: str = typer.Argument(..., help="Second run ID."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compare metrics between two runs."""
    rows = {row["id"]: row for row in project_runs(limit=200)}
    if first not in rows or second not in rows:
        raise typer.BadParameter("Both runs must belong to this project.")

    keys = (
        "status",
        "model_name",
        "quantization",
        "dataset_version_id",
        "train_loss",
        "validation_loss",
        "peak_vram_gb",
        "tokens_per_sec",
    )

    if json_output:
        typer.echo(
            json.dumps(
                {key: {first: rows[first][key], second: rows[second][key]} for key in keys},
                indent=2,
            )
        )
        return

    table = Table(title="Run Comparison", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="cyan")
    table.add_column(first[:20], justify="right")
    table.add_column(second[:20], justify="right")
    table.add_column("Delta", justify="right")

    for key in keys:
        v1, v2 = rows[first].get(key), rows[second].get(key)
        v1_str = f"{v1:.4f}" if isinstance(v1, float) else str(v1 or "—")
        v2_str = f"{v2:.4f}" if isinstance(v2, float) else str(v2 or "—")
        delta_str = "—"
        if isinstance(v1, float) and isinstance(v2, float):
            d = v2 - v1
            delta_str = f"[{'green' if d < 0 else 'red'}]{d:+.4f}[/{'green' if d < 0 else 'red'}]"
        table.add_row(key, v1_str, v2_str, delta_str)

    console.print(table)
