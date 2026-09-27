# MoroAI — Deep-Down Project Analysis & MVP Deployment Report

> **Scope:** Complete codebase review against all instruction documents, every module, all tests, live test run results, and architecture specs.
> **Date:** 2026-09-17 | **Test baseline:** 195 pass / 14 fail / 1 import error

---

## Executive Summary

MoroAI has a **solid architectural skeleton** but is **not yet MVP-deployable**. The five-pillar model (Data Compiler → Recipe Engine → Training Runner → Eval Harness → Release Pipeline) is all present in some form, but each pillar has **structural correctness gaps** that prevent it from being trusted by real users. The engineering is clean, the CLI surface is well-designed, and the core patterns are right — but trust, lineage, and correctness proofs are still incomplete.

**Current state in one line:** *The project can execute the workflow, but cannot yet prove that the output is trustworthy.*

---

## 1. What's Actually Working ✅

| Area | Status | Evidence |
|------|--------|----------|
| CLI structure | ✅ Solid | All 14 commands register correctly, Typer/Rich integration clean |
| Config schema (Pydantic) | ✅ Solid | `MoroConfig` validates, `extra="forbid"` on critical sections |
| Data ingestion (3 formats) | ✅ Working | JSONL/CSV/TXT/Alpaca/messages all normalize |
| Data cleaning + dedup | ✅ Working | Exact + near-dup detection, quality scoring |
| Hardware detection | ✅ Working | CPU/CUDA/MPS all detected, VRAM reported |
| Recipe engine | ✅ Working | Hardware-aware presets, memory breakdown, `fit` estimation |
| Training backend (HF) | ✅ Working | SFTTrainer with QLoRA, gradient checkpointing, val splits |
| Eval scorers | ✅ Working | `contains`, `any_of_contains`, `regex`, `json_schema` scoring |
| Eval runner | ✅ Working | Suite loading, generation, per-case scoring, sha256 integrity |
| Export adapter (safety) | ✅ Improved | Overlap protection, staging, atomic rename, no self-deletion |
| Release gates | ✅ Improved | `check_release_requirements()` is fail-closed and evidence-bound |
| SQLite storage | ✅ Working | WAL, FK constraints, all CRUD operations |
| Diagnose engine | ✅ Working | Pattern matching for OOM/NaN/deps/dataset errors |
| 195 unit tests | ✅ Passing | Core logic validated |

---

## 2. CRITICAL FAILURES — Test Suite (Live Run: 2026-09-17)

These are **active test failures** in the current codebase, not hypothetical:

### 2.1 — `test_snapshot_hashing.py` — **Import Error** 🔴

```
ImportError: cannot import name 'config_snapshot_hash' from 'moro.core.hashing'
```

