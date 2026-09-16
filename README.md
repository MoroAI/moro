# Moro

**MoroAI** is a local-first CLI for adapting open language models to private data.

Turn private data into reliable local models: import → clean → choose a recipe → train → evaluate → deploy.

Moro is for engineers and small teams building private support assistants, domain Q&A, and structured extraction workflows. The current focus is a repeatable local workflow on consumer hardware.

## Status

Early development. The core CLI, dataset workflow, recipe heuristics, and training dry-run have automated coverage without downloading models. A real offline CPU smoke test validates one-step LoRA training, validation loss, checkpoint creation, and adapter reload for generation. Training, model-backed evaluation, and deployment integrations remain experimental and have **not yet been validated end to end on a GPU**. This is not a production release.

## Install from source

Python 3.10 or newer:

```bash
git clone git@github.com:MoroAI/moro.git
cd moro
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Use the source checkout for now; package publication is not part of this setup.

## Try the local workflow

From the repository root:

```bash
moro init /tmp/moro-demo
cp examples/support.jsonl /tmp/moro-demo/data/raw/support.jsonl
cd /tmp/moro-demo
moro import data/raw/support.jsonl --name support
moro data build
moro data report
moro status
moro doctor
moro recipe suggest
moro train --dry-run
```

The sample data is synthetic and only demonstrates the workflow. Dry-run validates the normalized training rows and prints a rough memory estimate; it does not check installed training dependencies or prove a model will fit in memory.

The default config reads `data/raw/support.jsonl`. For another filename, update `dataset.source` in `moro.yaml`. Import registers a source but does not change that setting. Existing import destinations are protected against overwriting.

## Commands

| Command | Current behavior |
| --- | --- |
| `moro init PATH` | Create project configuration and folders |
| `moro import SOURCE` | Copy, link, or register raw input |
| `moro data build` | Normalize, clean, deduplicate, score, and split data |
| `moro data report` | Show dataset statistics; supports JSON |
| `moro status` | Inspect project state; supports JSON |
| `moro doctor` | Inspect hardware and dependencies |
| `moro recipe suggest` | Suggest heuristic settings; supports JSON |
| `moro train --dry-run` | Validate data and estimate memory without ML dependencies |
| `moro train` | Experimental Hugging Face adapter training |
| `moro eval run SUITE` | Experimental model evaluation |
| `moro export` | Experimental artifact export |
| `moro deploy --target ollama` | Prepare deployment files; does not launch Ollama |
| `moro diagnose` | Inspect recorded training failures |

Use `moro COMMAND --help` for options. Recipe suggestions do not update `moro.yaml`; apply the settings manually before training. Estimates are heuristics, especially for custom models and sequence lengths. CPU and Apple hardware receive conservative unquantized suggestions; MPS training is unverified.

## Experimental training

```bash
python -m pip install -e '.[train]'
# For CUDA quantization, additionally install:
python -m pip install -e '.[cuda]'
```

The backend uses a pinned Hugging Face / PEFT / TRL reference stack with an optional real CPU integration test. Actual CUDA training still needs hardware validation. See [training validation](docs/training-validation.md) for the environment and test scope. Checkpoint resume is explicitly unsupported. Failed and interrupted runs record their terminal status in SQLite, with configuration and training-data checksum snapshots in the run directory.

Data preparation and dry-run work locally. In `local_only` mode, training and evaluation resolve local directories or cached model snapshots and fail if weights are missing. `allow_external` permits downloads. Pre-download the selected model revision or use local model paths. Raw and processed datasets, credentials, and model weights should remain outside source control.

## Development

```bash
python -m pytest -q
ruff check .
ruff format --check .
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and the [engineering status](docs/engineering-status.md) for the next milestones. CI runs core tests, lint, formatting, and package build checks on Python 3.10–3.12 without training dependencies.

## License

[Apache License 2.0](LICENSE).
