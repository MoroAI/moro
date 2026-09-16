import json

import typer
from rich.console import Console
from rich.table import Table

from moro.hardware.detector import detect_hardware
from moro.hardware.profile import HardwareProfile

console = Console()


def doctor_command(
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON.",
    ),
) -> None:
    """Check environment and hardware readiness."""
    with console.status("[cyan]Checking environment…[/cyan]"):
        raw = detect_hardware()

    profile = HardwareProfile.model_validate(raw)

    if json_output:
        typer.echo(json.dumps(profile.model_dump(), indent=2))
        return

    table = Table(title="MoroAI Environment Check", show_header=True)
    table.add_column("Check", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_column("Status", justify="center")

    def ok(v: str) -> tuple[str, str]:
        return v, "[green]✓[/green]"

    def warn(v: str) -> tuple[str, str]:
        return v, "[yellow]⚠[/yellow]"

    def fail(v: str) -> tuple[str, str]:
        return v, "[red]✗[/red]"

    table.add_row("Python version", *ok(profile.python_version))

    if profile.torch_version:
        table.add_row("PyTorch", *ok(profile.torch_version))
    else:
        table.add_row("PyTorch", *warn("not installed (optional for training)"))

    if profile.gpu_available:
        gpu_label = profile.gpu_name or profile.gpu_vendor
        table.add_row("GPU", *ok(f"{gpu_label} ({profile.gpu_vendor})"))
        table.add_row("VRAM", *ok(f"{profile.vram_gb:.1f} GB"))
    else:
        table.add_row("GPU", *warn("not detected — CPU mode only"))
        table.add_row("VRAM", *warn("N/A"))

    if profile.cuda_available:
        table.add_row("CUDA", *ok("available"))
    else:
        table.add_row("CUDA", *warn("not available"))

    table.add_row("CPU RAM", *ok(f"{profile.cpu_ram_gb:.1f} GB"))

    disk_val = f"{profile.disk_free_gb:.1f} GB free"
    if profile.disk_free_gb < 20:
        table.add_row("Disk", *warn(disk_val))
    else:
        table.add_row("Disk", *ok(disk_val))

    console.print(table)

    if profile.recommended_models:
        console.print("\n[bold]Recommended models for your hardware:[/bold]")
        for model in profile.recommended_models:
            console.print(f"  [cyan]•[/cyan] {model}")

    if profile.warnings:
        console.print("\n[bold yellow]Warnings:[/bold yellow]")
        for w in profile.warnings:
            console.print(f"  [yellow]⚠[/yellow]  {w}")

    has_critical = not profile.gpu_available and not profile.torch_version
    if has_critical:
        console.print(
            "\n[bold red]Critical:[/bold red] PyTorch is not installed. "
            "Install with: pip install 'moroai[train]'"
        )
        raise typer.Exit(code=3)
    else:
        console.print("\n[bold green]Environment check complete.[/bold green]")
