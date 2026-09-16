"""
Structured logging helpers using Rich.
All MoroAI CLI output should go through these helpers to maintain consistent style.
"""

from rich.console import Console

_console = Console()
_err_console = Console(stderr=True)


def info(msg: str) -> None:
    """Print an informational message."""
    _console.print(msg)


def success(msg: str) -> None:
    """Print a success message (bold green)."""
    _console.print(f"[bold green]✓[/bold green] {msg}")


def warning(msg: str) -> None:
    """Print a warning message (yellow)."""
    _console.print(f"[yellow]⚠[/yellow]  {msg}")


def error(msg: str) -> None:
    """Print an error message to stderr (bold red)."""
    _err_console.print(f"[bold red]✗[/bold red] {msg}")


def step(msg: str) -> None:
    """Print a step/progress message (cyan)."""
    _console.print(f"[cyan]→[/cyan]  {msg}")


def dim(msg: str) -> None:
    """Print a dimmed/secondary message."""
    _console.print(f"[dim]{msg}[/dim]")


def get_console() -> Console:
    """Return the shared console for Rich tables, etc."""
    return _console
