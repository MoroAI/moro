import json
from pathlib import Path

import typer
from rich.console import Console

from moro.analytics.tracker import ExperimentTracker
from moro.config.loader import load_config
from moro.core.errors import ConfigError, DatasetError, DependencyError, TrainingError
from moro.core.hashing import config_snapshot_hash
from moro.core.paths import CONFIG_FILE
from moro.core.project import require_project_root
from moro.data.versions import select_snapshot, verify_snapshot
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
    exp_id = None
    tracker = None
    try:
        if resume:
            raise ConfigError("Checkpoint resume is not implemented; --resume cannot be used yet.")
        root = require_project_root()
        cfg_file = config_path or (root / CONFIG_FILE)
        cfg = load_config(cfg_file)

        snapshot = select_snapshot(root, cfg)
        if snapshot is None:
            raise DatasetError("No immutable dataset matches current inputs. Run moro data build.")
        dataset_row, dataset_manifest = snapshot
        dataset_directory = (root / dataset_row["manifest_path"]).parent
        train_path = dataset_directory / "train.jsonl"

        backend = HuggingFaceBackend()

        # Validate
        console.print("[cyan]→[/cyan]  Validating config and dataset…")
        with console.status("[cyan]Validating…[/cyan]"):
            warnings = backend.validate(cfg, train_path)

        for w in warnings:
            console.print(f"[yellow]⚠[/yellow]  {w}")

        validation_path = dataset_directory / "validation.jsonl"
        if validation_path.stat().st_size:
            backend.validate(cfg, validation_path)

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

        config_hash = config_snapshot_hash(cfg.model_dump_json())
        output_base = cfg.training.output_dir
        if not output_base.is_absolute():
            output_base = root / output_base
        output_dir = output_base / "pending"

        run_id = storage_db.create_run(
            conn=conn,
            project_id=project_id,
            config_hash=config_hash,
            model_name=cfg.model.name,
            quantization=cfg.model.quantization,
            output_dir=str(output_dir),
            run_name=run_name,
            dataset_version_id=dataset_row["version_id"],
        )
        storage_db.update_run_status(conn, run_id, "running")

        # Rename output dir to use run_id
        output_dir = output_base / run_id
        conn.execute(
            "UPDATE runs SET output_dir = ? WHERE id = ?",
            (str(output_dir), run_id),
        )
        conn.commit()

        console.print(f"[cyan]→[/cyan]  Starting run: [bold]{run_id}[/bold]")
        console.print(f"  Model: {cfg.model.name}")

        try:
            tracker = ExperimentTracker(root / ".moro" / "analytics.db")
            exp_id = tracker.create_experiment(
                name=run_name or f"run_{run_id}",
                base_model=cfg.model.name,
                dataset_id=dataset_row.get("version_id") if isinstance(dataset_row, dict) else getattr(dataset_row, "version_id", None),
                dataset_name=str(train_path),
                state_node_id=run_id,
            )
            tracker.start_experiment(
                experiment_id=exp_id,
                hyperparameters={
                    "learning_rate": getattr(cfg.training, "learning_rate", None),
                    "batch_size": getattr(cfg.training, "batch_size", None),
                    "gradient_accumulation_steps": getattr(cfg.training, "gradient_accumulation_steps", None),
                    "epochs": getattr(cfg.training, "epochs", None),
                    "warmup_ratio": getattr(cfg.training, "warmup_ratio", None),
                    "weight_decay": getattr(cfg.training, "weight_decay", None),
                    "lora_r": getattr(cfg.training, "lora_r", None),
                    "lora_alpha": getattr(cfg.training, "lora_alpha", None),
                    "lora_dropout": getattr(cfg.training, "lora_dropout", None),
                    "target_modules": getattr(cfg.training, "target_modules", []),
                    "optimizer": getattr(cfg.training, "optimizer", "adamw"),
                    "max_seq_length": getattr(cfg.training, "max_seq_length", 2048),
                    "seed": getattr(cfg.training, "seed", 42),
                },
                gpu_name=None,
                gpu_vram_gb=est_vram,
            )
        except Exception:
            pass

        try:
            output_dir.mkdir(parents=True, exist_ok=True)
            (output_dir / "config.json").write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
            from moro.core.hashing import sha256_file

            (output_dir / "dataset.json").write_text(
                json.dumps(
                    {
                        "path": str(train_path),
                        "sha256": sha256_file(train_path),
                        "dataset_version_id": dataset_row["version_id"],
                        "manifest_sha256": dataset_row["manifest_sha256"],
                        "files": dataset_manifest["files"],
                    },
                    indent=2,
                ),
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
            if tracker and exp_id:
                try:
                    tracker.fail_experiment(exp_id, error_message=str(exc) or "Interrupted")
                except Exception:
                    pass
            if isinstance(exc, KeyboardInterrupt):
                raise typer.Exit(code=130) from exc
            raise

        try:
            verify_snapshot(root, dataset_row)
            import math

            for metric in ("train_loss", "validation_loss", "peak_vram_gb", "tokens_per_sec"):
                value = result.get(metric)
                if value is not None and not math.isfinite(value):
                    raise TrainingError(f"Non-finite training metric: {metric}")
        except (DatasetError, TrainingError) as exc:
            storage_db.update_run_status(conn, run_id, "failed", error=str(exc))
            if tracker and exp_id:
                try:
                    tracker.fail_experiment(exp_id, error_message=str(exc))
                except Exception:
                    pass
            raise
        (output_dir / "training_report.json").write_text(json.dumps(result, indent=2, default=str))

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
        if tracker and exp_id:
            try:
                tracker.complete_experiment(
                    experiment_id=exp_id,
                    final_train_loss=result.get("train_loss"),
                    final_eval_loss=result.get("validation_loss"),
                    peak_vram_gb=result.get("peak_vram_gb"),
                    tokens_per_second=result.get("tokens_per_sec"),
                )
            except Exception:
                pass

        console.print(
            f"\n[bold green]✓[/bold green] Training complete! Run ID: [bold]{run_id}[/bold]"
        )
        if exp_id:
            console.print(f"  [cyan]📊 Experiment tracked:[/cyan] [bold]{exp_id}[/bold]")
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
