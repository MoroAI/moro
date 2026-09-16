import shutil
from pathlib import Path

import typer
from rich.console import Console

from moro.core.errors import DatasetError, ProjectError
from moro.core.hashing import sha256_file
from moro.core.project import require_project_root
from moro.storage import db as storage_db

console = Console()


def import_command(
    source: Path = typer.Argument(
        ...,
        help="Path to a dataset file or directory to import.",
        exists=True,
    ),
    name: str | None = typer.Option(
        None,
        "--name",
        help="Dataset source name (defaults to filename).",
    ),
    format: str = typer.Option(
        "auto",
        "--format",
        help="Dataset format: auto, jsonl, csv, txt, markdown.",
    ),
    copy: bool = typer.Option(
        True,
        "--copy/--link",
        help="Copy file to data/raw/ (default) or symlink it.",
    ),
) -> None:
    """Import raw dataset files into the project."""
    try:
        root = require_project_root()
        source = source.expanduser().resolve()

        # Determine destination inside data/raw/
        raw_dir = root / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        dest = raw_dir / source.name
        source_name = name or source.stem

        if source == dest.resolve():
            file_hash = sha256_file(source) if source.is_file() else ""
            if source.is_dir():
                from moro.core.hashing import sha256_text

                file_hash = sha256_text(
                    "".join(sha256_file(f) for f in sorted(source.rglob("*")) if f.is_file())
                )
            source_type = "directory" if source.is_dir() else source.suffix.lstrip(".")
        elif dest.exists() or dest.is_symlink():
            raise DatasetError(f"Import destination already exists: {dest}")
        elif source.is_dir():
            if copy:
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(source, dest)
                console.print(f"[green]Copied directory:[/green] {source.name} → data/raw/")
            else:
                if dest.exists():
                    dest.unlink()
                dest.symlink_to(source)
                console.print(f"[green]Linked directory:[/green] {source.name} → data/raw/")

            # Compute a hash of all files combined
            all_files = sorted(dest.rglob("*"))
            combined = "".join(sha256_file(f) for f in all_files if f.is_file())
            import hashlib

            file_hash = hashlib.sha256(combined.encode()).hexdigest()
            source_type = "directory"
        else:
            if copy:
                shutil.copy2(source, dest)
                console.print(f"[green]Copied:[/green] {source.name} → data/raw/")
            else:
                if dest.exists():
                    dest.unlink()
                dest.symlink_to(source)
                console.print(f"[green]Linked:[/green] {source.name} → data/raw/")

            file_hash = sha256_file(dest)
            source_type = format if format != "auto" else source.suffix.lstrip(".") or "auto"

        # Persist to DB
        from moro.config.loader import load_config
        from moro.core.paths import CONFIG_FILE

        config = load_config(root / CONFIG_FILE)
        conn = storage_db.get_connection(root)

        project_id = storage_db.get_or_create_project(
            conn, config.project.name, config.project.privacy_mode
        )

        source_id = storage_db.get_or_create_dataset_source(
            conn=conn,
            project_id=project_id,
            name=source_name,
            source_type=source_type,
            path=str(dest),
            sha256=file_hash,
        )
        conn.close()

        console.print(
            f"[bold green]✓[/bold green] Registered dataset source: [cyan]{source_name}[/cyan] "
            f"(id: {source_id})"
        )
        console.print(
            "\n[bold]Next step:[/bold] Run [bold]moro data build[/bold] "
            "to normalize and split the dataset."
        )

    except (ProjectError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
