# Dependency lock files

`pyproject.toml` declares compatible ranges for the runtime (`typer>=0.12`,
`fastapi>=0.100.0`, ...) so local installs keep working, but ranges drift:
every fresh `pip install` can resolve a different tree (e.g. FastAPI
0.147 -> 0.149 broke a deploy with no code change). These lock files are the
frozen, reviewed record of exactly which versions ship.

| File        | Contents                          | Target                                   | Used by                          |
|-------------|-----------------------------------|------------------------------------------|----------------------------------|
| `eval.lock` | runtime + `eval` extra (32 pkgs)  | CPython 3.10, `x86_64-manylinux_2_28`    | `Dockerfile`, CI `core` + release tests |
| `train.lock`| runtime + `eval` + `train` (89 pkgs) | CPython 3.11, `x86_64-manylinux_2_28` | CI `training-cpu`                |

Targets match where the locks are consumed: the Docker image
(`python:3.11-slim`, glibc 2.36), CI `ubuntu-latest` runners, and the CI
Python floor (3.10) for the eval lock. The locks are Linux-targeted; macOS
developers keep using `pip install -e '.[dev,eval]'` (ranges still resolve
there).

## Regenerating

Requires the same uv version CI checks with (see
`.github/workflows/ci.yml`, currently `uv==0.7.13`):

```bash
python -m pip install 'uv==0.7.13'
uv pip compile pyproject.toml --extra eval \
    --python-version 3.10 --python-platform x86_64-manylinux_2_28 \
    --custom-compile-command "uv pip compile pyproject.toml --extra eval --python-version 3.10 --python-platform x86_64-manylinux_2_28 -o requirements/eval.lock" \
    -o requirements/eval.lock
uv pip compile pyproject.toml --extra eval --extra train \
    --python-version 3.11 --python-platform x86_64-manylinux_2_28 \
    --custom-compile-command "uv pip compile pyproject.toml --extra eval --extra train --python-version 3.11 --python-platform x86_64-manylinux_2_28 -o requirements/train.lock" \
    -o requirements/train.lock
```

(The `--custom-compile-command` keeps the header byte-identical between the
committed file and the CI freshness check, which recompiles into `/tmp`.)

Without `--upgrade`, `uv pip compile` keeps the versions already pinned in
the existing output file, so re-running after a `pyproject.toml` edit only
moves what must move. Pass `-U` / `-P <pkg>` deliberately to roll versions
forward, then run the test suite and commit the lock diff for review.

## How the freeze is enforced

- **Docker** (`Dockerfile`, still `python:3.11-slim`) installs the service
  stack with `pip install -r requirements/eval.lock` and then the package
  itself with `pip install --no-deps .`, so the image cannot resolve
  anything outside the lock.
- **CI** installs with the locks as constraints
  (`pip install -c requirements/eval.lock ...`,
  `pip install -c requirements/train.lock ...`).
- **CI `lockfile` job** re-resolves both locks from `pyproject.toml`
  (seeded from the committed files, so only requirement changes - not new
  PyPI releases - produce diffs) and fails on any byte difference.
- **`tests/test_lockfile.py`** guards the invariants in-repo: every entry
  is `==`-pinned, FastAPI resolves to a single version, the declared
  `train` pins (`torch==2.14.1`, `aiohttp==3.14.4`, ...) are kept verbatim,
  and the Dockerfile/CI references stay wired.

## Deliberate trade-offs

- **Pins, not hashes.** Hash (`--require-hashes`) locks over-fit a single
  interpreter build (e.g. `pydantic-core` cp310 vs cp311 wheels have
  different hashes), which conflicts with the 3.10/3.11/3.12 CI matrix.
  `==` pins stop version drift while staying installable everywhere.
- **`train.lock` resolves torch from the default index.** The exact
  `torch==2.14.1` pin in `pyproject.toml` is incompatible with uv's
  `--torch-backend cpu` rewrite (`2.14.1+cpu`), so the lock records default
  (CUDA) build versions while CI pre-installs the CPU wheel from the
  PyTorch CPU index first - `==2.14.1` is already satisfied, and the lock
  acts as constraints for everything else. Installing `train.lock` with
  `-r` directly yields the CUDA stack instead.
