import json
from pathlib import Path

import typer
from rich.console import Console

from moro.config.loader import load_config
from moro.core.errors import ConfigError, DatasetError, DependencyError, TrainingError
from moro.core.hashing import sha256_text
from moro.core.paths import CONFIG_FILE
from moro.core.project import require_project_root
from moro.storage import db as storage_db
from moro.training.hf_backend import HuggingFaceBackend

app = typer.Typer(name="train", help="Training operations.")
console = Console()


def train_command(
    config_path: Path | None = typer.Option(
        None,
        "--config",
        help="Path to moro.yaml.",
    ),
    run_name: str | None = typer.Option(
        None,
        "--run-name",
        help="Human-readable name for this run.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and estimate memory without training.",
    ),
    resume: str | None = typer.Option(
        None,
        "--resume",
        help="Run ID to resume from checkpoint.",
    ),
) -> None:
    """Run fine-tuning with the current project config."""
    conn = None
    run_id = None
    try:
        if resume:
            raise ConfigError("Checkpoint resume is not implemented; --resume cannot be used yet.")
        root = require_project_root()
        cfg_file = config_path or (root / CONFIG_FILE)
        cfg = load_config(cfg_file)

        # Locate training dataset
        train_path = root / "data" / "splits" / "train.jsonl"
        if not train_path.exists():
            raise DatasetError("Training split not found. Run [bold]moro data build[/bold] first.")

        backend = HuggingFaceBackend()

        # Validate
        console.print("[cyan]→[/cyan]  Validating config and dataset…")
        with console.status("[cyan]Validating…[/cyan]"):
            warnings = backend.validate(cfg, train_path)

        for w in warnings:
            console.print(f"[yellow]⚠[/yellow]  {w}")

        # Estimate memory
        est_vram = backend.estimate_memory(cfg)
        console.print(f"[cyan]→[/cyan]  Estimated VRAM: [bold]{est_vram:.1f} GB[/bold]")

        if dry_run:
            console.print("\n[bold green]✓[/bold green] Dry-run complete — no training performed.")
            console.print(f"  Model:         {cfg.model.name}")
            console.print(f"  Quantization:  {cfg.model.quantization}")
            console.print(f"  Est. VRAM:     {est_vram:.1f} GB")
            return

        # Prepare run record in DB
        conn = storage_db.get_connection(root)
        project_id = storage_db.get_or_create_project(
            conn, cfg.project.name, cfg.project.privacy_mode
        )

        config_hash = sha256_text(cfg.model_dump_json())
        output_dir = root / "runs" / "pending"

        run_id = storage_db.create_run(
            conn=conn,
            project_id=project_id,
            config_hash=config_hash,
            model_name=cfg.model.name,
            quantization=cfg.model.quantization,
            output_dir=str(output_dir),
            run_name=run_name,
        )
        storage_db.update_run_status(conn, run_id, "running")

        # Rename output dir to use run_id
        output_dir = root / "runs" / run_id
        conn.execute(
            "UPDATE runs SET output_dir = ? WHERE id = ?",
            (str(output_dir), run_id),
        )
        conn.commit()

        console.print(f"[cyan]→[/cyan]  Starting run: [bold]{run_id}[/bold]")
        console.print(f"  Model: {cfg.model.name}")

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "config.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
            from moro.core.hashing import sha256_file

            (output_dir / "dataset.json").write_text(
                json.dumps({"path": str(train_path), "sha256": sha256_file(train_path)}, indent=2),
                encoding="utf-8",
            )

            # Execute training
            with console.status(f"[cyan]Training…[/cyan] (run: {run_id})"):
                result = backend.train(
                    config=cfg,
                    dataset_path=train_path,
                    output_dir=output_dir,
                    run_id=run_id,
                    dry_run=False,
                )

        except (Exception, KeyboardInterrupt) as exc:
            status = "cancelled" if isinstance(exc, KeyboardInterrupt) else "failed"
            storage_db.update_run_status(conn, run_id, status, error=str(exc) or "Interrupted")
            if isinstance(exc, KeyboardInterrupt):
                raise typer.Exit(code=130) from exc
            raise

        # Update run record
        storage_db.update_run_status(
            conn=conn,
            run_id=run_id,
            status="completed",
            train_loss=result.get("train_loss"),
            validation_loss=result.get("validation_loss"),
            peak_vram_gb=result.get("peak_vram_gb"),
            tokens_per_sec=result.get("tokens_per_sec"),
        )

        console.print(
            f"\n[bold green]✓[/bold green] Training complete! Run ID: [bold]{run_id}[/bold]"
        )
        if result.get("train_loss"):
            console.print(f"  Train loss:     {result['train_loss']}")
        if result.get("validation_loss"):
            console.print(f"  Val loss:       {result['validation_loss']}")
        if result.get("peak_vram_gb"):
            console.print(f"  Peak VRAM:      {result['peak_vram_gb']:.2f} GB")
        console.print(f"  Adapter saved:  {result.get('adapter_path', output_dir / 'adapter')}")
        console.print(
            "\n[bold]Next steps:[/bold] Run [bold]moro eval run[/bold] or [bold]moro export[/bold]"
        )

    except typer.Exit:
        raise
    except DependencyError as exc:
        console.print(f"[bold red]Dependency error:[/bold red] {exc}")
        raise typer.Exit(code=3)
    except (ConfigError,) as exc:
        console.print(f"[bold red]Config error:[/bold red] {exc}")
        raise typer.Exit(code=2)
    except DatasetError as exc:
        console.print(f"[bold red]Dataset error:[/bold red] {exc}")
        raise typer.Exit(code=5)
    except TrainingError as exc:
        console.print(f"[bold red]Training error:[/bold red] {exc}")
        raise typer.Exit(code=4)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    finally:
        if conn is not None:
            conn.close()
