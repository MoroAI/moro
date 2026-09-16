# Contributing to MoroAI

Moro is in early development. Contributions should improve bringing private data in, cleaning it, choosing workable training settings, measuring model quality, deploying locally, or reproducing a run.

## Setup and checks

```bash
git clone git@github.com:MoroAI/moro.git
cd moro
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest -q
ruff check .
ruff format --check .
```

Core tests must run without model downloads, network access, or training libraries. Use synthetic fixtures and mocked backends for lifecycle tests. Real GPU validation should report model revision, package versions, hardware, dataset size, peak memory, and evaluation results.

Keep changes focused, describe the user-visible problem, and include validation results. Discuss substantial architectural changes in an issue first. Mark experimental integrations clearly rather than claiming support from a dry-run alone.

Do not submit private datasets, credentials, generated runs, or model weights. Use minimal synthetic reproductions for bug reports. Be respectful and constructive in reviews.

See [engineering status](docs/engineering-status.md) for known gaps and priorities.
