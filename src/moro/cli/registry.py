"""
MoroAI Model Registry CLI.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.registry.manager import ModelRegistry

console = Console()
app = typer.Typer(
    name="registry",
    help="Model registry and lineage tracking.",
    no_args_is_help=True,
)


@app.command("list")
def list_models_command(
    tag: str | None = typer.Option(None, "--tag", "-t", help="Filter by tag (staging, production, candidate)."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """List registered models."""
    registry = ModelRegistry()
    models = registry.list_models(tag=tag)

    if json_output:
        typer.echo(json.dumps(models, indent=2))
        return

    if not models:
        console.print("[yellow]No models found in the registry.[/yellow]")
        return

    table = Table(title="MoroAI Model Registry", show_header=True)
    table.add_column("Model ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Base Model", style="dim")
    table.add_column("Tag", style="magenta")
    table.add_column("Val Loss", justify="right")
    table.add_column("Pass Rate", justify="right")
    table.add_column("Updated", style="dim")

    for m in models:
        loss_str = f"{m['val_loss']:.4f}" if m.get("val_loss") is not None else "—"
        pass_str = f"{m['pass_rate']:.1%}" if m.get("pass_rate") is not None else "—"
        table.add_row(
            m["model_id"],
            m["name"],
            m["base_model"],
            m["tag"],
            loss_str,
            pass_str,
            m["updated_at"][:19].replace("T", " "),
        )

    console.print(table)


@app.command("show")
def show_model_command(
    model_id: str = typer.Argument(..., help="Model ID to display."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show details of a registered model."""
    registry = ModelRegistry()
    model = registry.get_model(model_id)

    if not model:
        console.print(f"[bold red]Error:[/bold red] Model '{model_id}' not found.")
        raise typer.Exit(code=1)

    if json_output:
        typer.echo(json.dumps(model, indent=2))
        return

    loss_str = f"{model['val_loss']:.4f}" if model.get("val_loss") is not None else "N/A"
    pass_str = f"{model['pass_rate']:.1%}" if model.get("pass_rate") is not None else "N/A"

    console.print(
        Panel(
            f"[bold]Model ID:[/bold] {model['model_id']}\n"
            f"[bold]Name:[/bold] {model['name']}\n"
            f"[bold]Run ID:[/bold] {model['run_id']}\n"
            f"[bold]Base Model:[/bold] {model['base_model']}\n"
            f"[bold]Tag:[/bold] [bold magenta]{model['tag']}[/bold magenta]\n"
            f"[bold]Validation Loss:[/bold] {loss_str}\n"
            f"[bold]Eval Pass Rate:[/bold] {pass_str}\n"
            f"[bold]Artifacts:[/bold] {model.get('artifact_path') or 'N/A'}\n"
            f"[bold]Created:[/bold] {model['created_at']}\n"
            f"[bold]Updated:[/bold] {model['updated_at']}",
            title="Registered Model Details",
            border_style="cyan",
        )
    )


@app.command("promote")
def promote_model_command(
    model_id: str = typer.Argument(..., help="Model ID to promote."),
    tag: str = typer.Option("production", "--tag", "-t", help="Target tag (e.g. production, staging)."),
) -> None:
    """Promote a model to a target tag."""
    registry = ModelRegistry()
    success = registry.promote_model(model_id, target_tag=tag)
    if success:
        console.print(f"[bold green]✓[/bold green] Promoted model [bold]{model_id}[/bold] to [bold magenta]{tag}[/bold magenta].")
    else:
        console.print(f"[bold red]Error:[/bold red] Model '{model_id}' not found.")
        raise typer.Exit(code=1)


@app.command("delete")
def delete_model_command(
    model_id: str = typer.Argument(..., help="Model ID to delete."),
) -> None:
    """Delete a model from the registry."""
    registry = ModelRegistry()
    success = registry.delete_model(model_id)
    if success:
        console.print(f"[bold green]✓[/bold green] Deleted model [bold]{model_id}[/bold] from registry.")
    else:
        console.print(f"[bold red]Error:[/bold red] Model '{model_id}' not found.")
        raise typer.Exit(code=1)
