import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.core.errors import DependencyError, EvalError, ExportError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.eval.runner import run_suite
from moro.export.eligibility import resolve_export_run
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

        if base_model and run_id:
            raise EvalError("Choose --base-model or --run-id, not both.")
        if base_model:
            model_path = base_model
        else:
            selected = resolve_export_run(root, cfg.project.name, run_id)
            model_path = str(selected.adapter_path)
            run_id = selected.id

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
                revision=cfg.model.revision
                if not run_id and model_path == cfg.model.name
                else None,
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

    except (EvalError, ExportError, DependencyError) as exc:
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


@app.command("list")
def list_evaluations(
    limit: int = typer.Option(20, min=1), json_output: bool = typer.Option(False, "--json")
):
    root = require_project_root()
    cfg = load_project_config()
    conn = storage_db.get_connection(root)
    try:
        rows = [
            dict(row)
            for row in conn.execute(
                "SELECT e.id, e.run_id, e.suite_name, e.model, e.pass_rate, e.created_at "
                "FROM eval_runs e LEFT JOIN runs r ON r.id=e.run_id "
                "LEFT JOIN projects p ON p.id=r.project_id WHERE p.name=? OR e.run_id IS NULL "
                "ORDER BY e.created_at DESC LIMIT ?",
                (cfg.project.name, limit),
            ).fetchall()
        ]
    finally:
        conn.close()
    if json_output:
        typer.echo(json.dumps(rows, indent=2))
    else:
        for row in rows:
            typer.echo(f"{row['id']}  {row['suite_name']}  {row['pass_rate']:.4f}")
        if not rows:
            typer.echo("No recorded evaluations.")


