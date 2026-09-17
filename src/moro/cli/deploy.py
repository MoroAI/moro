import typer
from rich.console import Console

from moro.core.errors import ConfigError, ExportError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.export.eligibility import resolve_export_run
from moro.export.gates import check_release_requirements, write_gate_report
from moro.export.ollama import generate_ollama_package

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

        if target != "ollama":
            raise ExportError(f"Unsupported deployment target: {target}")
        selected = resolve_export_run(root, cfg.project.name, run_id)
        gate = check_release_requirements(root, selected, cfg)
        resolved_run_id = selected.id
        adapter_path = selected.adapter_path

        version = tag or "latest"
        out_dir = root / "releases" / f"{resolved_run_id}_{version}"

        if target == "ollama":
            console.print(
                f"[cyan]→[/cyan]  Building Ollama package for: [bold]{cfg.project.name}[/bold]"
            )
            pkg_dir = generate_ollama_package(
                adapter_path=adapter_path,
                base_model=selected.config.model.name,
                project_name=cfg.project.name,
                out_dir=out_dir,
            )
            write_gate_report(gate, pkg_dir)
            console.print(
                f"\n[bold green]✓[/bold green] Ollama package created: [bold]{pkg_dir}[/bold]"
            )
            console.print("\n[bold]To deploy:[/bold]")
            model_slug = cfg.project.name.lower().replace(" ", "-")
            console.print(f"  [cyan]ollama create {model_slug} -f {pkg_dir / 'Modelfile'}[/cyan]")
            console.print(f"  [cyan]ollama run {model_slug}[/cyan]")

    except ExportError as exc:
        console.print(f"[bold red]Export error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except (ProjectError, ConfigError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
