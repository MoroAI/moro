import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.core.errors import ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.diagnose.analyzer import analyze_error
from moro.storage import db as storage_db

console = Console()


def _extract_error_from_log(output_dir: Path) -> str | None:
    """
    Scan the run's output directory for a training_report.json or any .log files
    to extract a more detailed error message.
    """
    if not output_dir or not output_dir.exists():
        return None

    # 1. Try training_report.json
    report = output_dir / "training_report.json"
    if report.exists():
        try:
            data = json.loads(report.read_text(encoding="utf-8"))
            if "error" in data:
                return str(data["error"])
        except Exception:
            pass

    # 2. Try scanning .log files for exceptions
    for log_file in output_dir.rglob("*.log"):
        try:
            lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
            # Look for Traceback/Error lines in the last 200 lines
            tail = lines[-200:]
            error_lines = []
            in_traceback = False
            for line in tail:
                if "Traceback (most recent call last)" in line or "Error:" in line:
                    in_traceback = True
                if in_traceback:
                    error_lines.append(line)
                    if len(error_lines) > 30:
                        break
            if error_lines:
                return "\n".join(error_lines)
        except Exception:
            pass

    return None


def diagnose_command(
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID to diagnose."),
    last: bool = typer.Option(False, "--last", help="Diagnose the latest run."),
    json_output: bool = typer.Option(False, "--json"),
    scan_logs: bool = typer.Option(
        True,
        "--scan-logs/--no-scan-logs",
        help="Scan run output directory for more error context.",
    ),
) -> None:
    """Diagnose failures and suggest fixes."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        conn = storage_db.get_connection(root)
        if run_id:
            run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        else:
            run_row = conn.execute(
                "SELECT r.* FROM runs r JOIN projects p ON p.id=r.project_id "
                "WHERE p.name=? ORDER BY r.created_at DESC LIMIT 1",
                (cfg.project.name,),
            ).fetchone()
        conn.close()

        if not run_row:
            console.print("[yellow]No runs found in this project.[/yellow]")
            console.print("Run [bold]moro train[/bold] to create a run.")
            raise typer.Exit(code=0)

        run_data = dict(run_row)
        resolved_run_id = run_data["id"]
        status = run_data["status"]
        error_text = run_data.get("error") or ""

        # Supplement with log scan if available
        if scan_logs and run_data.get("output_dir"):
            output_dir = Path(run_data["output_dir"])
            if not output_dir.is_absolute():
                output_dir = root / output_dir
            log_error = _extract_error_from_log(output_dir)
            if log_error and log_error not in error_text:
                error_text = f"{error_text}\n\n[from logs]\n{log_error}".strip()

        if json_output:
            diagnosis = analyze_error(error_text)
            typer.echo(json.dumps({
                "run_id": resolved_run_id,
                "status": status,
                "error": error_text[:1000] if error_text else None,
                "diagnosis": diagnosis,
            }, indent=2))
            return

        # Header
        color = {
            "completed": "green",
            "failed": "red",
            "cancelled": "yellow",
            "running": "cyan",
        }.get(status, "white")
        console.print(f"\n[bold]Run:[/bold] {resolved_run_id}")
        console.print(f"[bold]Status:[/bold] [{color}]{status}[/{color}]")

        if status == "completed":
            console.print("\n[green]✓ This run completed successfully — nothing to diagnose.[/green]")
            return

        diagnosis = analyze_error(error_text)

        console.print()
        console.print(Panel(
            f"[bold red]{diagnosis['issue']}[/bold red]\n\n"
            f"[bold]Likely cause:[/bold] {diagnosis['cause']}",
            title="Diagnosis",
            border_style="red",
        ))

        if diagnosis["actions"]:
            console.print("\n[bold yellow]Recommended actions:[/bold yellow]")
            for i, action in enumerate(diagnosis["actions"], 1):
                console.print(f"  {i}. {action}")

        if diagnosis["config_changes"]:
            table = Table(title="Suggested moro.yaml changes", show_header=True)
            table.add_column("Key", style="cyan")
            table.add_column("Value", style="bold")
            for key, val in diagnosis["config_changes"].items():
                table.add_row(key, str(val))
            console.print()
            console.print(table)
            console.print(
                "\n[dim]Apply automatically: [bold]moro recipe apply[/bold][/dim]"
            )

        if error_text and status == "failed":
            short = error_text[:400].replace("\n", " ")
            console.print(f"\n[dim]Raw error (truncated): {short}…[/dim]")

    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
