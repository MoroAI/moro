"""
MoroAI Service Orchestrator CLI.
"""

from __future__ import annotations

import json

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.services.orchestrator import ServiceOrchestrator

console = Console()
app = typer.Typer(
    name="services",
    help="Background services management (Dashboard, Ollama, Webhook).",
    no_args_is_help=True,
)


@app.command("status")
def services_status_command(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Show status of all MoroAI background services."""
    orchestrator = ServiceOrchestrator()
    status = orchestrator.get_status()

    if json_output:
        typer.echo(json.dumps(status, indent=2))
        return

    table = Table(title="MoroAI Background Services", show_header=True)
    table.add_column("Service", style="bold")
    table.add_column("Port", justify="right", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("PID/Type", style="dim")
    table.add_column("URL", style="magenta")
    table.add_column("Description", style="dim")

    for name, s in status.items():
        state_str = "[green]● RUNNING[/green]" if s["running"] else "[red]○ STOPPED[/red]"
        pid_type = str(s.get("pid") or s.get("type") or "—")
        table.add_row(
            name,
            str(s["port"]),
            state_str,
            pid_type,
            s["url"],
            s["description"],
        )

    console.print(table)


@app.command("start")
def services_start_command(
    service: str = typer.Argument("all", help="Service name (all, dashboard, ollama, webhook)."),
) -> None:
    """Start one or all background services."""
    orchestrator = ServiceOrchestrator()
    services_to_start = ["dashboard", "ollama", "webhook"] if service.lower() == "all" else [service.lower()]

    for s in services_to_start:
        with console.status(f"[cyan]Starting {s}…[/cyan]"):
            ok = orchestrator.start_service(s)
        if ok:
            console.print(f"[bold green]✓[/bold green] Service [bold]{s}[/bold] started.")
        else:
            console.print(f"[bold yellow]⚠[/bold yellow] Could not start service [bold]{s}[/bold].")


@app.command("stop")
def services_stop_command(
    service: str = typer.Argument("all", help="Service name (all, dashboard, ollama, webhook)."),
) -> None:
    """Stop one or all background services."""
    orchestrator = ServiceOrchestrator()
    services_to_stop = ["dashboard", "ollama", "webhook"] if service.lower() == "all" else [service.lower()]

    for s in services_to_stop:
        with console.status(f"[cyan]Stopping {s}…[/cyan]"):
            ok = orchestrator.stop_service(s)
        if ok:
            console.print(f"[bold green]✓[/bold green] Service [bold]{s}[/bold] stopped.")
        else:
            console.print(f"[dim]Service {s} is not currently running or stopped.[/dim]")


@app.command("restart")
def services_restart_command(
    service: str = typer.Argument(..., help="Service name to restart (dashboard, ollama, webhook)."),
) -> None:
    """Restart a specific service."""
    orchestrator = ServiceOrchestrator()
    with console.status(f"[cyan]Restarting {service}…[/cyan]"):
        ok = orchestrator.restart_service(service)
    if ok:
        console.print(f"[bold green]✓[/bold green] Service [bold]{service}[/bold] restarted.")
    else:
        console.print(f"[bold yellow]⚠[/bold yellow] Failed to restart service [bold]{service}[/bold].")


@app.command("supervise")
def services_supervise_command() -> None:
    """Start the service supervisor (monitors and auto-restarts crashed services)."""
    orchestrator = ServiceOrchestrator()
    console.print("[bold cyan]Starting Service Supervisor[/bold cyan]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    orchestrator.start_all()
    orchestrator.supervise()


@app.command("logs")
def services_logs_command(
    service: str = typer.Argument(..., help="Service name (dashboard, ollama, webhook)."),
    tail: int = typer.Option(50, "--tail", "-n", help="Number of log lines to show."),
) -> None:
    """View recent logs for a service."""
    orchestrator = ServiceOrchestrator()
    logs = orchestrator.get_logs(service, tail=tail)
    console.print(Panel(logs, title=f"Logs: {service}", border_style="cyan"))


services_app = app

