"""
MoroAI Mission Control Dashboard CLI Commands.

Provides commands for:
- Starting the web dashboard (moro dashboard serve)
- Checking dashboard runtime status (moro dashboard status)
- Building and verifying static assets (moro dashboard build)
"""

from __future__ import annotations

import subprocess
import sys

import typer
from rich.console import Console
from rich.panel import Panel

from moro.core.errors import ProjectError
from moro.core.project import require_project_root

console = Console()
dashboard_app = typer.Typer(
    name="dashboard",
    help="MoroAI Mission Control Dashboard management.",
    no_args_is_help=False,
)


@dashboard_app.callback(invoke_without_command=True)
def dashboard_default(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind the dashboard to."),
    port: int = typer.Option(8501, "--port", "-p", help="Port to bind the dashboard to."),
    gateway: bool = typer.Option(False, "--gateway", help="Also start the feedback gateway."),
    gateway_port: int = typer.Option(8000, "--gateway-port", help="Port for the feedback gateway."),
    open_browser: bool = typer.Option(False, "--open/--no-open", help="Open browser automatically."),
) -> None:
    """Start the Mission Control Dashboard when invoked without subcommand."""
    if ctx.invoked_subcommand is None:
        dashboard_serve(
            host=host,
            port=port,
            gateway=gateway,
            gateway_port=gateway_port,
            open_browser=open_browser,
        )


@dashboard_app.command("serve")
def dashboard_serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind the dashboard to."),
    port: int = typer.Option(8501, "--port", "-p", help="Port to bind the dashboard to."),
    gateway: bool = typer.Option(False, "--gateway", help="Also start the feedback gateway."),
    gateway_port: int = typer.Option(8000, "--gateway-port", help="Port for the feedback gateway."),
    open_browser: bool = typer.Option(False, "--open/--no-open", help="Open browser automatically."),
) -> None:
    """
    Start the MoroAI Mission Control Dashboard.

    Provides a rich interactive web UI to:
    - Upload datasets with drag-and-drop
    - Start/stop training runs and track loss telemetry
    - Compare models and promote to production
    - Deploy to Ollama and test with sample prompts
    - Inspect continuous learning DPO preference pairs
    - Execute CLI commands from an embedded terminal
    """
    try:
        root = require_project_root()

        console.print(
            Panel(
                f"[bold cyan]MoroAI Mission Control Dashboard[/bold cyan]\n\n"
                f"Dashboard URL: [bold green]http://{host}:{port}[/bold green]\n"
                f"API Docs:      [cyan]http://{host}:{port}/docs[/cyan]\n"
                f"Gateway:       {'http://' + host + ':' + str(gateway_port) if gateway else '[dim]Disabled[/dim]'}\n\n"
                f"Press [bold red]Ctrl+C[/bold red] to stop.",
                border_style="blue",
            )
        )

        gateway_proc = None
        if gateway:
            console.print(f"[yellow]Starting Feedback Gateway on port {gateway_port}...[/yellow]")
            gateway_proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "moro.dashboard.gateway:gateway_app",
                    "--host",
                    host,
                    "--port",
                    str(gateway_port),
                ],
                cwd=root,
            )

        if open_browser:
            import webbrowser

            webbrowser.open(f"http://{host}:{port}")

        try:
            import uvicorn

            from moro.dashboard.mission_control import app as mission_app

            uvicorn.run(mission_app, host=host, port=port, log_level="info")
        finally:
            if gateway_proc:
                gateway_proc.terminate()

    except ProjectError as exc:
        console.print(f"[bold red]Project error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped.[/yellow]")


@dashboard_app.command("build")
def dashboard_build() -> None:
    """Build and verify dashboard template assets."""
    console.print("[cyan]Verifying dashboard assets...[/cyan]")
    from moro.dashboard.utils import get_project_root

    root = get_project_root()
    template_path = root / "src" / "moro" / "dashboard" / "templates" / "mission_control.html"
    if template_path.exists():
        size_kb = template_path.stat().st_size / 1024
        console.print(f"[green]✓ Dashboard template verified ({size_kb:.1f} KB)[/green]")
    else:
        console.print("[yellow]Template file not found at default path.[/yellow]")


@dashboard_app.command("status")
def dashboard_status(
    host: str = typer.Option("127.0.0.1", "--host", help="Host to check"),
    port: int = typer.Option(8501, "--port", help="Port to check"),
) -> None:
    """Check if the dashboard is actively responding."""
    import httpx

    target_url = f"http://{host}:{port}/api/health"
    try:
        resp = httpx.get(target_url, timeout=3.0)
        if resp.status_code == 200:
            console.print(f"[bold green]✓ Dashboard is online and healthy[/bold green] at http://{host}:{port}")
        else:
            console.print(f"[yellow]○ Dashboard returned status code {resp.status_code}[/yellow]")
    except Exception:
        console.print(f"[red]✗ Dashboard is not reachable at http://{host}:{port}[/red]")
        console.print("[dim]Launch with: moro dashboard[/dim]")
