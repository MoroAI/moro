# MoroAI

**MoroAI** is a local-first model adaptation foundry.

> Build, evaluate, and deploy private local language models — without cloud dependencies.

## What it is

MoroAI manages the full lifecycle of turning messy private data into a reliable, deployable local model:

```
raw data → clean dataset → hardware-safe recipe → QLoRA training → eval → export → Ollama deploy
```

## Quickstart

```bash
pip install moroai

moro init my-project
cd my-project

# add your data
cp your-data.jsonl data/raw/

moro import ./data/raw/your-data.jsonl --name my-data
moro data build
moro data report

moro doctor
moro recipe suggest

moro train
moro eval run eval/support-golden-v1.yaml

moro export --format adapter
moro deploy --target ollama
```

## Core commands

| Command | Description |
|---------|-------------|
| `moro init` | Create a new MoroAI project |
| `moro status` | Show current project status |
| `moro doctor` | Check environment and hardware readiness |
| `moro import` | Import raw dataset files |
| `moro data build` | Normalize, clean, and split dataset |
| `moro data report` | Show dataset quality report |
| `moro recipe suggest` | Suggest hardware-safe training recipe |
| `moro train` | Run fine-tuning |
| `moro eval run` | Run evaluation suite |
| `moro export` | Export run artifacts |
| `moro deploy` | Prepare local deployment |
| `moro diagnose` | Diagnose failures and suggest fixes |

## Design principles

- **Local-first by default** — works without cloud services
- **Recipes over raw config** — hardware-aware safe defaults
- **Trust is first-class** — eval, safety checks, and model cards built in
- **Reproducible by design** — every run is fully auditable
- **Small models are first-class** — optimized for 0.5B–8B models on consumer hardware

## Installation

```bash
# Core CLI only
pip install moroai

# With training support
pip install "moroai[train]"

# Development
pip install -e ".[dev]"
```

## Requirements

- Python 3.10+
- For training: CUDA-capable GPU or Apple Silicon (MPS)
- Disk space for model weights and checkpoints

## License

Apache 2.0
