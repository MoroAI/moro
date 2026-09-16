from pathlib import Path

import typer
from rich.console import Console

from moro.core.errors import ExportError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.export.ollama import generate_ollama_package
from moro.storage import db as storage_db

console = Console()


def deploy_command(
    target: str = typer.Option(
        "ollama",
        "--target",
        help="Deployment target: ollama.",
    ),
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID to deploy."),
    tag: str | None = typer.Option(None, "--tag", help="Version tag (e.g. v0.1.0)."),
) -> None:
    """Prepare local deployment artifacts."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        conn = storage_db.get_connection(root)
        project_id = storage_db.get_or_create_project(conn, cfg.project.name)

        if run_id:
            run_row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        else:
            run_row = storage_db.get_latest_run(conn, project_id)

        conn.close()

        if not run_row:
            console.print("[red]No completed run found. Run `moro train` first.[/red]")
            raise typer.Exit(code=1)

        resolved_run_id = run_row["id"]
        run_dir = Path(run_row["output_dir"])
        adapter_path = run_dir / "adapter"

        version = tag or "latest"
        out_dir = root / "releases" / f"{resolved_run_id}_{version}"

        if target == "ollama":
            console.print(
                f"[cyan]→[/cyan]  Building Ollama package for: [bold]{cfg.project.name}[/bold]"
            )
            pkg_dir = generate_ollama_package(
                adapter_path=adapter_path,
                base_model=cfg.model.name,
                project_name=cfg.project.name,
                out_dir=out_dir,
            )
            console.print(
                f"\n[bold green]✓[/bold green] Ollama package created: [bold]{pkg_dir}[/bold]"
            )
            console.print("\n[bold]To deploy:[/bold]")
            model_slug = cfg.project.name.lower().replace(" ", "-")
            console.print(f"  [cyan]ollama create {model_slug} -f {pkg_dir / 'Modelfile'}[/cyan]")
            console.print(f"  [cyan]ollama run {model_slug}[/cyan]")

        elif target == "gguf":
            console.print(
                "[yellow]GGUF export is not yet implemented in this MVP.[/yellow]\n"
                "Use llama.cpp's convert_hf_to_gguf.py manually with the merged model."
            )
        else:
            console.print(f"[red]Unknown target: {target}[/red]")
            raise typer.Exit(code=1)

    except ExportError as exc:
        console.print(f"[bold red]Export error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except ProjectError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