**What:** A test file (`test_snapshot_hashing.py`) imports `config_snapshot_hash` and `matches_config_snapshot` from `moro.core.hashing`. **These functions do not exist** in [`hashing.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py).

**Impact:** The entire test collection fails with 1 import error, blocking CI. This test covers a versioned hash format `config-json-v1:` that provides layout/key-order invariant config hashing — a feature **needed for reproducibility** that has never been implemented.

**Gap:** `hashing.py` only has `sha256_file`, `sha256_text`, `sha256_directory`. The config snapshot hashing upgrade (`config_snapshot_hash`, `matches_config_snapshot`) was planned but never written.

**What's needed:**
- Implement `config_snapshot_hash(text: str) -> str` — canonical JSON digest with `config-json-v1:` prefix
- Implement `matches_config_snapshot(text: str, digest: str) -> bool` — supports both legacy (raw sha256) and versioned format
- Handle invalid JSON (NaN, Infinity, duplicate keys, non-object) with `ValueError`

---

### 2.2 — `test_export_eligibility.py` — 13 failures 🔴

**Failure group 1: Scientific notation config hash mismatch**
```
test_unchanged_scientific_notation_snapshot_can_export[1e-05] — FAILED
test_unchanged_scientific_notation_snapshot_can_export[1e-06] — FAILED
```
Python's JSON serializer renders `2e-5` differently than `0.00002`, so `sha256_text(cfg.model_dump_json())` produces different digests for configs with small floats. The config hash written at train time doesn't match what `eligibility.py` reads back. This **blocks export for any run where `learning_rate` is in scientific notation**.

**Failure group 2: Unsafe deployment tags not rejected**
```
test_unsafe_deployment_tags_rejected[a/b], [..], [/absolute], [a b], etc. — 11 FAILED
```
The `deploy` command's `--tag` option accepts path traversal strings like `../../escaped`, spaces, newlines, and absolute paths. The test expects exit code 1 but gets 0. **A user can accidentally or deliberately overwrite arbitrary filesystem locations** using the `--tag` parameter in `moro deploy`.

**Failure group 3: Symlinked package directory not rejected**
```
test_deployment_refuses_symlinked_package_directory — FAILED
```
If the releases output directory contains symlinks pointing to sensitive locations, deployment still proceeds. The deploy command doesn't validate the package directory for symlink attacks.

---

### 2.3 — `test_project_privacy.py` — 1 failure 🔴

```
test_initialized_project_git_ignores_private_inputs — FAILED
Expected: data/raw/, weights/, *.gguf, *.safetensors, .env.production, etc.
Got: only .env is excluded
```

The generated `.gitignore` in [`templates/project.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py) **does not protect `data/raw/`** from being staged by Git. A user running `git add .` in their project will commit private training data, model weights, and credentials. This is a **privacy and data safety regression** — the main value proposition of MoroAI is local-only privacy.

---

## 3. Pillar-by-Pillar Gap Analysis

