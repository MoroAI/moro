> Historical scaffold plan. For implemented behavior, verified checks, and remaining work, see [engineering status](docs/engineering-status.md).

# MoroAI MVP — Full Implementation Plan

## Summary

MoroAI is a **local-first model adaptation foundry** — a Python CLI tool (`moro`) that manages the full lifecycle of turning private, messy data into deployed local LLMs. It is not just a fine-tuning script; it is a structured system covering data ingestion, quality checks, hardware-aware recipe suggestion, QLoRA training (via Hugging Face stack), evaluation, export, and Ollama deployment.

---

## Deep Analysis of Instructions

### What the 5 specification files cover

| File | Coverage |
|------|----------|
| `MoroAI.txt` | Brand strategy, product family, high-level architecture, command structure |
| `-MoroAI-Full-Archi.txt` | Full architectural blueprint — 4 planes, 9 modules, 10 data models, storage schema, CLI surface |
| `MoroAI-MVP-Engineering-Spec.txt` | Exact repo layout, CLI spec, Pydantic schemas, SQLite schema, 25 ordered engineering tasks, DoD |
| `MoroAI-starter-code-skeleton.txt` | Ready-to-paste code for Tasks 1–6 (init, status, doctor, config, templates) |
| `next-stage-MoroAI-starter-skeleton.txt` | Ready-to-paste code for Tasks 7–16 (storage, data pipeline, import, build, report) |

### Architecture — 4 Planes

```
CLI Layer         moro init / doctor / data / train / eval / deploy
Control Plane     Projects / Datasets / Recipes / Runs / Releases  (SQLite)
Execution Plane   Data Compiler | Trainer | Eval Runner | Exporter
Intelligence      Recipe Engine | Memory Governor | Diagnostics
Backend Adapters  HF / PEFT / TRL / bitsandbytes / Unsloth / Ollama
```

### MVP Definition of Done (25 Tasks)

The spec prescribes an exact build order. Tasks 1–16 have reference skeleton code already written. Tasks 17–25 require implementation from the spec description.

---

## Proposed Changes

### Repository Root: `moro/`

#### [NEW] `pyproject.toml`
Package: `moroai`, console script `moro = moro.main:app`, Python ≥ 3.10.
Core deps: `typer`, `rich`, `pydantic>=2`, `pyyaml`, `psutil`.
Optional extra `[train]`: torch, transformers, datasets, peft, trl, accelerate, bitsandbytes.

#### [NEW] `README.md`, `.gitignore`, `Makefile`, `moro.yaml.example`

---

### `src/moro/` — Package Root

#### [NEW] `__init__.py` — version `0.1.0`
#### [NEW] `main.py` — Typer app, registers all CLI commands

---

### `src/moro/core/` — Shared Foundation (Task 2)

#### [NEW] `errors.py` — `MoroError`, `ProjectError`, `ConfigError`, `DatasetError`, `DependencyError`, `TrainingError`, `ExportError`
#### [NEW] `paths.py` — `find_project_root()`, `project_dirs()`, `ensure_project_dirs()`, `PROJECT_DIRS` constant
#### [NEW] `project.py` — `require_project_root()`, `load_project_config()`
#### [NEW] `hashing.py` — `sha256_file()`, `sha256_text()`
#### [NEW] `ids.py` — `new_id(prefix)` with `{prefix}_YYYYMMDDHHMMSS_4hex` format
#### [NEW] `logging.py` — structured rich logging helpers

---

### `src/moro/config/` — Config Models (Tasks 3–4)

#### [NEW] `models.py` — Pydantic v2 models:
- `ProjectConfig`, `DatasetConfig`, `ModelConfig`, `AdapterConfig`
- `TrainingConfig`, `EvalConfig`, `ReleaseConfig`, `MoroConfig`

#### [NEW] `loader.py` — `load_config(path) -> MoroConfig`
#### [NEW] `validators.py` — extra cross-field validation helpers

---

### `src/moro/templates/` — Project Templates (Task 5)

#### [NEW] `project.py` — `default_moro_yaml()`, `readme_template()`, `DEFAULT_GITIGNORE`, `SAMPLE_EVAL_YAML`

---

### `src/moro/cli/` — CLI Commands

