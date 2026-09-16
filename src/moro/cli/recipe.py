import typer
from rich.console import Console
from rich.table import Table

from moro.hardware.detector import detect_hardware
from moro.hardware.profile import HardwareProfile
from moro.recipes.engine import suggest_recipe

app = typer.Typer(name="recipe", help="Recipe suggestion.")
console = Console()


@app.command("suggest")
def suggest_command(
    model: str | None = typer.Option(
        None,
        "--model",
        help="Override the suggested model name.",
    ),
    target_vram: float | None = typer.Option(
        None,
        "--target-vram",
        min=0,
        help="Override VRAM budget in GB (e.g. 8.0).",
    ),
    max_seq_length: int | None = typer.Option(
        None,
        "--max-seq-length",
        min=16,
        max=32768,
        help="Override maximum sequence length.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output as JSON.",
    ),
) -> None:
    """Suggest a hardware-safe training recipe."""
    with console.status("[cyan]Detecting hardware…[/cyan]"):
        raw = detect_hardware()

    hardware = HardwareProfile.model_validate(raw)
    try:
        suggestion = suggest_recipe(
            hardware=hardware,
            model_name=model,
            target_vram=target_vram,
            max_seq_length=max_seq_length,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if json_output:
        import json

        typer.echo(json.dumps(suggestion.model_dump(), indent=2))
        return

    table = Table(title="Suggested Training Recipe", show_header=True)
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Model", suggestion.model)
    table.add_row("Hardware tier", suggestion.hardware_tier)
    table.add_row("Quantization", suggestion.quantization)
    table.add_row("LoRA rank (r)", str(suggestion.adapter_r))
    table.add_row("LoRA alpha", str(suggestion.adapter_alpha))
    table.add_row("Target modules", ", ".join(suggestion.target_modules))
    table.add_row("Max sequence length", str(suggestion.max_seq_length))
    table.add_row("Batch size", str(suggestion.batch_size))
    table.add_row("Gradient accumulation", str(suggestion.gradient_accumulation_steps))
    table.add_row(
        "Effective batch size", str(suggestion.batch_size * suggestion.gradient_accumulation_steps)
    )
    table.add_row("Optimizer", suggestion.optimizer)
    table.add_row("Gradient checkpointing", str(suggestion.gradient_checkpointing))
    table.add_row("Precision", suggestion.precision)
    table.add_row("Est. VRAM usage", f"{suggestion.estimated_vram_gb:.1f} GB")
    table.add_row(
        "Confidence",
        suggestion.confidence,
    )

    console.print(table)

    if suggestion.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in suggestion.warnings:
            console.print(f"  [yellow]⚠[/yellow]  {w}")

    console.print(
        "\n[dim]Apply this recipe by updating your moro.yaml, then run "
        "[bold]moro train[/bold][/dim]"
    )
