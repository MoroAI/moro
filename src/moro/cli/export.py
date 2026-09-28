from pathlib import Path

import typer
from rich.console import Console

from moro.core.errors import ConfigError, DependencyError, ExportError, ProjectError
from moro.core.hashing import sha256_directory, sha256_file
from moro.core.project import load_project_config, require_project_root
from moro.export.eligibility import resolve_export_run
from moro.export.gates import check_release_requirements, write_gate_report
from moro.export.manifest import (
    export_adapter,
    generate_manifest,
    generate_model_card,
    write_manifest,
    write_model_card,
)
from moro.storage import db

console = Console()

_FORMATS = ("adapter", "ollama", "merged", "gguf")


def export_command(
    run_id: str | None = typer.Option(None, "--run-id", help="Run ID to export."),
    format: str = typer.Option(
        "adapter",
        "--format",
        help=f"Export format: {', '.join(_FORMATS)}.",
    ),
    out: Path | None = typer.Option(None, "--out", help="Output directory."),
    dtype: str = typer.Option(
        "auto",
        "--dtype",
        help="Dtype for merged model (auto, float16, bfloat16, float32). Ignored for adapter format.",
    ),
    llama_cpp: Path | None = typer.Option(
        None,
        "--llama-cpp",
        help="Path to llama.cpp checkout for direct GGUF conversion.",
    ),
    gguf_quantization: str = typer.Option(
        "q4_k_m",
        "--gguf-quant",
        help="GGUF quantization type (q4_k_m, q5_k_m, q8_0, f16).",
    ),
) -> None:
    """Export artifacts from a training run."""
    try:
        root = require_project_root()
        cfg = load_project_config()

        if format not in _FORMATS:
            raise ExportError(
                f"Unsupported export format: {format}. Choose from: {', '.join(_FORMATS)}"
            )

        selected = resolve_export_run(root, cfg.project.name, run_id)
        gate = check_release_requirements(root, selected, cfg)
        resolved_run_id = selected.id
        run_dir = selected.directory
        out_dir = out or root / "releases" / resolved_run_id

        console.print(f"[cyan]→[/cyan]  Exporting run: [bold]{resolved_run_id}[/bold]")
        console.print(f"[cyan]→[/cyan]  Format: [bold]{format}[/bold]")
        if gate["status"] == "passed":
            console.print(
                f"[green]✓[/green] Release gate: passed ({len(gate['evaluations'])} evaluation(s) verified)"
            )
        else:
            console.print("[dim]ℹ  Release gate: not required[/dim]")

        if format == "adapter":
            adapter_dest = export_adapter(run_dir, out_dir)
            if sha256_directory(adapter_dest) != gate["adapter_sha256"]:
                raise ExportError(
                    "Copied adapter differs from checked evidence; release not published."
                )

            manifest = generate_manifest(
                project_name=cfg.project.name,
                run_id=resolved_run_id,
                base_model=selected.config.model.name,
                artifact_paths=sorted(p for p in adapter_dest.rglob("*") if p.is_file()),
                eval_summary={"evaluations": gate["evaluations"], "gate_status": gate["status"]},
                dataset_version_id=selected.dataset_version_id,
                base_model_revision=selected.config.model.revision,
            )
            for artifact in manifest["artifacts"]:
                artifact["path"] = str(Path(artifact["path"]).relative_to(out_dir))
            manifest["release_gate"] = gate
            manifest_path = write_manifest(manifest, out_dir)

            card_content = generate_model_card(
                project_name=cfg.project.name,
                model_name=selected.config.model.name,
                run_id=resolved_run_id,
                eval_summary={"gate_status": gate["status"], "evaluations": gate["evaluations"]},
            )
            card_path = write_model_card(card_content, out_dir)
            conn = db.get_connection(root)
            try:
                for path in [
                    *sorted(p for p in adapter_dest.rglob("*") if p.is_file()),
                    manifest_path,
                    card_path,
                ]:
                    db.add_artifact(
                        conn,
                        resolved_run_id,
                        "release_file",
                        str(path.resolve()),
                        sha256_file(path),
                        path.stat().st_size,
                    )
            finally:
                conn.close()

            console.print(f"[green]✓[/green] Adapter:    {adapter_dest}")
            console.print(f"[green]✓[/green] Manifest:   {manifest_path}")
            console.print(f"[green]✓[/green] Model card: {card_path}")

        elif format == "ollama":
            from moro.export.ollama import generate_ollama_package

            adapter_path = run_dir / "adapter"
            pkg_dir = generate_ollama_package(
                adapter_path=adapter_path,
                base_model=selected.config.model.name,
                project_name=cfg.project.name,
                out_dir=out_dir,
            )
            write_gate_report(gate, pkg_dir)
            console.print(f"[green]✓[/green] Ollama package: {pkg_dir}")
            console.print("\n[bold]To deploy:[/bold]")
            model_slug = cfg.project.name.lower().replace(" ", "-")
            console.print(f"  ollama create {model_slug} -f {pkg_dir / 'Modelfile'}")
            console.print(f"  ollama run {model_slug}")

        elif format == "merged":
            from moro.export.merge import merge_adapter_into_base

            adapter_path = run_dir / "adapter"
            merged_dir = out_dir / "merged"
            console.print("[cyan]→[/cyan]  Merging adapter into base model…")
            console.print("[dim]  This may take several minutes for large models.[/dim]")
            with console.status("[cyan]Merging weights…[/cyan]"):
                merged_dir = merge_adapter_into_base(
                    adapter_path=adapter_path,
                    output_dir=merged_dir,
                    local_only=cfg.project.privacy_mode == "local_only",
                    torch_dtype=dtype,
                )
            console.print(f"[green]✓[/green] Merged model saved: {merged_dir}")
            console.print("\n[bold]Load with transformers:[/bold]")
            console.print("  from transformers import AutoModelForCausalLM")
            console.print(f'  model = AutoModelForCausalLM.from_pretrained("{merged_dir}")')

        elif format == "gguf":
            from moro.export.gguf import convert_to_gguf_direct, write_gguf_script
            from moro.export.merge import merge_adapter_into_base

            adapter_path = run_dir / "adapter"
            gguf_dir = out_dir / "gguf"

            # Step 1: Always merge first
            merged_dir = out_dir / "merged"
            console.print("[cyan]→[/cyan]  Step 1/2: Merging adapter into base model…")
            with console.status("[cyan]Merging weights…[/cyan]"):
                merged_dir = merge_adapter_into_base(
                    adapter_path=adapter_path,
                    output_dir=merged_dir,
                    local_only=cfg.project.privacy_mode == "local_only",
                    torch_dtype=dtype,
                )
            console.print(f"[green]✓[/green] Merged model: {merged_dir}")

            # Step 2: Convert to GGUF
            if llama_cpp:
                console.print("[cyan]→[/cyan]  Step 2/2: Converting to GGUF directly…")
                with console.status("[cyan]Converting to GGUF…[/cyan]"):
                    gguf_path = convert_to_gguf_direct(
                        merged_model_dir=merged_dir,
                        out_dir=gguf_dir,
                        llama_cpp_path=llama_cpp,
                        quantization=gguf_quantization,
                        project_name=cfg.project.name,
                    )
                console.print(f"[green]✓[/green] GGUF model: {gguf_path}")
            else:
                console.print("[cyan]→[/cyan]  Step 2/2: Generating GGUF conversion script…")
                script_path = write_gguf_script(
                    merged_model_dir=merged_dir,
                    out_dir=gguf_dir,
                    quantization=gguf_quantization,
                    project_name=cfg.project.name,
                )
                console.print(f"[green]✓[/green] Conversion script: {script_path}")
                console.print("\n[bold]To convert:[/bold]")
                console.print("  export LLAMA_CPP_PATH=/path/to/llama.cpp")
                console.print(f"  {script_path}")

    except DependencyError as exc:
        console.print(f"[bold red]Dependency error:[/bold red] {exc}")
        raise typer.Exit(code=3)
    except ExportError as exc:
        console.print(f"[bold red]Export error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except (ProjectError, ConfigError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