#### [NEW] `init.py` — `moro init [PATH]` with `--template`, `--force` (Task 5)
#### [NEW] `status.py` — `moro status` with `--json` (Task 6)
#### [NEW] `doctor.py` — `moro doctor` with hardware detection (Task 8)
#### [NEW] `import_data.py` — `moro import SOURCE` with `--name`, `--format`, `--copy/--link` (Task 9)
#### [NEW] `data.py` — `moro data build`, `moro data report` (Tasks 15–16)
#### [NEW] `recipe.py` — `moro recipe suggest` with `--model`, `--target-vram`, `--json` (Task 18)
#### [NEW] `train.py` — `moro train` with `--dry-run`, `--resume`, `--run-name` (Task 21)
#### [NEW] `eval.py` — `moro eval run`, `moro eval report` (Task 23)
#### [NEW] `export.py` — `moro export` with `--format`, `--run-id`, `--out` (Task 24)
#### [NEW] `deploy.py` — `moro deploy` with `--target`, `--run-id`, `--tag` (Task 25)
#### [NEW] `diagnose.py` — `moro diagnose` with `--run-id`, `--last`, `--json` (Task 25)

---

### `src/moro/storage/` — SQLite Persistence (Task 7)

#### [NEW] `db.py` — `get_connection()`, `ensure_schema()`, CRUD helpers for:
  - `projects`, `dataset_sources`, `dataset_versions`, `runs`, `eval_runs`, `artifacts`
#### [NEW] `queries.py` — higher-level query functions

---

### `src/moro/hardware/` — Hardware Detection (Task 8)

#### [NEW] `detector.py` — detect GPU, VRAM, CPU RAM, disk, PyTorch/CUDA availability
#### [NEW] `profile.py` — `HardwareProfile` Pydantic model

---

### `src/moro/data/` — Data Pipeline (Tasks 10–16)

#### [NEW] `models.py` — `DatasetMessage`, `DatasetRow`, `InvalidRow`, `DatasetStats`, `DatasetReport`
#### [NEW] `ingest.py` — `read_raw_rows()`, format auto-detect, JSONL/CSV/TXT readers
#### [NEW] `normalize.py` — `normalize_rows()` supporting messages / instruction-input-output / prompt-completion formats
#### [NEW] `clean.py` — `clean_rows()` removing empty, oversized, malformed rows
#### [NEW] `dedupe.py` — `deduplicate_rows()` exact + near-duplicate removal (shingling)
#### [NEW] `quality.py` — `score_row()`, `approximate_token_count()`
#### [NEW] `privacy.py` — regex-based PII scanner (email, phone, API keys)
#### [NEW] `splitter.py` — `split_rows()` → train/validation/eval JSONL files
#### [NEW] `report.py` — `compute_stats()`, `build_report()`, table/JSON output

---

### `src/moro/recipes/` — Recipe Engine (Tasks 17–18)

#### [NEW] `presets.py` — hardware tier presets (CPU-only, ≤4 GB, ≤8 GB, ≤16 GB, 24+ GB)
#### [NEW] `rules.py` — rule functions: pick model, quantization, seq_length, batch_size, adapter rank
#### [NEW] `engine.py` — `suggest_recipe(hardware, config) -> RecipeSuggestion`

---

### `src/moro/training/` — Training Engine (Tasks 19–21)

#### [NEW] `backend.py` — abstract `TrainingBackend` protocol
#### [NEW] `hf_backend.py` — HF + PEFT + TRL + bitsandbytes QLoRA implementation
#### [NEW] `run.py` — `RunRecord` model, run lifecycle helpers (create/update/fail/complete)
#### [NEW] `checkpoints.py` — checkpoint saving/loading helpers
#### [NEW] `metrics.py` — metrics capture (loss, VRAM, tokens/sec)

---

### `src/moro/eval/` — Evaluation (Tasks 22–23)

#### [NEW] `models.py` — `EvalSuite`, `EvalCase`, `EvalExpect`, `EvalResult`, `CaseScore`
#### [NEW] `loader.py` — YAML → `EvalSuite` loader
#### [NEW] `scorers.py` — `contains`, `any_of_contains`, `regex`, `json_schema` scorers
#### [NEW] `runner.py` — run suite against model, persist `EvalResult`
#### [NEW] `report.py` — format eval results table/JSON

