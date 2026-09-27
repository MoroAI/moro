from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from moro.core.errors import ConfigError, DatasetError, ProjectError
from moro.core.project import load_project_config, require_project_root
from moro.data import clean, ingest, normalize, privacy, report, splitter
from moro.data.versions import publish_snapshot, select_snapshot, source_fingerprint
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
        min=1,
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

        if not force:
            cached = select_snapshot(root, cfg, limit)
            if cached:
                console.print(
                    f"Dataset unchanged; using {cached[0]['version_id']}. Use --force to rebuild."
                )
                return
        fingerprint = source_fingerprint(source)

        # 1. Ingest
        with console.status("[cyan]Ingesting raw data…[/cyan]"):
            raw_rows = ingest.read_raw_rows(source, cfg.dataset.format, limit)

        console.print(f"[cyan]→[/cyan]  Ingested [bold]{len(raw_rows)}[/bold] raw rows")

        # 2. Normalize
        with console.status("[cyan]Normalizing rows…[/cyan]"):
            valid_rows, invalid_rows = normalize.normalize_rows(raw_rows, str(source))

        console.print(
            f"[cyan]→[/cyan]  Normalized: [green]{len(valid_rows)} valid[/green], "
            f"[red]{len(invalid_rows)} invalid[/red]"
        )

        # 3. Clean + deduplicate (with epistemic scoring & MI Guard)
        glossary_path = root / "domain_glossary.txt"
        if not glossary_path.exists() and hasattr(cfg.dataset, "domain_glossary") and cfg.dataset.domain_glossary:
            glossary_path = root / cfg.dataset.domain_glossary

        with console.status("[cyan]Cleaning, scoring epistemically, and deduplicating…[/cyan]"):
            clean_valid, clean_invalid, exact_dups, near_dups = clean.clean_rows(
                valid_rows,
                max_seq_length=cfg.dataset.max_seq_length,
                min_quality_score=cfg.dataset.min_quality_score,
                deduplicate=cfg.dataset.deduplicate,
                domain_glossary_path=glossary_path if glossary_path.exists() else None,
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

        destination, manifest = publish_snapshot(
            root,
            cfg,
            source,
            fingerprint,
            limit,
            clean_valid,
            (train_rows, val_rows, eval_rows),
            stats,
            all_invalid,
        )
        report_path = destination / "report.json"
        console.print(f"Dataset version: {manifest['dataset_version_id']}")

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
        cfg = load_project_config()
        conn = storage_db.get_connection(root)
        try:
            row = conn.execute(
                """SELECT s.manifest_path FROM dataset_snapshots s
                JOIN dataset_versions v ON s.version_id=v.id JOIN projects p ON p.id=v.project_id
                WHERE p.name=? ORDER BY v.created_at DESC, v.id DESC LIMIT 1""",
                (cfg.project.name,),
            ).fetchone()
        finally:
            conn.close()
        report_path = (
            (root / row["manifest_path"]).parent / "report.json"
            if row
            else root / ".moro/reports/dataset_report.json"
        )

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

        if stats.classification_counts or stats.mi_guard_count > 0:
            table.add_row("─" * 20, "─" * 20)
            table.add_row("MI Guard saved rows", f"[bold green]{stats.mi_guard_count}[/bold green]")
            if stats.avg_zlib_entropy > 0:
                table.add_row("Avg zlib entropy", f"{stats.avg_zlib_entropy:.4f}")
            if stats.avg_ppmi > 0:
                table.add_row("Avg domain PPMI", f"{stats.avg_ppmi:.4f}")
            for cls_name, count in sorted(stats.classification_counts.items()):
                table.add_row(f"Class: {cls_name}", str(count))

        console.print(table)

        if stats.warnings:
            console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for w in stats.warnings:
                console.print(f"  [yellow]⚠[/yellow]  {w}")

    except typer.Exit:
        raise
    except (ProjectError,) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)


@app.command("inspect")
def inspect_command(
    split: str = typer.Option(
        "train",
        "--split",
        help="Which split to inspect: train, validation, eval, dataset.",
    ),
    n: int = typer.Option(5, "--n", min=1, max=100, help="Number of rows to show."),
    offset: int = typer.Option(0, "--offset", min=0, help="Row offset to start from."),
    format: str = typer.Option("table", "--format", help="Output format: table or json."),
) -> None:
    """Inspect sample rows from the latest built dataset split."""
    import json as _json

    try:
        root = require_project_root()
        cfg = load_project_config()

        conn = storage_db.get_connection(root)
        try:
            row = conn.execute(
                """SELECT s.manifest_path FROM dataset_snapshots s
                JOIN dataset_versions v ON s.version_id=v.id
                JOIN projects p ON p.id=v.project_id
                WHERE p.name=? ORDER BY v.created_at DESC, v.id DESC LIMIT 1""",
                (cfg.project.name,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            console.print(
                "[bold red]No built dataset found.[/bold red] "
                "Run [bold]moro data build[/bold] first."
            )
            raise typer.Exit(code=1)

        dataset_dir = (root / row["manifest_path"]).parent
        filename = f"{split}.jsonl" if split != "dataset" else "dataset.jsonl"
        split_path = dataset_dir / filename

        if not split_path.exists():
            console.print(f"[red]Split file not found: {split_path}[/red]")
            raise typer.Exit(code=1)

        rows_data = []
        with split_path.open("r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i < offset:
                    continue
                if len(rows_data) >= n:
                    break
                rows_data.append(_json.loads(line.strip()))

        total_count = sum(1 for _ in open(split_path, encoding="utf-8"))

        if format == "json":
            typer.echo(_json.dumps(rows_data, indent=2, ensure_ascii=False))
            return

        console.print(
            f"\n[bold]Dataset:[/bold] {split} split · "
            f"showing rows {offset + 1}–{offset + len(rows_data)} of {total_count}\n"
        )

        for i, row_data in enumerate(rows_data, start=offset + 1):
            messages = row_data.get("messages", [])
            console.print(f"[bold cyan]── Row {i} ──────────────────────────────[/bold cyan]")
            for msg in messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                # Truncate long content for readability
                if len(content) > 300:
                    content = content[:297] + "…"
                role_color = {
                    "system": "dim",
                    "user": "green",
                    "assistant": "blue",
                }.get(role, "white")
                console.print(f"  [{role_color}][{role}][/{role_color}] {content}")
            console.print()

    except typer.Exit:
        raise
    except (ProjectError, DatasetError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)
    except Exception as exc:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
        raise typer.Exit(code=1)
