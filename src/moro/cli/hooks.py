"""
moro hooks — Git hooks and repository governance commands.

Provides the DevSecOps governance layer for MoroAI repositories.
Ensures every commit is scanned for hardcoded secrets and PII leaks
before reaching version control.

Commands:
  moro hooks install  — Install safety pre-commit hooks
  moro hooks check    — Run safety checks on all files (without committing)
  moro hooks uninstall — Remove MoroAI hooks
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from moro.core.errors import ProjectError
from moro.core.project import require_project_root

console = Console()
hooks_app = typer.Typer(
    name="hooks",
    help="Git hooks and repository governance commands.",
    no_args_is_help=True,
)


@hooks_app.command("install")
def install_hooks(
    force: bool = typer.Option(False, "--force", "-f", help="Reinstall even if hooks already exist."),
) -> None:
    """
    Install MoroAI safety and alignment pre-commit hooks.

    This ensures that every commit is automatically scanned for:
      • Hardcoded secrets (API keys, private keys, OAuth tokens)
      • PII leaks in dataset files (.jsonl, .csv, .json)
      • Unsafe eval configurations

    Requires the pre-commit package. MoroAI will install it automatically
    if not already present.
    """
    try:
        root = require_project_root()
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    pre_commit_config = root / ".pre-commit-config.yaml"
    if not pre_commit_config.exists():
        console.print(
            "[bold red]Error:[/bold red] .pre-commit-config.yaml not found in project root.\n"
            "Expected at: " + str(pre_commit_config) + "\n"
            "This file should have been created during moro init."
        )
        raise typer.Exit(code=1)

    console.print("[cyan]Installing pre-commit framework…[/cyan]")
    pip_result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "pre-commit", "--quiet"],
        capture_output=True,
        text=True,
    )
    if pip_result.returncode != 0:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] Could not auto-install pre-commit:\n"
            f"{pip_result.stderr}\n"
            "Please run: pip install pre-commit"
        )

    console.print("[cyan]Installing git hooks…[/cyan]")
    install_result = subprocess.run(
        ["pre-commit", "install", "--hook-type", "pre-commit"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )

    if install_result.returncode != 0:
        console.print(
            Panel(
                f"[bold red]Hook installation failed.[/bold red]\n\n"
                f"{install_result.stderr or install_result.stdout}\n\n"
                "Try running manually:\n  pre-commit install",
                border_style="red",
            )
        )
        raise typer.Exit(code=1)

    console.print(
        Panel(
            "[bold green]✓ MoroAI safety hooks installed.[/bold green]\n\n"
            "Every future commit will be automatically scanned for:\n"
            "  • Hardcoded secrets (API keys, tokens, private keys)\n"
            "  • PII leaks in dataset files\n"
            "  • Code quality issues (ruff lint + format)\n\n"
            f"Config: {pre_commit_config}",
            border_style="green",
            title="MoroAI DevSecOps",
        )
    )


@hooks_app.command("check")
def check_hooks(
    path: Path = typer.Argument(
        Path("."),
        help="Directory to scan (default: current directory).",
    ),
) -> None:
    """
    Run MoroAI safety checks on all files without committing.

    Useful for scanning an existing repository for secrets or PII
    that may have been committed before hooks were installed.
    """
    import os

    try:
        root = require_project_root()
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    script = root / "scripts" / "hooks" / "pre_commit_safety_check.py"
    if not script.exists():
        console.print(
            f"[bold red]Error:[/bold red] Safety check script not found at {script}"
        )
        raise typer.Exit(code=1)

    console.print("[cyan]Running MoroAI safety scan on all tracked files…[/cyan]\n")

    # Get all tracked files
    result = subprocess.run(
        ["git", "ls-files"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode != 0:
        console.print("[bold red]Error:[/bold red] Not a git repository or git not available.")
        raise typer.Exit(code=1)

    tracked_files = [f for f in result.stdout.strip().split("\n") if f]
    if not tracked_files:
        console.print("[dim]No tracked files found.[/dim]")
        return

    # Import and run the scanner directly
    sys.path.insert(0, str(root))
    try:
        from scripts.hooks.pre_commit_safety_check import check_pii_in_data, check_secrets
    except ImportError:
        console.print(
            "[bold red]Error:[/bold red] Cannot import safety check script. "
            "Ensure scripts/hooks/pre_commit_safety_check.py exists."
        )
        raise typer.Exit(code=1)

    all_violations: list[str] = []
    scanned = 0

    with console.status("[cyan]Scanning…[/cyan]"):
        for filepath in tracked_files:
            full = str(root / filepath)
            violations = check_secrets(full) + check_pii_in_data(full)
            all_violations.extend(violations)
            scanned += 1

    if all_violations:
        console.print(
            Panel(
                "\n".join(f"❌ {v}" for v in all_violations),
                title=f"[bold red]🚨 {len(all_violations)} Violation(s) Found[/bold red]",
                border_style="red",
            )
        )
        console.print(
            "\n[dim]Run [bold]moro guard redact <file>[/bold] to auto-redact PII from dataset files.[/dim]"
        )
        raise typer.Exit(code=1)
    else:
        console.print(
            f"[bold green]✓ Safety scan passed.[/bold green] "
            f"{scanned} file(s) scanned, no violations found."
        )


@hooks_app.command("uninstall")
def uninstall_hooks() -> None:
    """Remove MoroAI pre-commit hooks from this repository."""
    try:
        root = require_project_root()
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    result = subprocess.run(
        ["pre-commit", "uninstall"],
        capture_output=True,
        text=True,
        cwd=str(root),
    )
    if result.returncode == 0:
        console.print("[green]✓[/green] Pre-commit hooks uninstalled.")
    else:
        console.print(
            f"[bold yellow]Warning:[/bold yellow] Could not uninstall hooks automatically.\n"
            f"Remove .git/hooks/pre-commit manually.\n{result.stderr}"
        )
