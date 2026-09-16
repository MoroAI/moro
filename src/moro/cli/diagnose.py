import json

import typer
from rich.console import Console
from rich.panel import Panel

from moro.core.errors import ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.diagnose.analyzer import analyze_error
from moro.storage import db as storage_db

console = Console()


def diagnose_command(
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID to diagnose."),
    last: bool = typer.Option(False, "--last", help="Diagnose the latest run."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Diagnose failures and suggest fixes."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        conn = storage_db.get_connection(root)
        project_id = storage_db.get_or_create_project(conn, cfg.project.name)

        if run_id:
            run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        else:
            run_row = conn.execute(
                "SELECT * FROM runs WHERE project_id = ? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()

        conn.close()

        if not run_row:
            console.print("[yellow]No runs found in this project.[/yellow]")
            console.print("Run [bold]moro train[/bold] to create a run.")
            raise typer.Exit(code=0)

        resolved_run_id = run_row["id"]
        status = run_row["status"]
        error_text = run_row["error"] or ""

        if json_output:
            diagnosis = analyze_error(error_text)
            typer.echo(
                json.dumps(
                    {
                        "run_id": resolved_run_id,
                        "status": status,
                        "diagnosis": diagnosis,
                    },
                    indent=2,
                )
            )
            return

        console.print(f"[bold]Run:[/bold] {resolved_run_id}")
        console.print(
            f"[bold]Status:[/bold] {'[green]' if status == 'completed' else '[red]'}{status}[/]"
        )

        if status == "completed":
            console.print(
                "\n[green]✓ This run completed successfully — nothing to diagnose.[/green]"
            )
            return

        diagnosis = analyze_error(error_text)

        console.print()
        console.print(
            Panel(
                f"[bold red]{diagnosis['issue']}[/bold red]\n\n"
                f"[bold]Likely cause:[/bold] {diagnosis['cause']}",
                title="Diagnosis",
                border_style="red",
            )
        )

        if diagnosis["actions"]:
            console.print("\n[bold yellow]Recommended actions:[/bold yellow]")
            for i, action in enumerate(diagnosis["actions"], 1):
                console.print(f"  {i}. {action}")

        if diagnosis["config_changes"]:
            console.print("\n[bold]Suggested moro.yaml changes:[/bold]")
            for key, val in diagnosis["config_changes"].items():
                console.print(f"  [cyan]{key}[/cyan]: [bold]{val}[/bold]")

    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