### Pillar 1: Data Compiler

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Dataset versions are mutable (rebuild overwrites historical data) | P1 | [`data.py:108`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L108) | Not fixed |
| Source attribution uses most-recently-imported source, not configured source | P1 | [`data.py:143`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L143) | Not fixed |
| No `--force` behavior connected | P2 | [`data.py:24`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L24) | Declared, unused |
| `--limit` applied after full memory load | P2 | [`data.py:59`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L59) | Not fixed |
| Splitting can produce 0 training rows from tiny datasets | P1 | [`splitter.py:27`](file:///Users/mac/Dev/MoroAI/moro/src/moro/data/splitter.py#L27) | Not fixed |
| No cross-field ratio validation (val+eval ratio can sum > 1.0) | P2 | [`models.py:22`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py#L22) | Not fixed |
| No group-aware splitting (related examples can cross split boundaries) | P2 | [`splitter.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/data/splitter.py) | Not planned |
| Token count is word-based not tokenizer-aware | P2 | [`quality.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py) | Not fixed |
| PII scan is advisory — flagged rows stay in dataset | P2 | [`data.py:92`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L92) | By design but undocumented |
| No split checksums stored, no immutable output dirs | P1 | [`data.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py) | Not fixed |
| No rejection artifact (rejected rows not persisted for audit) | P2 | [`data.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py) | Missing entirely |
| Negative `--limit` not rejected | P2 | [`data.py:59`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L59) | Not fixed |

**Missing module:** [`src/moro/data/dedupe.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/data/) — The spec calls for a separate dedupe module; deduplication lives inside `clean.py` which is fine, but `report.py` is missing near-duplicate field tracking.

---

### Pillar 2: Recipe Engine

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Estimates uncalibrated against real runs | P2 | [`engine.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py) | Documented in warnings |
| Hardware detects total VRAM, not available VRAM | P2 | [`detector.py:24`](file:///Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py#L24) | Not fixed |
| Disk space checked on `/` not project filesystem | P2 | [`detector.py:69`](file:///Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py#L69) | Not fixed |
| Apple MPS VRAM is rough heuristic (75% of RAM) | P2 | [`detector.py:36`](file:///Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py#L36) | Not fixed |
| Training uses OLD estimator, recipe suggest uses NEW planner | P1 | [`hf_backend.py:71`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py#L71) | Diverged |
| Model family detection can match org/directory names | P2 | [`engine.py:55`](file:///Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py#L55) | Not fixed |
| Missing `moro recipe list` and `moro recipe show` CLI commands | P2 | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) | Not implemented |

**Good:** The planner now explicitly labels estimates as uncalibrated heuristics and uses `fit: "unknown"` when parameter count can't be inferred.

---

### Pillar 3: Training Runner

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Runs NOT bound to dataset versions (`dataset_version_id` always None) | P1 | [`train.py:86`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L86) | Not fixed |
| `training.output_dir` config field ignored — always writes to `runs/` | P1 | [`train.py:84`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L84) | Not fixed |
| `--resume` raises ConfigError instead of being implemented | P2 | [`train.py:45`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L45) | Explicit stub |
| No validation data format check before model loads | P2 | [`hf_backend.py:220`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py#L220) | Not fixed |
| Peak VRAM starts after model initialization (misses load peaks) | P2 | [`hf_backend.py:263`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py#L263) | Not fixed |
| Abandoned "running" records not cleaned up after crash | P2 | [`train.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py) | Not implemented |
| `moro runs list` command missing from CLI | P1 | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) | Not implemented |
| `moro runs compare` command missing | P2 | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) | Not implemented |
| Run snapshot doesn't record tokenizer identity or chat template hash | P2 | [`train.py:110`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L110) | Not fixed |
| No dry-run completeness check for dependencies/tokenizer/quantization | P2 | [`train.py:70`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L70) | Not fixed |
| Training report (metrics history) not persisted to `.moro/reports/` | P2 | [`hf_backend.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py) | Not implemented |
| `training/run.py`, `training/checkpoints.py`, `training/metrics.py` | — | — | **Never created** |

**Significant gap:** The spec calls for `training/run.py`, `training/checkpoints.py`, and `training/metrics.py` modules. None of these exist — training orchestration logic is entirely inside `hf_backend.py`. This makes the code harder to test and extend.

---

### Pillar 4: Eval Harness

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Eval ID printed to console ≠ ID stored in DB | P1 | [`eval.py:78`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py#L78) | **Fixed in `db.py:322`** — `add_eval_run` uses `result.get("id")` |
| Generation-only cases (no `expect`) score as `passed=True` | P1 | [`scorers.py:19`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L19) | Present, but gates now reject these for release |
| `--base-model` + `--run-id` now correctly rejected | ✅ Fixed | [`eval.py:51`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py#L51) | Fixed |
| Empty JSON schema `{}` is falsey — skips validation | P2 | [`scorers.py:59`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L59) | Not fixed (empty schema matches anything) |
| Invalid regex patterns produce `False` instead of suite error | P2 | [`scorers.py:51`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L51) | Not fixed |
| Substring `contains` can't distinguish correct from negated answer | P2 | [`scorers.py:32`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L32) | By design, documented limitation |
| No baseline vs. adapter comparison built in | P1 | [`runner.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py) | Missing entirely |
| Inference doesn't preserve training quantization plan | P2 | [`runner.py:37`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py#L37) | Not fixed — uses `model_load_options` without bnb |
| `moro eval list` command missing | P2 | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) | Not implemented |
| `moro eval compare` command missing | P2 | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) | Not implemented |
| `eval/report.py` module never created | — | — | **Missing** |
| No suite hash recorded when `max_samples` limits evaluation | P2 | [`runner.py:85`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py#L85) | Not fixed |

---

### Pillar 5: Release Pipeline

| Issue | Severity | File | Status |
|-------|----------|------|--------|
| Export manifest has empty `artifact_paths=[]` | P1 | [`export.py:58`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py#L58) | Not fixed |
| Export manifest has empty `eval_summary={}` | P1 | [`export.py:59`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py#L59) | Not fixed |
| Dataset version not populated in manifest (`dataset_version_id=None`) | P1 | [`export.py:54`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py#L54) | Not fixed |
| Exported artifacts not registered in `artifacts` DB table | P1 | [`export.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py) | Not implemented |
| Ollama Modelfile uses **absolute path** to adapter | P1 | [`ollama.py:52`](file:///Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py#L52) | Not fixed — `ADAPTER {adapter_path.resolve()}` |
| Ollama package is not self-contained (breaks on move/copy) | P1 | [`ollama.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py) | Not fixed |
| No proven Ollama create-and-run acceptance test | P1 | — | Missing |
| Deploy `--tag` accepts path traversal strings | P1 | [`deploy.py:21`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py#L21) | **Active test failure** |
| Deploy does not reject symlinked package directories | P1 | [`deploy.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py) | **Active test failure** |
| `gguf` format export is an explicit non-stub exit-0 placeholder | P2 | Architecture doc | Not implemented — should be `NotImplementedError` with exit 1 |
| `merged` format export not implemented | P2 | — | Not implemented |
| `export/adapter.py` module listed in spec | — | — | **Never created** |
| `export/gguf.py` module listed in spec | — | — | **Never created** |
| `export/model_card.py` standalone module listed in spec | — | — | Logic lives in `manifest.py`, not a dedicated module |

---

## 4. Modules Specified but Never Created

From the MVP spec's folder structure, these are **entirely missing**:

| Spec Path | What It Should Do |
|-----------|-------------------|
| `src/moro/core/context.py` | Run context / execution state management |
| `src/moro/core/logging.py` | Structured logging to `.moro/logs/` |
| `src/moro/training/run.py` | Run record management & state machine |
| `src/moro/training/checkpoints.py` | Checkpoint tracking, resume logic |
| `src/moro/training/metrics.py` | Metrics collection, loss history, report |
| `src/moro/eval/report.py` | Eval report rendering (CLI currently prints inline) |
| `src/moro/export/adapter.py` | Dedicated adapter export logic |
| `src/moro/export/gguf.py` | GGUF conversion wrapper |
| `src/moro/diagnose/recommendations.py` | Separated recommendation engine from analyzer |
| `src/moro/storage/queries.py` | SQL query layer (all queries in `db.py` directly) |
| `src/moro/utils/` (entire folder) | `yaml.py`, `json.py`, `text.py`, `system.py` helpers |
| `templates/project/` folder structure | The spec asks for a directory of templates, not just Python strings |
| `Makefile` | Listed in spec as part of repo root |
| `moro.yaml.example` | Example config at repo root |

---

## 5. CLI Commands Specified but Missing

| Command | Status |
|---------|--------|
| `moro runs list` | **Missing** — `list_runs` exists in `db.py` but no CLI command |
| `moro runs compare` | **Missing entirely** |
| `moro eval list` | **Missing entirely** |
| `moro eval compare` | **Missing entirely** |
| `moro recipe list` | **Missing entirely** |
| `moro recipe show` | **Missing entirely** |
| `moro config show` | **Missing entirely** |
| `moro data guard` | **Missing entirely** |
| `moro hardware` | **Missing** — folded into `doctor`, not a separate command |

---

## 6. Database / Storage Gaps

| Issue | Severity |
|-------|----------|
| No schema migration mechanism — adding columns to existing DBs will fail silently or error | P1 |
| `dataset_version_id` in `runs` table always `NULL` — lineage completely broken | P1 |
| Run statuses are free-form strings — no constraint ensures valid values | P2 |
| `artifacts` table exists but is never populated by any command | P1 |
| Project identity based on mutable name — renaming breaks all run references | P2 |
| No `releases` table in schema — releases tracked only on filesystem | P2 |
| `get_latest_run` fetches any latest run then checks status — can hide old completed run | P2 |
| Version number uses `COUNT(*) + 1` — race condition under concurrent build | P2 |

---

## 7. Configuration / Schema Gaps

| Issue | Severity | Location |
|-------|----------|----------|
| `ProjectConfig`, `DatasetConfig`, `ModelConfig`, `TrainingConfig`, `EvalConfig`, `AdapterConfig` all missing `extra="forbid"` | P1 | [`models.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py) |
| `model.name` can be blank string (only `DatasetConfig.source` has explicit validator) | P2 | [`models.py:34`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py#L34) |
| `validation_ratio + eval_ratio` can sum to 1.0 leaving zero training rows | P1 | [`models.py:22`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py#L22) |
| `training.output_dir` exists but is completely disconnected from behavior | P1 | [`train.py:84`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L84) |
| `eval.base_model` and `eval.max_samples` fields are set but not consumed by `eval run` | P2 | [`eval.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/eval.py) |
| `release.export` list (formats) not enforced — any format accepted even if unsupported | P2 | [`export.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py) |

---

## 8. Privacy & Security Gaps

| Issue | Severity | Status |
|-------|----------|--------|
| `.gitignore` in generated projects doesn't protect `data/raw/` | P1 (active test failure) | [`templates/project.py:1`](file:///Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py#L1) |
| `.gitignore` doesn't ignore `*.safetensors`, `*.bin`, `*.gguf` model weights | P1 | Same |
| `.gitignore` doesn't ignore `.env.production` or secrets | P1 | Same |
| `--tag` in deploy accepts path traversal strings → filesystem escape | P1 (active test failure) | [`deploy.py:21`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py#L21) |
| PII scan flags rows but never blocks/quarantines them | P2 | [`data.py:92`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L92) |
| Ollama Modelfile contains absolute adapter path — leaks file system layout | P2 | [`ollama.py:52`](file:///Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py#L52) |
| No documented test of "no network calls in local_only mode" | P2 | — |

---

## 9. Things You May Not Know Yet (Non-Obvious Risks)

These aren't bugs — they're **design-level risks** that become problems at real scale:

### 9.1 Fine-tuning Can Appear to Succeed While Making the Model Worse
Loss going down ≠ model improving. Without baseline-vs-adapter comparison on a holdout set, you have no evidence of actual improvement. MoroAI currently has no `moro eval compare` command and no paired baseline measurement.

### 9.2 Evaluation Leakage Is Invisible
If related examples from the same source document, customer, or conversation appear in both training and eval splits, pass rates will be inflated. The current random splitter has no grouping awareness. A user building a support assistant from ticket threads could unknowingly train AND evaluate on the same customer's tickets.

### 9.3 Truncation Can Remove the Answer Being Learned
A long conversation may consume the entire context window, leaving zero tokens for the assistant turn. The model is penalized on loss for generating nothing it should generate. `approximate_token_count` is word-based, not tokenizer-aware — so a conversation that "passes" the token check can still be silently truncated during training.

### 9.4 An Adapter Is Not a Self-Contained Model
The Ollama Modelfile references an absolute adapter path. If the user moves, archives, or shares the release package, it breaks. The adapter also depends on: (1) specific base model revision, (2) specific tokenizer + chat template, (3) specific PEFT version. None of these are pinned in the release manifest.

### 9.5 A Seed Is Not a Reproducibility Guarantee
The `project.seed` is passed to `set_seed()` and `data_seed`. But hardware, kernel versions, library updates, and cuDNN nondeterminism can all produce different results with the same seed. MoroAI should document the distinction between "reproducible inputs" and "bitwise-identical execution."

### 9.6 Concurrent Use Is Unsafe
Two terminal windows running `moro data build` simultaneously will produce race conditions on split files and version numbers. The count-based version numbering (`COUNT(*) + 1`) is not atomic. This matters even for solo users with scripted workflows.

### 9.7 Data Deletion Doesn't Cascade
Deleting `data/raw/your-data.jsonl` doesn't remove examples from normalized copies, checkpoints, the trained adapter (weights), or eval outputs. Users who need to honor data deletion requests (GDPR, internal policy) have no tooling for this.

### 9.8 Model Cards Can Overstate Evidence
The generated `model_card.md` shows `N/A` for evaluation results if no eval data is passed. But the card still says "fine-tuned using MoroAI" — creating the impression of validated quality without supporting evidence. The manifest has `eval_summary: {}`.

---

## 10. Test Coverage Gaps

| Missing Test | Why It Matters |
|--------------|----------------|
| Rebuild without changing previous dataset version contents | Core lineage guarantee |
| Build after importing source A then B — verify A is used | Source attribution correctness |
| Retrieve eval report using the exact printed ID | Eval ID consistency |
| Export blocks runs with failed/cancelled status | Release safety |
| Deploy with path-traversal `--tag` is rejected | Security (active failure) |
| Generated `.gitignore` protects all private file types | Privacy (active failure) |
| Config with unknown keys is rejected | Config safety |
| `validation_ratio + eval_ratio = 1.0` is rejected | Data correctness |
| Ollama package runs independently of original run directory | Deployment correctness |
| CUDA/MPS training integration (full forward pass) | Hardware support |
| `moro runs list` returns expected rows | CLI completeness |

---

## 11. MVP Deployment Checklist

### 🔴 Blockers — Must Fix Before MVP

| # | Task | Location |
|---|------|----------|
| B1 | Implement `config_snapshot_hash` / `matches_config_snapshot` in `hashing.py` | [`hashing.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py) |
| B2 | Fix `deploy --tag` path traversal security issue | [`deploy.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py) |
| B3 | Fix generated `.gitignore` to protect `data/raw/`, `*.safetensors`, `*.gguf`, `*.bin`, secrets | [`templates/project.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/templates/project.py) |
| B4 | Fix config snapshot scientific notation serialization bug | [`eligibility.py:86`](file:///Users/mac/Dev/MoroAI/moro/src/moro/export/eligibility.py#L86) |
| B5 | Bind runs to dataset versions (`dataset_version_id` must be set) | [`train.py:86`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L86) |
| B6 | Fix dataset version mutability — each build must write to immutable versioned path | [`data.py:108`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L108) |
| B7 | Fix dataset source attribution — use configured source not most-recent import | [`data.py:143`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py#L143) |
| B8 | Fix Ollama Modelfile to use relative adapter path or copy adapter into package | [`ollama.py:52`](file:///Users/mac/Dev/MoroAI/moro/src/moro/export/ollama.py#L52) |
| B9 | Implement `moro runs list` CLI command | [`main.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/main.py) |
| B10 | Add `extra="forbid"` to all config model sections | [`models.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py) |
| B11 | Add cross-field ratio validation (`validation_ratio + eval_ratio < 1.0`) | [`models.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/config/models.py) |
| B12 | Populate `artifact_paths` and `eval_summary` in export manifest | [`export.py:54`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py#L54) |
| B13 | Register exported artifacts in `artifacts` DB table | [`export.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py) |
| B14 | Reject symlinked package directories in deploy | [`deploy.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py) |
| B15 | All 14 active test failures must be green before release | test suite |

---

### 🟡 Important — MVP Quality

| # | Task | Location |
|---|------|----------|
| Q1 | Write core logging to `.moro/logs/` (training output, errors) | New: `core/logging.py` |
| Q2 | Add `moro runs compare` to compare two runs' metrics | New CLI command |
| Q3 | Unify training memory estimator with recipe engine | [`hf_backend.py:71`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py#L71) |
| Q4 | Add tokenizer-aware token count (use `AutoTokenizer` for measurements) | [`quality.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py) |
| Q5 | Detect and recover abandoned "running" runs on startup | [`train.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py) |
| Q6 | Add `moro config show` command | New CLI command |
| Q7 | Add schema migration mechanism for existing SQLite databases | [`db.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py) |
| Q8 | Add training report saved to `.moro/reports/training_report.json` | [`hf_backend.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py) |
| Q9 | Fix `empty JSON schema {}` being falsey — empty schema should error | [`scorers.py:59`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L59) |
| Q10 | Fix invalid regex → should raise `EvalError`, not silently fail | [`scorers.py:51`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py#L51) |
| Q11 | Honor `training.output_dir` config field | [`train.py:84`](file:///Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py#L84) |
| Q12 | Add baseline-vs-adapter eval comparison (even basic side-by-side) | [`runner.py`](file:///Users/mac/Dev/MoroAI/moro/src/moro/eval/runner.py) |
| Q13 | Add `moro eval list` CLI command | New CLI command |
| Q14 | Produce a `Makefile` and `moro.yaml.example` for the repo | Repo root |

---

### 🟢 Post-MVP / Nice-to-Have

| # | Task |
|---|------|
| P1 | Releases table in SQLite with full provenance chain |
| P2 | `moro data guard` — explicit privacy/toxicity scanning command |
| P3 | `moro hardware` as a standalone command (currently inside `doctor`) |
| P4 | Group-aware splitting to prevent evaluation leakage |
| P5 | GGUF export via `llama.cpp` converter integration |
| P6 | Merged model export (full weight merge before export) |
| P7 | `moro resume` for checkpoint recovery |
| P8 | Windows CI coverage (currently Linux-only) |
| P9 | macOS/Apple Silicon CI coverage |
| P10 | Unsloth backend as optional fast-training alternative |

---

## 12. What "MVP-Deployable" Actually Means

The correct MVP readiness standard is:

> **An immutable dataset version produces a traceable run; that run receives a trustworthy evaluation comparison; enforced release requirements permit a checksummed package; and that package runs independently of the original workspace.**

**Current distance from that standard:**

```
Immutable dataset    → ❌ Not yet (datasets are mutable)
Traceable run        → ❌ Not yet (dataset_version_id always NULL)
Trustworthy eval     → ⚠️  Partial (gates work, no baseline comparison)
Enforced requirements → ✅ Gates exist and are fail-closed
Checksummed package  → ⚠️  Partial (adapter checksummed, artifacts empty)
Portable package     → ❌ Not yet (Ollama uses absolute paths)
```

**Milestone to reach MVP:**

1. Fix all 14+1 test failures (B1–B15)
2. Immutable dataset versions (B6–B7)
3. Run-to-version binding (B5)
4. Portable Ollama package (B8)
5. Full manifest evidence (B12–B13)
6. Run one demonstrated end-to-end: `import → build → train → eval → export → ollama create → ollama run`

Once those six milestones are done, MoroAI is genuinely MVP-deployable.

---

## 13. Recommended Next Session Priorities

```
1. hashing.py     → Add config_snapshot_hash + matches_config_snapshot  [B1]
2. templates/     → Fix .gitignore to protect private data               [B3]  
3. deploy.py      → Validate and sanitize --tag input                    [B2]
4. eligibility.py → Fix scientific notation config hash                  [B4]
5. data.py        → Immutable versioned output dirs + correct source     [B6, B7]
6. train.py       → Bind dataset_version_id + honor output_dir           [B5, Q11]
7. ollama.py      → Copy adapter into package, use relative path         [B8]
8. export.py      → Populate artifacts + eval_summary in manifest        [B12]
9. models.py      → extra="forbid" + ratio cross-field validation        [B10, B11]
10. main.py       → Add moro runs list command                           [B9]
```

After those 10 tasks, run the full test suite. Everything should be green and the project crosses the MVP threshold.
