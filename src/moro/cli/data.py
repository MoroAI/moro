from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from moro.core.errors import ConfigError, DatasetError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.data import clean, ingest, normalize, privacy, report, splitter
from moro.data.splitter import write_split
from moro.storage import db as storage_db

app = typer.Typer(name="data", help="Dataset operations.")
console = Console()


@app.command("build")
def build_command(
    config_path: Path | None = typer.Option(
        None,
        "--config",
        help="Path to moro.yaml (auto-detected if not given).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Rebuild even if dataset is up to date.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Process only this many rows (for debugging).",
    ),
) -> None:
    """Normalize, clean, score, and split the dataset."""
    try:
        root = require_project_root()
        from moro.config.loader import load_config

        cfg = load_config(config_path) if config_path else load_project_config()

        # Resolve source
        source = cfg.dataset.source
        if not source.is_absolute():
            source = root / source

        if not source.exists():
            raise DatasetError(
                f"Dataset source not found: {source}\n"
                "Run `moro import` first or update dataset.source in moro.yaml."
            )

        console.print(f"[cyan]→[/cyan]  Reading from: [bold]{source}[/bold]")

        # 1. Ingest
        with console.status("[cyan]Ingesting raw data…[/cyan]"):
            raw_rows = ingest.read_raw_rows(source, cfg.dataset.format)

        if limit:
            raw_rows = raw_rows[:limit]

        console.print(f"[cyan]→[/cyan]  Ingested [bold]{len(raw_rows)}[/bold] raw rows")

        # 2. Normalize
        with console.status("[cyan]Normalizing rows…[/cyan]"):
            valid_rows, invalid_rows = normalize.normalize_rows(raw_rows, str(source))

        console.print(
            f"[cyan]→[/cyan]  Normalized: [green]{len(valid_rows)} valid[/green], "
            f"[red]{len(invalid_rows)} invalid[/red]"
        )

        # 3. Clean + deduplicate
        with console.status("[cyan]Cleaning and deduplicating…[/cyan]"):
            clean_valid, clean_invalid, exact_dups, near_dups = clean.clean_rows(
                valid_rows,
                max_seq_length=cfg.dataset.max_seq_length,
                min_quality_score=cfg.dataset.min_quality_score,
                deduplicate=cfg.dataset.deduplicate,
            )
            all_invalid = invalid_rows + clean_invalid

        console.print(
            f"[cyan]→[/cyan]  After cleaning: [bold]{len(clean_valid)}[/bold] rows "
            f"({exact_dups} exact dups, {near_dups} near-dups removed)"
        )

        if not clean_valid:
            raise DatasetError("No valid rows remain after cleaning. Check your dataset format.")

        # 4. Privacy scan
        if cfg.dataset.pii_scan:
            with console.status("[cyan]Scanning for PII…[/cyan]"):
                privacy.scan_rows(clean_valid)
            flagged = sum(1 for r in clean_valid if r.privacy_flags)
            if flagged > 0:
                console.print(f"[yellow]⚠[/yellow]  {flagged} rows flagged for possible PII")

        # 5. Split
        with console.status("[cyan]Splitting dataset…[/cyan]"):
            train_rows, val_rows, eval_rows = splitter.split_rows(
                clean_valid,
                validation_ratio=cfg.dataset.validation_ratio,
                eval_ratio=cfg.dataset.eval_ratio,
                seed=cfg.project.seed,
            )

        # 6. Write outputs
        norm_path = root / "data" / "normalized" / "dataset.jsonl"
        splits_dir = root / "data" / "splits"

        with console.status("[cyan]Writing dataset files…[/cyan]"):
            write_split(clean_valid, norm_path)
            write_split(train_rows, splits_dir / "train.jsonl")
            write_split(val_rows, splits_dir / "validation.jsonl")
            write_split(eval_rows, splits_dir / "eval.jsonl")

        # 7. Compute stats
        stats = report.compute_stats(
            rows=clean_valid,
            invalid_count=len(all_invalid),
            exact_dup_count=exact_dups,
            near_dup_count=near_dups,
            train_rows=len(train_rows),
            validation_rows=len(val_rows),
            eval_rows=len(eval_rows),
            pii_scan=cfg.dataset.pii_scan,
        )

        # 8. Save stats report
        reports_dir = root / ".moro" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / "dataset_report.json"
        report_path.write_text(stats.model_dump_json(indent=2), encoding="utf-8")

        # 9. Persist dataset version in DB

        conn = storage_db.get_connection(root)
        project_id = storage_db.get_or_create_project(
            conn, cfg.project.name, cfg.project.privacy_mode
        )

        # Find or create dataset source record
        src_row = conn.execute(
            "SELECT id FROM dataset_sources WHERE project_id = ? ORDER BY imported_at DESC LIMIT 1",
            (project_id,),
        ).fetchone()

        if src_row:
            source_id = src_row["id"]
            # Count existing versions
            count = conn.execute(
                "SELECT COUNT(*) FROM dataset_versions WHERE source_id = ?", (source_id,)
            ).fetchone()[0]
            version = f"v{count + 1}"
            storage_db.add_dataset_version(
                conn, project_id, source_id, version, str(norm_path), stats.model_dump()
            )
        conn.close()

        console.print(
            f"\n[bold green]✓[/bold green] Dataset built successfully! "
            f"[bold]{len(clean_valid)}[/bold] rows across "
            f"train={len(train_rows)} / val={len(val_rows)} / eval={len(eval_rows)}"
        )
        console.print(f"  Report saved to: [dim]{report_path}[/dim]")
        console.print(
            "\n[bold]Next steps:[/bold] Run [bold]moro data report[/bold] "
            "or [bold]moro recipe suggest[/bold]"
        )

    except (ProjectError, ConfigError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=5)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        import traceback

        console.print(traceback.format_exc())
        raise typer.Exit(code=1)


