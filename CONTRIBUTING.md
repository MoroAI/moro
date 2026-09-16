# Contributing to MoroAI

Thanks for your interest in MoroAI.

MoroAI is an early-stage open-source project focused on building a local-first model adaptation foundry.

The current priorities are:

- dataset ingestion and normalization
- dataset quality and validation
- low-VRAM training recipes
- evaluation harness design
- export and local deployment workflows
- CLI usability and documentation

## Ground rules

- Be respectful and constructive.
- Keep pull requests focused.
- Open an issue before starting large changes.
- Prefer small, reviewable changes over large rewrites.
- Update docs when changing user-facing behavior.

## Areas where contributions are especially helpful

- dataset cleaning heuristics
- eval scorers
- eval suite examples
- low-VRAM recipe validation
- documentation
- CLI improvements
- bug reports with reproducible steps

## Development setup

```bash
git clone https://github.com/moroai/moro.git
cd moro
python -m venv .venv
source .venv/bin/activate
pip install -e .
