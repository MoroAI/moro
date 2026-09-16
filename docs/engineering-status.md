# Engineering status — 2026-09-16

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

The local suite passes 83 tests on Python 3.14. Lint and formatting checks pass. Wheel and source distribution builds pass. No real model training or model-backed evaluation was performed. CI is configured but has not run remotely.

## Next milestones

1. Establish a tested training dependency range and CUDA smoke run. Verify trainer API compatibility, k-bit preparation, chat formatting, validation loss, and checkpoint semantics.
2. Enforce local-only model loading when requested; make cache/download behavior explicit.
3. Persist immutable dataset versions and bind each run to its actual inputs. Current versions point to files that can be rebuilt in place.
4. Implement baseline-versus-adapter evaluation and enforce release gates. Verify adapters are loaded correctly and errors cannot be mistaken for model quality evidence.
5. Validate export artifacts, supported model formats, and an actual Ollama import. Merged/GGUF paths and automatic release approval remain incomplete.
6. Make recipe suggestions directly applicable with a reviewable config change and validate memory estimates empirically.

Some scaffold options remain incomplete: data-build `--force` has no cache to bypass, and `--resume` now fails explicitly rather than silently starting a new run. `moro data build --config` now honors the alternate configuration. Recipe estimates for custom models remain low-confidence.

## Repository

The canonical checkout is `/Users/mac/Dev/MoroAI/moro`, with origin `git@github.com:MoroAI/moro.git`. It preserves the original main-branch history. The parent `MoroAI` directory contains this checkout only. All project files and the local virtual environment live inside `moro`; generated files and the virtual environment are excluded from Git.

The supplied design documents remain reference material in `instructions/`. No GitHub settings, issues, or boards were changed.
