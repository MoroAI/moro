from pathlib import Path

import typer
from rich.console import Console

from moro.core.errors import ProjectError
from moro.core.paths import CONFIG_FILE, ensure_project_dirs
from moro.templates.project import (
    DEFAULT_GITIGNORE,
    SAMPLE_EVAL_YAML,
    default_moro_yaml,
    readme_template,
)

console = Console()


def sanitize_project_name(name: str) -> str:
    """Convert a directory name to a valid project name slug."""
    cleaned = name.strip().lower().replace(" ", "-")
    cleaned = "".join(ch for ch in cleaned if ch.isalnum() or ch in {"-", "_"})
    return cleaned or "moro-project"


def init_command(
    path: Path = typer.Argument(
        default=Path("."),
        help="Directory where the MoroAI project will be created.",
    ),
    template: str = typer.Option(
        "minimal",
        help="Project template to use (currently: minimal).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite existing project files.",
    ),
) -> None:
    """Initialize a new MoroAI project."""
    try:
        if template not in {"minimal"}:
            console.print(
                f"[yellow]Warning:[/yellow] template '{template}' is not implemented yet. "
                "Falling back to 'minimal'."
            )

        root = Path(path).expanduser().resolve()
        config_path = root / CONFIG_FILE

        if config_path.exists() and not force:
            raise ProjectError(
                f"A MoroAI project already exists at {root}. Use --force to overwrite."
            )

        root.mkdir(parents=True, exist_ok=True)
        dirs = ensure_project_dirs(root)

        project_name = sanitize_project_name(root.name)

        files: dict[Path, str] = {
            root / "moro.yaml": default_moro_yaml(project_name),
            root / "README.md": readme_template(project_name),
            root / ".gitignore": DEFAULT_GITIGNORE,
            dirs["eval"] / "support-golden-v1.yaml": SAMPLE_EVAL_YAML,
            dirs["raw"] / ".gitkeep": "",
            dirs["moro"] / ".gitkeep": "",
        }

        for file_path, content in files.items():
            if file_path.exists() and not force:
                console.print(f"[dim]Skipping (exists):[/dim] {file_path.relative_to(root)}")
                continue

            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            console.print(f"[green]Created:[/green]  {file_path.relative_to(root)}")

        console.print(
            f"\n[bold green]✓[/bold green] MoroAI project initialized at: [bold]{root}[/bold]"
        )
        console.print("\n[bold]Next steps:[/bold]")
        console.print("  1. Add your raw dataset to [cyan]data/raw/[/cyan]")
        console.print("  2. Update [cyan]moro.yaml[/cyan] with your model and dataset settings")
        console.print("  3. Run [bold]moro doctor[/bold] to verify your environment")
        console.print("  4. Run [bold]moro import[/bold] to register your data")

    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
