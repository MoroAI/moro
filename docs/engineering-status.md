# Engineering status — 2026-09-26

## Verified locally

- CLI imports and every command's help page.
- Project initialization, JSONL import, normalization, cleaning, dataset report, status, and dry-run.
- Imports already inside `data/raw/` and rejection of destination collisions.
- Content-based exact deduplication and case/whitespace deduplication that preserves message roles.
- Inclusive quality thresholds and zero quality for incomplete conversations.
- Recipe selection without fractional VRAM gaps, bounded by detected CUDA capacity.
- Non-CUDA suggestions avoid quantization and bitsandbytes optimizers.
- Training failures and interrupts are persisted, with config and dataset checksum snapshots.
- Unit tests for configuration, storage, normalization, quality, scoring, and diagnostics.
- Immutable dataset versioning with content-addressed manifests bound to each run.
- Release gates: export blocked unless eval evidence matches exact adapter hash.
- Fail-closed export: symlinks and non-materialized adapters rejected at eligibility check.

**256 tests passed, 1 skipped** on Python 3.14. Lint and formatting checks pass.

## New in this session (2026-09-26)

### Export formats extended
- `moro export --format merged` — merges LoRA adapter into base model weights via
  PEFT `merge_and_unload`, saves a standalone transformers model directory.
- `moro export --format gguf` — merges first, then either generates a llama.cpp shell
  script or invokes `convert_hf_to_gguf.py` + `llama-quantize` directly if
  `--llama-cpp` is provided. Supports `--gguf-quant` (q4_k_m, q5_k_m, q8_0, f16).
- All formats display the gate status summary before writing artifacts.

### Eval comparison
- `moro eval compare <suite> --base-model <model> [--run-id <id>]` runs the eval
  suite against both the base model and the fine-tuned adapter, computes per-case
  improvement/regression deltas, and prints a rich summary panel + per-case table.
- Both results are persisted to the project database.
- `moro/eval/compare.py` contains the `compare_eval` function and `_compute_delta`
  — importable for programmatic use.

### Recipe apply
- `moro recipe apply` reads the hardware-suggested recipe, shows a YAML preview,
  prompts for confirmation, backs up `moro.yaml` with a UTC timestamp suffix, then
  deep-merges the patch into the existing config preserving all other keys.
- `--yes` / `-y` flag skips the confirmation prompt (CI-safe).
- `moro recipe suggest` now prints the apply command in its footer.

### Data inspect
- `moro data inspect [--split train|validation|eval|dataset] [--n N] [--offset N]`
  reads sample rows from the latest built dataset snapshot and prints role-coloured
  conversation turns. Long content truncated at 300 chars. `--format json` emits raw.

### Runs CLI rewrite
- `moro runs list` now renders a rich table: ID, name, status (coloured), model,
  train loss, val loss, peak VRAM, throughput, and finish time.
- `moro runs show <run-id>` shows full run details including output path and error.
- `moro runs compare <id1> <id2>` now renders a delta table with colour-coded
  numeric changes (green = better for loss, red = worse).
- Adds `--status` filter to `moro runs list`.

### Diagnose enhanced
- `moro diagnose` now scans the run's output directory for `training_report.json`
  and `*.log` files to extract deeper error context (last 200 lines, first traceback).
- Config change suggestions now shown as a rich table with a note to use
  `moro recipe apply`.
- `--scan-logs/--no-scan-logs` flag controls log scanning (default: on).
- `--json` output includes full diagnosis struct.

## Next milestones

1. Validate the pinned training stack on CUDA. Trainer API, k-bit prep, and chat
   formatting are implemented; CUDA validation remains pending.
2. Validate real Ollama import end-to-end with a locally downloaded model.
3. Empirically validate memory estimates against a real training run and calibrate
   the heuristic coefficients in `recipes/rules.py`.
4. Evaluate token throughput on a real GPU run and surface in `moro doctor`.
5. Custom tokenizer model families — extend coverage in target-module heuristics.
6. Checkpoint resume support (currently fails explicitly with a helpful message).

## Repository

The canonical checkout is `/Users/mac/Dev/MoroAI/moro`, with origin
`git@github.com:MoroAI/moro.git`. All project files and the local virtual
environment live inside `moro`; generated files and the virtual environment are
excluded from Git. The supplied design documents remain reference material in
`instructions/`.