---

### `src/moro/export/` — Export & Release (Tasks 24–25)

#### [NEW] `adapter.py` — copy/zip adapter artifacts
#### [NEW] `manifest.py` — generate `manifest.json` / `ReleaseManifest`
#### [NEW] `model_card.py` — generate `model_card.md`
#### [NEW] `ollama.py` — generate Ollama `Modelfile` and packaging folder
#### [NEW] `gguf.py` — stub for GGUF conversion (calls external `llama.cpp` if available)

---

### `src/moro/diagnose/` — Diagnostics (Task 25)

#### [NEW] `analyzer.py` — inspect run logs, detect OOM, config issues, dataset errors
#### [NEW] `recommendations.py` — map detected issues → actionable config suggestions

---

### `tests/` — Test Suite

#### [NEW] `conftest.py` — shared fixtures (tmp project dir, sample dataset)
#### [NEW] `test_config.py` — config parsing, defaults, validation errors
#### [NEW] `test_paths.py` — path helpers
#### [NEW] `test_data_normalize.py` — all 3 input formats
#### [NEW] `test_data_clean.py` — cleaning edge cases
#### [NEW] `test_data_quality.py` — quality scoring
#### [NEW] `test_recipe_engine.py` — low/high VRAM presets
#### [NEW] `test_cli_init.py` — project creation
#### [NEW] `test_cli_doctor.py` — hardware detection
#### [NEW] `test_eval_scorers.py` — all scorers
#### [NEW] `test_export_manifest.py` — manifest generation

---

### Templates

#### [NEW] `templates/project/moro.yaml` — starter config
#### [NEW] `templates/project/README.md`
#### [NEW] `templates/project/.gitignore`
#### [NEW] `templates/eval/support-golden-v1.yaml` — sample eval suite

---

## Build Order (Exactly per Spec §15)

Tasks are executed in this order:
1. Repo scaffold (`pyproject.toml`, `main.py`, `__init__.py`)
2. Core utilities (`errors`, `logging`, `paths`)
3. Config Pydantic models
4. Config YAML loader
5. `moro init`
6. `moro status`
7. SQLite storage layer
8. Hardware detection + `moro doctor`
9. `moro import`
10. JSONL/CSV ingestion
11. Normalization engine
12. Cleaning engine
13. Deduplication engine
14. Quality scoring + privacy flags
15. Splitter + `moro data build`
16. `moro data report`
17. Recipe engine rules + presets
18. `moro recipe suggest` CLI
19. Training backend interface + run lifecycle
20. HF QLoRA backend
21. `moro train`
22. Eval suite loader + schema
23. Eval runner + scorers
24. Export + release manifest
25. Ollama deploy + diagnostics

---

## Verification Plan

### Automated Tests
```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Smoke Test (End-to-End MVP Flow)
```bash
moro init demo && cd demo
# add sample data to data/raw/support.jsonl
moro import ./data/raw/support.jsonl --name support
moro data build
moro data report
moro doctor
moro recipe suggest
moro train --dry-run
```

### Unit Test Coverage
- All config validation paths
- Data normalization for all 3 input formats
- Cleaning/deduplication logic
- Recipe presets (CPU-only / low VRAM / high VRAM)
- All eval scorers
- Export manifest generation

> [!NOTE]
> The `moro train` (actual training) step requires optional ML deps (`torch`, `transformers`, etc.) and is validated with `--dry-run` only for the MVP. Real training test requires GPU hardware.

---

## Open Questions

> [!IMPORTANT]
> **Training hardware target**: The spec defaults to Qwen/Qwen2.5-1.5B-Instruct as sample model. Should I keep that default or parameterize it to a model you already have locally?

> [!IMPORTANT]
> **Python environment**: Should I create a `venv` or use an existing one? And should I run `pip install -e .` now as part of setup?

> [!NOTE]
> **DuckDB analytics**: The full arch spec includes DuckDB for dataset profiling/analytics. The MVP spec treats it as optional. I will stub it in for the MVP but not make it a hard dependency.

> [!NOTE]
> **MoroAI.txt and `-MoroAI-Full-Archi.txt`** read like strategic documents / vision docs rather than engineering specs. I will use them for architecture reference only, not as code sources.
