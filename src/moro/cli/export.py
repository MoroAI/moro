from pathlib import Path

import typer
from rich.console import Console

from moro.core.errors import ExportError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.export.manifest import (
    export_adapter,
    generate_manifest,
    generate_model_card,
    write_manifest,
    write_model_card,
)
from moro.storage import db as storage_db

console = Console()


def export_command(
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID to export."),
    format: str = typer.Option(
        "adapter",
        "--format",
        help="Export format: adapter, ollama.",
    ),
    out: Path | None = typer.Option(None, "--out", help="Output directory."),
) -> None:
    """Export artifacts from a training run."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        conn = storage_db.get_connection(root)
        project_id = storage_db.get_or_create_project(conn, cfg.project.name)

        # Resolve run
        if run_id:
            run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        else:
            run_row = storage_db.get_latest_run(conn, project_id)

        if not run_row:
            console.print("[red]No completed run found. Run `moro train` first.[/red]")
            raise typer.Exit(code=1)

        resolved_run_id = run_row["id"]
        run_dir = Path(run_row["output_dir"])
        out_dir = out or root / "releases" / resolved_run_id

        console.print(f"[cyan]→[/cyan]  Exporting run: [bold]{resolved_run_id}[/bold]")
        console.print(f"[cyan]→[/cyan]  Format: [bold]{format}[/bold]")

        if format == "adapter":
            adapter_dest = export_adapter(run_dir, out_dir)

            manifest = generate_manifest(
                project_name=cfg.project.name,
                run_id=resolved_run_id,
                base_model=cfg.model.name,
                artifact_paths=[],
                eval_summary={},
            )
            manifest_path = write_manifest(manifest, out_dir)

            card_content = generate_model_card(
                project_name=cfg.project.name,
                model_name=cfg.model.name,
                run_id=resolved_run_id,
            )
            card_path = write_model_card(card_content, out_dir)

            console.print(f"[green]✓[/green] Adapter:    {adapter_dest}")
            console.print(f"[green]✓[/green] Manifest:   {manifest_path}")
            console.print(f"[green]✓[/green] Model card: {card_path}")

        elif format == "ollama":
            from moro.export.ollama import generate_ollama_package

            adapter_path = run_dir / "adapter"
            pkg_dir = generate_ollama_package(
                adapter_path=adapter_path,
                base_model=cfg.model.name,
                project_name=cfg.project.name,
                out_dir=out_dir,
            )
            console.print(f"[green]✓[/green] Ollama package: {pkg_dir}")
            console.print("\n[bold]To deploy:[/bold]")
            console.print(f"  ollama create {cfg.project.name} -f {pkg_dir / 'Modelfile'}")
            console.print(f"  ollama run {cfg.project.name}")

        else:
            console.print(f"[red]Unknown format: {format}[/red]")
            raise typer.Exit(code=1)

        conn.close()

    except ExportError as exc:
        console.print(f"[bold red]Export error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
