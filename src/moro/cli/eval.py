import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from moro.core.errors import EvalError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.eval.runner import run_suite
from moro.storage import db as storage_db

app = typer.Typer(name="eval", help="Evaluation operations.")
console = Console()


@app.command("run")
def eval_run_command(
    suite_path: Path = typer.Argument(
        ...,
        help="Path to the eval suite YAML file.",
        exists=True,
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID whose adapter to evaluate.",
    ),
    base_model: str | None = typer.Option(
        None,
        "--base-model",
        help="Override model path/name to evaluate.",
    ),
    max_samples: int | None = typer.Option(
        None,
        "--max-samples",
        help="Limit cases evaluated.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Run an evaluation suite against a trained model."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        # Determine model path
        if base_model:
            model_path = base_model
        elif run_id:
            model_path = str(root / "runs" / run_id / "adapter")
        else:
            # Try latest run
            conn = storage_db.get_connection(root)
            project_id = storage_db.get_or_create_project(conn, cfg.project.name)
            run_row = storage_db.get_latest_run(conn, project_id)
            conn.close()
            if run_row and run_row["status"] == "completed":
                model_path = str(Path(run_row["output_dir"]) / "adapter")
                run_id = run_row["id"]
                if not json_output:
                    console.print(f"[dim]Using latest completed run: {run_id}[/dim]")
            else:
                raise EvalError(
                    "No completed run found. Specify --run-id or --base-model, "
                    "or run `moro train` first."
                )

        if not json_output:
            console.print(f"[cyan]→[/cyan]  Evaluating: [bold]{model_path}[/bold]")
            console.print(f"[cyan]→[/cyan]  Suite: [bold]{suite_path}[/bold]")

        with console.status("[cyan]Running eval suite…[/cyan]"):
            result = run_suite(
                suite_path=suite_path,
                model_path=model_path,
                run_id=run_id,
                max_samples=max_samples,
                local_only=cfg.project.privacy_mode == "local_only",
                revision=cfg.model.revision if not run_id else None,
            )

        # Persist to DB
        conn = storage_db.get_connection(root)
        storage_db.add_eval_run(
            conn=conn,
            run_id=run_id,
            suite_name=result.suite_name,
            model=model_path,
            total_cases=result.total_cases,
            pass_rate=result.pass_rate,
            avg_score=result.avg_score,
            result=result.model_dump(mode="json"),
        )
        conn.close()

        if json_output:
            typer.echo(result.model_dump_json(indent=2))
            return

        # Display table
        table = Table(title=f"Eval Results — {result.suite_name}", show_header=True)
        table.add_column("Case ID", style="cyan")
        table.add_column("Passed", justify="center")
        table.add_column("Score", justify="right")

        for cs in result.cases:
            status = "[green]✓[/green]" if cs.passed else "[red]✗[/red]"
            table.add_row(cs.case_id, status, f"{cs.score:.4f}")

        console.print(table)

        color = (
            "green" if result.pass_rate >= 0.8 else "yellow" if result.pass_rate >= 0.5 else "red"
        )
        console.print(
            f"\n[bold]Pass rate:[/bold] [{color}]{result.pass_rate * 100:.1f}%[/{color}] "
            f"({sum(1 for c in result.cases if c.passed)}/{result.total_cases})"
        )
        console.print(f"[bold]Avg score:[/bold] {result.avg_score:.4f}")
        console.print(f"\n[dim]Eval ID: {result.id}[/dim]")

    except EvalError as exc:
        console.print(f"[bold red]Eval error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("report")
def eval_report_command(
    eval_id: str = typer.Argument(..., help="Eval run ID to show."),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show a specific evaluation result."""
    try:
        root = require_project_root()
        conn = storage_db.get_connection(root)
        row = conn.execute("SELECT * FROM eval_runs WHERE id = ?", (eval_id,)).fetchone()
        conn.close()

        if not row:
            console.print(f"[red]Eval run not found: {eval_id}[/red]")
            raise typer.Exit(code=1)

        data = json.loads(row["result_json"])

        if json_output:
            typer.echo(json.dumps(data, indent=2))
            return

        console.print(f"[bold]Suite:[/bold] {row['suite_name']}")
        console.print(f"[bold]Model:[/bold] {row['model']}")
        console.print(f"[bold]Total cases:[/bold] {row['total_cases']}")
        console.print(f"[bold]Pass rate:[/bold] {row['pass_rate'] * 100:.1f}%")
        console.print(f"[bold]Avg score:[/bold] {row['avg_score']:.4f}")

    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