@app.command("report")
def report_command(
    format: str = typer.Option(
        "table",
        "--format",
        help="Output format: table or json.",
    ),
) -> None:
    """Show dataset quality report."""
    try:
        root = require_project_root()
        report_path = root / ".moro" / "reports" / "dataset_report.json"

        if not report_path.exists():
            console.print(
                "[bold red]Error:[/bold red] No dataset report found. "
                "Run [bold]moro data build[/bold] first."
            )
            raise typer.Exit(code=1)

        from moro.data.models import DatasetStats

        stats = DatasetStats.model_validate_json(report_path.read_text(encoding="utf-8"))

        if format == "json":
            typer.echo(stats.model_dump_json(indent=2))
            return

        table = Table(title="Dataset Quality Report", show_header=True)
        table.add_column("Metric", style="cyan", no_wrap=True)
        table.add_column("Value", style="white")

        table.add_row("Total rows (input)", str(stats.rows_total))
        table.add_row("Valid rows", f"[green]{stats.rows_valid}[/green]")
        table.add_row(
            "Invalid rows",
            str(stats.rows_invalid),
        )
        table.add_row("Exact duplicates removed", str(stats.rows_deduplicated))
        table.add_row("Near-duplicates removed", str(stats.rows_near_duplicate))
        table.add_row("─" * 20, "─" * 20)
        table.add_row("Train rows", str(stats.train_rows))
        table.add_row("Validation rows", str(stats.validation_rows))
        table.add_row("Eval rows", str(stats.eval_rows))
        table.add_row("─" * 20, "─" * 20)
        table.add_row("Avg token count", f"{stats.avg_tokens:.1f}")
        table.add_row("P50 token count", f"{stats.p50_tokens:.0f}")
        table.add_row("P95 token count", f"{stats.p95_tokens:.0f}")
        table.add_row("Max token count", str(stats.max_tokens))
        table.add_row("─" * 20, "─" * 20)
        table.add_row("Avg quality score", f"{stats.avg_quality_score:.4f}")
        table.add_row("Min quality score", f"{stats.min_quality_score:.4f}")
        table.add_row("P50 quality score", f"{stats.quality_score_p50:.4f}")
        table.add_row("PII warnings", str(stats.privacy_warning_count))

        console.print(table)

        if stats.warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for w in stats.warnings:
                console.print(f"  [yellow]⚠[/yellow]  {w}")

    except (ProjectError,) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
