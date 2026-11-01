"""Dependency lock files freeze the runtime supply chain.

pyproject.toml declares compatible ranges, so without a lock every fresh
install can resolve a different tree (the FastAPI 0.147 -> 0.149 drift).
requirements/*.lock record the exact shipped versions; these tests guard
the lock invariants, the Dockerfile wiring, and the CI frozen checks.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = ROOT / "requirements"
EVAL_LOCK = REQUIREMENTS / "eval.lock"
TRAIN_LOCK = REQUIREMENTS / "train.lock"
PYPROJECT = ROOT / "pyproject.toml"
DOCKERFILE = ROOT / "Dockerfile"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

PIN_LINE = re.compile(r"^[A-Za-z0-9_.\-]+==[^ \t*<>~=!;]+$")
FLOATING_OPS = (">=", "~=", "!=", ">", "<", "*")


def read_lines(path):
    return path.read_text().splitlines()


def pin_entries(path):
    """Non-comment requirement lines from a lock file."""
    entries = []
    for line in read_lines(path):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            continue
        entries.append(stripped)
    return entries


def train_extra_pins():
    """Verbatim == pins declared in pyproject's train extra."""
    text = PYPROJECT.read_text()
    start = text.index("train = [")
    end = text.index("]", start)
    block = text[start:end]
    return re.findall(r'"([A-Za-z0-9_.\-]+==[^"]+)"', block)


@pytest.mark.parametrize("lock", [EVAL_LOCK, TRAIN_LOCK])
def test_lock_file_is_fully_pinned(lock):
    assert lock.is_file(), f"missing lock file: {lock.name}"
    entries = pin_entries(lock)
    assert entries, f"{lock.name} has no pinned entries"
    for entry in entries:
        name = entry.split("==")[0] if "==" in entry else entry
        assert "==" in entry, f"{lock.name}: {name} is not pinned: {entry!r}"
        assert not any(op in entry.split("==", 1)[1] for op in FLOATING_OPS), (
            f"{lock.name}: {name} has a floating specifier: {entry!r}"
        )
        assert PIN_LINE.match(entry), f"{lock.name}: malformed pin: {entry!r}"


def test_eval_lock_freezes_fastapi_to_single_version():
    pins = [e for e in pin_entries(EVAL_LOCK) if e.split("==")[0] == "fastapi"]
    assert len(pins) == 1, f"expected one fastapi pin, got: {pins}"
    version = tuple(int(p) for p in pins[0].split("==")[1].split("."))
    assert version >= (0, 100, 0), f"fastapi pin below pyproject floor: {pins[0]}"


def test_train_lock_keeps_declared_train_pins_verbatim():
    declared = train_extra_pins()
    assert "torch==2.14.1" in declared
    assert "aiohttp==3.14.4" in declared
    locked = pin_entries(TRAIN_LOCK)
    for pin in declared:
        assert pin in locked, f"train lock moved declared pin {pin}"


@pytest.mark.parametrize("package", ["torch", "aiohttp"])
def test_train_lock_pins_critical_packages_exactly_once(package):
    pins = [e for e in pin_entries(TRAIN_LOCK) if e.split("==")[0] == package]
    assert len(pins) == 1, f"expected one {package} pin, got: {pins}"


@pytest.mark.parametrize(
    "lock,extras",
    [(EVAL_LOCK, "--extra eval"), (TRAIN_LOCK, "--extra eval --extra train")],
)
def test_lock_header_records_pyproject_source(lock, extras):
    header = "\n".join(line for line in read_lines(lock) if line.startswith("#"))
    assert "uv pip compile" in header
    assert "pyproject.toml" in header
    assert extras in header


def test_dockerfile_installs_frozen_eval_lock():
    text = DOCKERFILE.read_text()
    assert "FROM python:3.11-slim" in text
    assert "COPY requirements/eval.lock ./requirements/eval.lock" in text
    assert "-r requirements/eval.lock" in text
    assert "--no-deps" in text
    assert '".[eval]"' not in text, "Dockerfile must not resolve .[eval] ranges"


def test_ci_enforces_frozen_locks():
    text = CI_WORKFLOW.read_text()
    assert "-c requirements/eval.lock" in text
    assert "-c requirements/train.lock" in text
    assert "uv pip compile" in text
    assert "diff -u requirements/eval.lock" in text
    assert "diff -u requirements/train.lock" in text