@app.command("compare")
def compare_command(
    suite_path: Path = typer.Argument(
        ...,
        help="Path to the eval suite YAML file.",
        exists=True,
    ),
    base_model: str = typer.Option(
        ...,
        "--base-model",
        help="Base model path/name to compare against.",
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID whose adapter to compare.",
    ),
    max_samples: int | None = typer.Option(None, "--max-samples"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Compare base model vs fine-tuned adapter on an eval suite."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        selected = resolve_export_run(root, cfg.project.name, run_id)
        adapter_path = str(selected.adapter_path)
        resolved_run_id = selected.id

        console.print(f"[cyan]→[/cyan]  Comparing on suite: [bold]{suite_path}[/bold]")
        console.print(f"  Base model: {base_model}")
        console.print(f"  Adapter:    {adapter_path}")

        from moro.eval.compare import compare_eval

        with console.status("[cyan]Evaluating base model…[/cyan]"):
            base_result, adapter_result, delta = compare_eval(
                suite_path=suite_path,
                base_model=base_model,
                adapter_path=adapter_path,
                run_id=resolved_run_id,
                max_samples=max_samples,
                local_only=cfg.project.privacy_mode == "local_only",
            )

        # Persist both results
        conn = storage_db.get_connection(root)
        try:
            for result in (base_result, adapter_result):
                storage_db.add_eval_run(
                    conn=conn,
                    run_id=resolved_run_id if result is adapter_result else None,
                    suite_name=result.suite_name,
                    model=result.model,
                    total_cases=result.total_cases,
                    pass_rate=result.pass_rate,
                    avg_score=result.avg_score,
                    result=result.model_dump(mode="json"),
                )
        finally:
            conn.close()

        if json_output:
            import json as _json

            typer.echo(
                _json.dumps(
                    {
                        "base": base_result.model_dump(mode="json"),
                        "adapter": adapter_result.model_dump(mode="json"),
                        "delta": delta,
                    },
                    indent=2,
                )
            )
            return

        # Summary panel
        dr = delta["pass_rate_delta"]
        summary_color = "green" if dr > 0 else "red" if dr < 0 else "yellow"
        console.print(
            Panel(
                f"[bold]Pass rate:[/bold] {base_result.pass_rate * 100:.1f}% → "
                f"[{summary_color}]{adapter_result.pass_rate * 100:.1f}%[/{summary_color}] "
                f"([{summary_color}]{'+' if dr >= 0 else ''}{dr * 100:.1f}%[/{summary_color}])\n"
                f"[bold]Avg score:[/bold] {base_result.avg_score:.4f} → "
                f"{adapter_result.avg_score:.4f} ({'+' if delta['avg_score_delta'] >= 0 else ''}"
                f"{delta['avg_score_delta']:.4f})\n"
                f"[bold]Improved cases:[/bold] [green]{delta['improved_cases']}[/green]  "
                f"[bold]Regressions:[/bold] [red]{delta['regressed_cases']}[/red]  "
                f"[bold]Unchanged:[/bold] {delta['unchanged_cases']}",
                title=f"Comparison — {delta['summary'].replace('_', ' ').title()}",
                border_style=summary_color,
            )
        )

        # Per-case delta table
        table = Table(title="Per-Case Delta", show_header=True)
        table.add_column("Case ID", style="cyan")
        table.add_column("Base", justify="center")
        table.add_column("Adapter", justify="center")
        table.add_column("Δ Score", justify="right")
        table.add_column("Change", justify="center")

        base_by_id = {c.case_id: c for c in base_result.cases}
        for cs in adapter_result.cases:
            base_cs = base_by_id.get(cs.case_id)
            b_pass = "[green]✓[/green]" if (base_cs and base_cs.passed) else "[red]✗[/red]"
            a_pass = "[green]✓[/green]" if cs.passed else "[red]✗[/red]"
            score_delta = cs.score - (base_cs.score if base_cs else 0)
            change = ""
            if base_cs:
                if not base_cs.passed and cs.passed:
                    change = "[green]↑ improved[/green]"
                elif base_cs.passed and not cs.passed:
                    change = "[red]↓ regressed[/red]"
            table.add_row(
                cs.case_id,
                b_pass,
                a_pass,
                f"{'+' if score_delta >= 0 else ''}{score_delta:.4f}",
                change,
            )

        console.print(table)

        if delta["regressed_cases"] > 0:
            console.print(
                "\n[bold yellow]⚠  Regressions detected.[/bold yellow] "
                "Review the cases above before exporting."
            )

    except (EvalError, ExportError, DependencyError) as exc:
        console.print(f"[bold red]Eval error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("perturb")
def perturb_command(
    suite_path: Path = typer.Argument(
        ...,
        help="Path to the eval suite YAML file.",
        exists=True,
    ),
    run_id: str | None = typer.Option(
        None,
        "--run-id",
        help="Run ID whose adapter to evaluate under perturbations.",
    ),
    base_model: str | None = typer.Option(
        None,
        "--base-model",
        help="Base model path/name to evaluate under perturbations.",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Export generated perturbed cases as a new eval suite YAML.",
    ),
    seed: int = typer.Option(42, "--seed", help="Random seed for deterministic perturbations."),
    max_samples: int | None = typer.Option(None, "--max-samples", help="Limit cases evaluated."),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Run adversarial robustness testing with deterministic perturbations."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        from moro.eval.robustness import create_perturbed_suite, evaluate_robustness

        if output:
            create_perturbed_suite(suite_path, output, seed=seed, max_samples=max_samples)
            if not json_output:
                console.print(
                    f"[bold green]✓[/bold green] Perturbed eval suite exported to: [bold]{output}[/bold]"
                )
            if not base_model and not run_id:
                if json_output:
                    typer.echo(json.dumps({"exported_suite": str(output), "seed": seed}))
                return

        # Model evaluation path
        if base_model and run_id:
            raise EvalError("Choose --base-model or --run-id, not both.")

        if base_model:
            model_path = base_model
        elif run_id:
            selected = resolve_export_run(root, cfg.project.name, run_id)
            model_path = str(selected.adapter_path)
            run_id = selected.id
        else:
            try:
                selected = resolve_export_run(root, cfg.project.name, None)
                model_path = str(selected.adapter_path)
                run_id = selected.id
            except Exception:
                model_path = cfg.model.name

        if not json_output:
            console.print(f"[cyan]→[/cyan]  Adversarial testing on: [bold]{model_path}[/bold]")
            console.print(f"[cyan]→[/cyan]  Suite: [bold]{suite_path}[/bold] (seed: {seed})")

        with console.status("[cyan]Running adversarial perturbations…[/cyan]"):
            report = evaluate_robustness(
                suite_path=suite_path,
                model_path=model_path,
                seed=seed,
                max_samples=max_samples,
                local_only=cfg.project.privacy_mode == "local_only",
                revision=cfg.model.revision
                if not run_id and model_path == cfg.model.name
                else None,
            )

        if json_output:
            payload = {
                "total_cases": report.total_cases,
                "avg_raw_robustness": report.avg_raw_robustness,
                "avg_strict_robustness": report.avg_strict_robustness,
                "total_vulnerabilities": report.total_vulnerabilities,
                "most_vulnerable_perturbation": report.most_vulnerable_perturbation,
                "robustness_grade": report.robustness_grade,
                "perturbation_failure_counts": report.perturbation_failure_counts,
                "cases": [
                    {
                        "case_id": c.case_id,
                        "base_passed": c.base_passed,
                        "raw_robustness": c.raw_robustness,
                        "strict_robustness": c.strict_robustness,
                        "vulnerability_count": c.vulnerability_count,
                        "failed_perturbations": c.failed_perturbations,
                    }
                    for c in report.case_results
                ],
            }
            typer.echo(json.dumps(payload, indent=2))
            return

        # Rich Display
        grade_color = (
            "green"
            if "A" in report.robustness_grade or "B" in report.robustness_grade
            else "yellow"
            if "C" in report.robustness_grade
            else "red"
        )
        console.print(
            Panel(
                f"[bold]Robustness Grade:[/bold] [{grade_color}]{report.robustness_grade}[/{grade_color}]\n"
                f"[bold]Strict Robustness:[/bold] {report.avg_strict_robustness * 100:.1f}%\n"
                f"[bold]Raw Robustness:[/bold] {report.avg_raw_robustness * 100:.1f}%\n"
                f"[bold]Total Regressions/Vulnerabilities:[/bold] [red]{report.total_vulnerabilities}[/red]\n"
                f"[bold]Most Fragile Under:[/bold] [yellow]{report.most_vulnerable_perturbation or 'None'}[/yellow]",
                title="Adversarial Robustness Summary",
                border_style=grade_color,
            )
        )

        table = Table(title="Per-Case Adversarial Breakdown", show_header=True)
        table.add_column("Case ID", style="cyan")
        table.add_column("Base", justify="center")
        table.add_column("Raw Rob.", justify="right")
        table.add_column("Strict Rob.", justify="right")
        table.add_column("Vulns", justify="center")
        table.add_column("Failed Perturbations", style="dim")

        for c in report.case_results:
            b_icon = "[green]✓[/green]" if c.base_passed else "[red]✗[/red]"
            v_color = "green" if c.vulnerability_count == 0 else "red"
            failed_str = (
                ", ".join(c.failed_perturbations)
                if c.failed_perturbations
                else "[green]none[/green]"
            )
            table.add_row(
                c.case_id,
                b_icon,
                f"{c.raw_robustness * 100:.0f}%",
                f"{c.strict_robustness * 100:.0f}%",
                f"[{v_color}]{c.vulnerability_count}[/{v_color}]",
                failed_str,
            )

        console.print(table)

    except (EvalError, ExportError, DependencyError) as exc:
        console.print(f"[bold red]Eval error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
