"""
MoroAI UI CLI command.
"""

from __future__ import annotations

import typer
from rich.console import Console

from moro.ui.server import start_server

console = Console()


def ui_command(
    port: int = typer.Option(8765, "--port", "-p", help="Port to run the dashboard on."),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind to."),
) -> None:
    """Launch the MoroAI Mission Control Web Dashboard."""
    console.print(
        f"\n[bold green]✓ Launching MoroAI Mission Control[/bold green] at "
        f"[bold cyan]http://{host}:{port}[/bold cyan]\n"
    )
    console.print("Press [bold red]Ctrl+C[/bold red] to stop.\n")
    server = start_server(host=host, port=port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")
    finally:
        server.server_close()
