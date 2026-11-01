# Validation record — October 5, 2026

All results refer to the local remediation branch, not a pushed commit or remote CI run. Raw evidence is in [evidence](evidence/README.md). Counts include existing tests and new regressions; a count alone is not a security or quality assessment.

| Check | Result | What it establishes |
|---|---|---|
| Native Python 3.12 complete suite | **451 passed, 3 skipped**, 3 warnings | Core contracts and security/data/API regressions; optional real training skipped in native environment. |
| Linux Python 3.11 complete suite, new training environment | **454 passed**, 12 warnings | Same suite plus three real offline CPU training cases. |
| Dataset API regression subset | **26 passed** | Verified compiled preview, corrupt snapshot rejection, immutable-version rejection, bounded preview and existing dashboard contracts. |
| Real CPU integration from installed final wheel | **3 passed** | Backend, SDK and controlled recovery work using site-packages outside the source checkout. |
| Live service checks | **47 passed** | Native/alternate/Compose login, protected APIs/assets, rejected host/origin/terminal; gateway empty inventory and missing-model error; webhook auth/validation/replay conflict. |
| Ruff lint / format | Passed | Repository lint and formatting; not static security certification. |
| Git diff whitespace | Passed | No whitespace errors in tracked diff. |
| Source distribution / wheel build | Passed | Local build completed. |
| Isolated wheel smoke | Passed | Site-packages import outside checkout, CLI help, packaged HTML/vendor assets and Git hook. |
| Docker image build | Passed | Final source installs in web-service image; image ID in service evidence. |
| Compose runtime | Passed | Dashboard, gateway, webhook and Ollama running; webhook/Ollama healthy; project-service UID 501:20 in this host verification (image default 10001); loopback ports. |
| Training environment pip check | Passed | No broken Python requirements. |
| Python dependency advisory assessment | Zero known matches in recorded installed-environment scan; separate normalized Torch scan also zero | Time-bound advisory lookup only. CPU local-version package required the separate Torch check. |

## Commands and inputs

Native suite:

```sh
cd /Users/mac/Dev/MoroAI/moro
/tmp/moro-remediation-20261003/venv/bin/python -m pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
git diff --check
```

Linux full suite:

```sh
docker exec -e PYTHONPATH=/workspace/src -e MORO_TRAINING_TESTS=1 \
  moro-audit-20261002-cpu-dev /opt/moro-candidate/bin/python -m pytest \
  /workspace/tests -q -o cache_dir=/tmp/candidate-pytest-cache
```

Installed-wheel real integration (no source PYTHONPATH):

```sh
docker exec -w /tmp -e PYTHONPATH= -e MORO_TRAINING_TESTS=1 \
  moro-audit-20261002-cpu-dev /opt/moro-candidate/bin/python -m pytest \
  /workspace/tests/integration/test_training_cpu.py -q \
  -o cache_dir=/tmp/candidate-pytest-cache
```

The final wheel was force-reinstalled with `--no-deps` into the already validated training environment; `pip check` passed. A separate import check resolved the backend to `/opt/moro-candidate/lib/python3.11/site-packages/moro/training/hf_backend.py`. The final native wheel smoke resolved dashboard imports under the isolated wheel virtualenv's site-packages.

Reference training pins: Torch 2.14.1 (installed CPU build `2.14.1+cpu`), Transformers 5.18.0, Datasets 5.0.1, PEFT 0.21.2, TRL 1.14.1, Accelerate 1.15.0. Optional bitsandbytes 0.50.2 is declared but CUDA execution was not tested. Build tooling requires setuptools >=83. Full scan input/results are retained rather than representing direct pins as a lock of every dependency.

## Important boundaries of the evidence

- The CPU fixture creates a tiny local GPT-2 model/tokenizer; it does not establish quality, speed or memory behavior for a production model.
- The SDK integration intentionally records a **0%** evaluation and permits release with a test-only minimum pass rate of zero and safety requirement disabled. This verifies real evidence persistence and gate wiring; it is not an acceptable production quality threshold.
- The OOM case raises a controlled exception on CPU. Weak-reference collection and successful retry are verified; CUDA memory return-to-baseline, MPS recovery, multi-GPU and hardware throughput are not.
- Successful gateway mapping is unit-tested with a mocked upstream. Live Ollama inventories are empty; actual missing-model failure and inventory behavior are verified. No production model was downloaded or successfully served.
- Authentication HTTP tests validate login, cookie attributes and authenticated HTML/API/asset responses. Browser automation rendered the login page but its submission did not reach the server. Authenticated browser interaction, all UI controls and visual regression checks remain unverified.
- Existing tests include mocked backend contracts. They are not counted as additional real model training runs.
- Advisory lookup reports known matches at scan time. It does not cover every OS package, vendored JavaScript package, optional CUDA dependency, future disclosure or malicious model artifact. The older audit CPU system environment remains unchanged; use `/opt/moro-candidate`.
- FastAPI lifecycle/dependency deprecation warnings remain. A passing suite does not mean every supported Python/platform combination was exercised locally; remote CI was not run here.
- No hard-kill crash/restart reconciliation, model merge/GGUF equivalence, remote deployment, signed attestation, TLS/RBAC deployment or restored backup was verified.

## Security acceptance cases retained in code

[Boundary tests](../../../tests/test_security_boundaries.py) cover both removed terminal paths, host/origin/WebSocket rejection, session expiry and mutation CSRF protection, upload traversal/symlink/overwrite/size rejection, SQL expression rejection, external schema retrieval denial, PEM redaction, shell-name rejection, stale/invalid config preservation, webhook idempotency, staged-blob hook scanning, truthful gateway errors and interprocess training locks.

[Export tests](../../../tests/test_export_eligibility.py) exercise gate/digest and promotion boundaries. [Flywheel tests](../../../tests/test_flywheel_orchestrator.py) exercise undersized/capped consumption, failed training, reused epochs and deployment enablement. [Dataset tests](../../../tests/test_dataset_versions.py) cover cache identity, immutable split checks and duplicate/document grouping. See the [ledger](STATUS.md) for acceptance criteria still unmet.
