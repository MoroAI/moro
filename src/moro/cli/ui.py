"""
MoroAI UI CLI command.
"""

from __future__ import annotations

import typer
from rich.console import Console

from moro.core.net import NonLoopbackBindError, check_bind_host

console = Console()


def ui_command(
    port: int = typer.Option(8501, "--port", "-p", help="Port to run the dashboard on."),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind to."),
    allow_non_loopback: bool = typer.Option(
        False,
        "--allow-non-loopback",
        help="Allow binding to a non-loopback address (exposes the dashboard to the network).",
    ),
) -> None:
    """Launch the MoroAI Mission Control Web Dashboard."""
    try:
        warning = check_bind_host(host, allow_non_loopback=allow_non_loopback)
    except NonLoopbackBindError as exc:
        console.print(f"[bold red]Refused:[/bold red] {exc}")
        raise typer.Exit(code=2)
    if warning:
        console.print(f"[bold yellow]Warning:[/bold yellow] {warning}")
    console.print(
        f"\n[bold green]✓ Launching MoroAI Mission Control[/bold green] at "
        f"[bold cyan]http://{host}:{port}[/bold cyan]\n"
    )
    console.print("Press [bold red]Ctrl+C[/bold red] to stop.\n")
    try:
        import uvicorn

        from moro.dashboard.mission_control import app as mission_app
    except ImportError:
        console.print(
            "[bold red]Cannot start dashboard:[/bold red] uvicorn/fastapi are not installed. "
            "Install the dashboard dependencies instead of running an unauthenticated fallback."
        )
        raise typer.Exit(code=2)
    uvicorn.run(mission_app, host=host, port=port, log_level="info")
