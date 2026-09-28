"""
moro guard — PII and Secrets Guard CLI.

Provides first-class data privacy commands:
  moro guard scan    — Scan a file or project dataset for PII and secrets
  moro guard redact  — Redact detected PII/secrets with safe placeholders
  moro guard check   — Exit code 0 if clean, 1 if PII found (for CI/hooks)
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from moro.core.errors import DatasetError, ProjectError
from moro.core.project import find_project_root, load_project_config
from moro.data.privacy import _PATTERNS, redact_text

console = Console()
app = typer.Typer(
    name="guard",
    help="PII and secrets scanning and redaction.",
    no_args_is_help=True,
)


def _resolve_target_file(file_path: Path | None) -> Path:
    if file_path:
        if not file_path.exists():
            raise DatasetError(f"Target file not found: {file_path}")
        return file_path

    root = find_project_root()
    if not root:
        raise ProjectError("Not in a MoroAI project and no file path provided.")

    cfg = load_project_config()
    source = cfg.dataset.source
    if not source.is_absolute():
        source = root / source
    if not source.exists():
        raise DatasetError(f"Project dataset source not found: {source}")
    return source


@app.command("scan")
def scan_command(
    file_path: Path | None = typer.Argument(
        None,
        help="Path to JSONL/CSV/text file to scan (defaults to project dataset source).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
) -> None:
    """Scan a dataset or file for PII and leaked secrets."""
    try:
        target = _resolve_target_file(file_path)
        if not json_output:
            console.print(f"[cyan]→[/cyan]  Scanning for PII & secrets in: [bold]{target}[/bold]")

        leaks: list[dict] = []
        flag_counts: dict[str, int] = {}
        total_lines = 0

        with target.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, 1):
                total_lines += 1
                found_in_line = []
                for flag_name, pattern in _PATTERNS:
                    matches = pattern.findall(line)
                    if matches:
                        flag_counts[flag_name] = flag_counts.get(flag_name, 0) + len(matches)
                        found_in_line.append(flag_name)
                if found_in_line:
                    leaks.append(
                        {
                            "line": line_no,
                            "types": found_in_line,
                            "snippet": line.strip()[:80] + ("…" if len(line.strip()) > 80 else ""),
                        }
                    )

        total_leaks = sum(flag_counts.values())

        if json_output:
            typer.echo(
                json.dumps(
                    {
                        "target": str(target),
                        "total_lines": total_lines,
                        "total_leaks": total_leaks,
                        "flag_counts": flag_counts,
                        "leaks": leaks[:100],
                    },
                    indent=2,
                )
            )
            return

        if not leaks:
            console.print(
                Panel(
                    f"[bold green]✓ No PII or secrets detected across {total_lines} lines.[/bold green]\n"
                    "Dataset is safe for training.",
                    title="Privacy Guard Clean",
                    border_style="green",
                )
            )
            return

        console.print(
            Panel(
                f"[bold red]⚠  {total_leaks} potential PII/secret matches found across {len(leaks)} lines.[/bold red]\n"
                "Use [bold]moro guard redact[/bold] to clean these before training or publishing.",
                title="Privacy Guard Alert",
                border_style="red",
            )
        )

        table = Table(title="Detected Leak Summary", show_header=True)
        table.add_column("Category", style="cyan")
        table.add_column("Count", justify="right")

        for cat, cnt in sorted(flag_counts.items(), key=lambda x: -x[1]):
            table.add_row(cat, str(cnt))

        console.print(table)

        if leaks:
            sample_table = Table(title="Sample Detected Lines", show_header=True)
            sample_table.add_column("Line", justify="right", style="dim")
            sample_table.add_column("Types", style="yellow")
            sample_table.add_column("Snippet", style="white")

            for item in leaks[:10]:
                sample_table.add_row(str(item["line"]), ", ".join(item["types"]), item["snippet"])

            console.print(sample_table)
            if len(leaks) > 10:
                console.print(
                    f"[dim]... and {len(leaks) - 10} more lines with potential leaks.[/dim]"
                )

    except (ProjectError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("redact")
def redact_command(
    file_path: Path | None = typer.Argument(
        None,
        help="File to redact (defaults to project dataset source).",
    ),
    output: Path | None = typer.Option(
        None,
        "--output",
        "-o",
        help="Path for redacted output (defaults to stdout or specified file).",
    ),
    in_place: bool = typer.Option(
        False,
        "--in-place",
        "-i",
        help="Overwrite the target file in-place with redacted content.",
    ),
) -> None:
    """Redact PII and secrets with safe semantic placeholders."""
    try:
        target = _resolve_target_file(file_path)

        if in_place and output:
            raise DatasetError("Cannot specify both --in-place and --output.")

        out_path = target if in_place else output

        redacted_lines: list[str] = []
        total_redactions = 0
        redaction_counts: dict[str, int] = {}

        with target.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                new_line, flags = redact_text(line)
                redacted_lines.append(new_line)
                for flag in flags:
                    redaction_counts[flag] = redaction_counts.get(flag, 0) + 1
                    total_redactions += 1

        if out_path:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with out_path.open("w", encoding="utf-8") as f:
                f.writelines(redacted_lines)
            console.print(
                f"[bold green]✓[/bold green] Redacted {total_redactions} PII/secrets. "
                f"Saved to: [bold]{out_path}[/bold]"
            )
        else:
            # Print to stdout
            for line in redacted_lines:
                print(line, end="")

    except (ProjectError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("check")
def check_command(
    file_path: Path | None = typer.Argument(
        None,
        help="File to verify (exits 0 if clean, 1 if PII found).",
    ),
) -> None:
    """Headless check: exit 0 if clean, exit 1 if PII found (for CI/pre-commit)."""
    try:
        target = _resolve_target_file(file_path)
        found = False

        with target.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                for _, pattern in _PATTERNS:
                    if pattern.search(line):
                        found = True
                        break
                if found:
                    break

        if found:
            console.print(f"[bold red]FAIL:[/bold red] PII or secret patterns detected in {target}")
            raise typer.Exit(code=1)
        else:
            console.print(f"[bold green]PASS:[/bold green] {target} is clean.")
            raise typer.Exit(code=0)

    except (ProjectError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
