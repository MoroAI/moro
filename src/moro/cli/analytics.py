"""
MoroAI Analytics CLI Commands.

Provides CLI access to experiment tracking, multi-run comparison,
quality trends, and automated experiment recommendations.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.analytics.tracker import ExperimentTracker
from moro.core.errors import ProjectError
from moro.core.project import require_project_root

console = Console()
analytics_app = typer.Typer(
    name="analytics",
    help="Experiment tracking and visual analytics commands.",
    no_args_is_help=True,
)


def _get_tracker() -> ExperimentTracker:
    root = require_project_root()
    db_path = root / ".moro" / "analytics.db"
    return ExperimentTracker(db_path)


@analytics_app.command("list")
def analytics_list(
    status: str | None = typer.Option(
        None, help="Filter by status (e.g. completed, failed, running)"
    ),
    base_model: str | None = typer.Option(None, help="Filter by base model name"),
    limit: int = typer.Option(20, help="Maximum number of experiments to show"),
) -> None:
    """List tracked experiments."""
    try:
        tracker = _get_tracker()
        experiments = tracker.list_experiments(status=status, base_model=base_model, limit=limit)

        if not experiments:
            console.print("[yellow]No experiments found in analytics database.[/yellow]")
            return

        table = Table(title="MoroAI Experiments")
        table.add_column("ID", style="cyan", min_width=12)
        table.add_column("Name", style="white", min_width=14)
        table.add_column("Status", style="white", min_width=10)
        table.add_column("Model", style="white", min_width=16)
        table.add_column("Eval Delta", style="white", min_width=10)
        table.add_column("Duration", style="white", min_width=10)
        table.add_column("Created", style="white", min_width=10)

        for exp in experiments:
            status_val = exp.get("status", "unknown")
            status_str = {
                "completed": "[green]completed[/green]",
                "failed": "[red]failed[/red]",
                "running": "[blue]running[/blue]",
                "pending": "[yellow]pending[/yellow]",
            }.get(status_val, status_val)

            delta_str = "-"
            if exp.get("eval_delta") is not None:
                delta = exp["eval_delta"]
                color = "green" if delta > 0 else "red"
                delta_str = f"[{color}]{delta:+.1%}[/{color}]"

            duration_str = "-"
            if exp.get("duration_seconds") is not None:
                mins = exp["duration_seconds"] / 60
                duration_str = f"{mins:.1f}m"

            table.add_row(
                exp.get("experiment_id", "-")[:12],
                exp.get("experiment_name", "-")[:20],
                status_str,
                (exp.get("base_model") or "-")[:20],
                delta_str,
                duration_str,
                str(exp.get("created_at") or "-")[:10],
            )

        console.print(table)

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Error listing experiments:[/bold red] {exc}")
        raise typer.Exit(code=1)


@analytics_app.command("show")
def analytics_show(
    experiment_id: str = typer.Argument(..., help="Experiment ID to inspect"),
) -> None:
    """Show detailed metadata and hyperparameters for an experiment."""
    try:
        tracker = _get_tracker()
        exp = tracker.get_experiment(experiment_id)

        if not exp:
            console.print(f"[red]Experiment not found: {experiment_id}[/red]")
            raise typer.Exit(code=1)

        hp = tracker.get_hyperparameters(experiment_id) or {}
        metrics = tracker.get_metrics(experiment_id)

        console.print(
            Panel(
                f"[bold]Experiment:[/bold] {exp.get('experiment_name')} ({exp.get('experiment_id')})\n"
                f"[bold]Status:[/bold] {exp.get('status')} | [bold]Base Model:[/bold] {exp.get('base_model')}\n"
                f"[bold]Created:[/bold] {exp.get('created_at')} | [bold]Duration:[/bold] {exp.get('duration_seconds', 0) or 0:.1f}s\n"
                f"[bold]Train Loss:[/bold] {exp.get('final_train_loss') or '-'} | [bold]Eval Delta:[/bold] {exp.get('eval_delta') or '-'}\n"
                f"[bold]Metric Steps Logged:[/bold] {len(metrics)}",
                title=f"Experiment Detail: {experiment_id}",
                border_style="cyan",
            )
        )

        if hp:
            hp_table = Table(title="Recorded Hyperparameters")
            hp_table.add_column("Parameter", style="cyan")
            hp_table.add_column("Value", style="white")

            for k, v in hp.items():
                if k not in (
                    "param_id",
                    "experiment_id",
                    "created_at",
                    "full_config_json",
                    "target_modules_json",
                    "full_config",
                ):
                    hp_table.add_row(k, str(v) if v is not None else "-")

            console.print(hp_table)

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)


@analytics_app.command("compare")
def analytics_compare(
    experiment_ids: str = typer.Argument(..., help="Comma-separated experiment IDs to compare"),
) -> None:
    """Compare multiple experiments side-by-side."""
    try:
        tracker = _get_tracker()
        ids = [i.strip() for i in experiment_ids.split(",") if i.strip()]

        if not ids:
            console.print("[red]Please specify at least one experiment ID to compare.[/red]")
            return

        comparison = tracker.compare_experiments(ids)

        if "error" in comparison:
            console.print(f"[red]{comparison['error']}[/red]")
            return

        console.print(
            Panel(
                f"[bold]Comparing {len(ids)} experiments[/bold]: {', '.join(ids)}",
                border_style="blue",
            )
        )

        # Hyperparameter differences
        hp_diffs = comparison.get("hyperparameter_differences", {})
        if hp_diffs:
            console.print("\n[bold cyan]Hyperparameter Differences:[/bold cyan]")
            hp_table = Table()
            hp_table.add_column("Parameter", style="cyan")
            for i, exp_id in enumerate(ids):
                hp_table.add_column(f"Exp {i + 1} ({exp_id[:8]})", style="white")

            for param, values in hp_diffs.items():
                row = [param] + [str(v) if v is not None else "-" for v in values]
                hp_table.add_row(*row)

            console.print(hp_table)
        else:
            console.print("\n[dim]No hyperparameter differences found across runs.[/dim]")

        # Metrics comparison
        metrics = comparison.get("metrics_comparison", {})
        console.print("\n[bold cyan]Metrics Comparison:[/bold cyan]")

        metric_table = Table()
        metric_table.add_column("Metric", style="cyan")
        for i, exp_id in enumerate(ids):
            metric_table.add_column(f"Exp {i + 1} ({exp_id[:8]})", style="white")

        for metric_name in [
            "final_train_loss",
            "final_eval_loss",
            "eval_pass_rate",
            "eval_delta",
            "duration_seconds",
            "peak_vram_gb",
        ]:
            values = metrics.get(metric_name, [])
            row = [metric_name]
            for val in values:
                if val is None:
                    row.append("-")
                elif isinstance(val, float):
                    row.append(f"{val:.4f}")
                else:
                    row.append(str(val))
            metric_table.add_row(*row)

        console.print(metric_table)

        # Best experiment
        best_id = comparison.get("best_experiment_id")
        if best_id:
            console.print(f"\n[bold green]🏆 Best Experiment: {best_id}[/bold green]")

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Error comparing experiments:[/bold red] {exc}")
        raise typer.Exit(code=1)


@analytics_app.command("trend")
def analytics_trend(
    base_model: str | None = typer.Option(None, help="Filter by base model"),
    limit: int = typer.Option(20, help="Number of experiments to include"),
) -> None:
    """Show model quality trend over time."""
    try:
        tracker = _get_tracker()
        trend = tracker.get_quality_trend(base_model=base_model, limit=limit)

        if not trend:
            console.print("[yellow]No completed experiments found for quality trend.[/yellow]")
            return

        table = Table(title="Model Quality Trend")
        table.add_column("Date", style="cyan")
        table.add_column("Name", style="white")
        table.add_column("Pass Rate", style="white")
        table.add_column("Delta", style="white")
        table.add_column("Loss", style="white")

        for exp in trend:
            delta_str = "-"
            if exp.get("eval_delta") is not None:
                delta = exp["eval_delta"]
                color = "green" if delta > 0 else "red"
                delta_str = f"[{color}]{delta:+.1%}[/{color}]"

            pass_rate = exp.get("eval_pass_rate")
            pass_str = f"{pass_rate:.1%}" if pass_rate is not None else "-"
            loss_val = exp.get("final_train_loss")
            loss_str = f"{loss_val:.4f}" if loss_val is not None else "-"

            table.add_row(
                str(exp.get("created_at") or "-")[:10],
                str(exp.get("experiment_name") or "-")[:20],
                pass_str,
                delta_str,
                loss_str,
            )

        console.print(table)

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Error calculating quality trend:[/bold red] {exc}")
        raise typer.Exit(code=1)


@analytics_app.command("recommend")
def analytics_recommend(
    recent: int = typer.Option(10, help="Number of recent experiments to analyze"),
) -> None:
    """Get recommendations for the next experiment based on historical trends."""
    try:
        tracker = _get_tracker()
        recommendations = tracker.generate_recommendations(recent_experiments=recent)

        if not recommendations:
            console.print("[yellow]No recommendations available yet.[/yellow]")
            return

        console.print(
            Panel(
                "[bold]Experiment Recommendations[/bold]\n"
                "Derived from historical metrics, hyperparameter analysis, and failure patterns",
                border_style="blue",
            )
        )

        rec_type_icons = {
            "hyperparameter_change": "⚙️",
            "dataset_change": "📊",
            "architecture_change": "🏗️",
            "stop_training": "🛑",
            "start_training": "🚀",
        }

        for rec in recommendations:
            icon = rec_type_icons.get(rec.get("rec_type"), "💡")
            desc = rec.get("description", "")
            conf = rec.get("confidence", 0.0)
            reasoning = rec.get("reasoning")
            suggested = rec.get("suggested_config")

            console.print(f"\n{icon} [bold]{desc}[/bold]")
            console.print(f"   Confidence: {conf:.0%}")
            if reasoning:
                console.print(f"   [dim]{reasoning}[/dim]")
            if suggested:
                console.print(f"   Suggested Config: {suggested}")

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except Exception as exc:
        console.print(f"[bold red]Error generating recommendations:[/bold red] {exc}")
        raise typer.Exit(code=1)
