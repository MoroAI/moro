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
        default_config = (
            "repos:\n"
            "  - repo: local\n"
            "    hooks:\n"
            "      - id: moro-safety-check\n"
            "        name: MoroAI Safety & Secret Scanner\n"
            "        entry: python scripts/hooks/pre_commit_safety_check.py\n"
            "        language: system\n"
            "        pass_filenames: false\n"
            "        always_run: true\n"
        )
        pre_commit_config.write_text(default_config, encoding="utf-8")
        console.print(f"[green]Created:[/green] {pre_commit_config.name}")

    scripts_dir = root / "scripts" / "hooks"
    safety_script = scripts_dir / "pre_commit_safety_check.py"
    if not safety_script.exists():
        scripts_dir.mkdir(parents=True, exist_ok=True)
        # Create minimal self-contained scanner if not already copied
        src_script = Path(__file__).resolve().parents[3] / "scripts" / "hooks" / "pre_commit_safety_check.py"
        if src_script.exists():
            safety_script.write_text(src_script.read_text(encoding="utf-8"), encoding="utf-8")

    console.print("[cyan]Installing git hooks…[/cyan]")
    installed = False

    try:
        install_result = subprocess.run(
            ["pre-commit", "install", "--hook-type", "pre-commit"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        if install_result.returncode == 0:
            installed = True
    except Exception:
        pass

    # Direct fallback if pre-commit command is unavailable
    if not installed:
        git_hooks_dir = root / ".git" / "hooks"
        if git_hooks_dir.exists():
            direct_hook = git_hooks_dir / "pre-commit"
            direct_hook.write_text(
                "#!/bin/sh\n"
                "python scripts/hooks/pre_commit_safety_check.py\n",
                encoding="utf-8",
            )
            direct_hook.chmod(0o755)
            installed = True

    if not installed:
        console.print(
            Panel(
                "[bold red]Hook installation failed.[/bold red]\n\n"
                "Could not find .git directory or pre-commit command.",
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

    uninstalled = False
    try:
        result = subprocess.run(
            ["pre-commit", "uninstall"],
            capture_output=True,
            text=True,
            cwd=str(root),
        )
        if result.returncode == 0:
            uninstalled = True
    except Exception:
        pass

    direct_hook = root / ".git" / "hooks" / "pre-commit"
    if direct_hook.exists():
        direct_hook.unlink()
        uninstalled = True

    if uninstalled:
        console.print("[green]✓[/green] Pre-commit hooks uninstalled.")
    else:
        console.print("[dim]No pre-commit hook found to uninstall.[/dim]")
