# Development environments: audit runbook

Snapshot: 2026-10-02, after the checks in `evidence/environment-final.json`. Services are live at delivery, not installed as persistent login services. A machine/app restart can stop them. All app commands run in **`/tmp/moro-audit-20261002/dev`**, a synthetic project; the repository's real model/data state was not used. The application source was left unchanged.

## Running services

| Service | Address | Process / container | Verified behavior |
|---|---|---|---|
| Mission Control | [Open dashboard](http://127.0.0.1:8501) | PID 17653 | HTTP 200; 102,831-byte HTML; API probes completed |
| Alternate UI command | [Open UI](http://127.0.0.1:8765) | PID 18077 | Same FastAPI application, HTTP 200 |
| Gateway | [Health](http://127.0.0.1:8000/health) | PID 17668, child of dashboard | HTTP 200; unavailable-model fallback is fabricated, not valid inference |
| Webhook | [Health](http://127.0.0.1:8001/health) | PID 17717 | HTTP 200; accepted synthetic feedback into audit project |
| Ollama | [Model list](http://127.0.0.1:11434/api/tags) | `moro-audit-20261002-ollama` | HTTP 200, empty model list; loopback-only published port |
| Flywheel extraction loop | `/tmp/moro-audit-20261002/flywheel-daemon.log` | PID 18827 | Runs extraction once/hour against synthetic project; no real DPO trainer |
| Linux CPU training environment | `docker exec -it moro-audit-20261002-cpu-dev sh` | `moro-audit-20261002-cpu-dev` | Reusable running container; 2 CPU / 6 GiB cap; source mounted read-only; all 18 integration tests passed |

The dashboard/webhook retain the security defects described in the report. Keep this audit environment limited to synthetic data and loopback. There is no demonstrated pretrained inference service: no pretrained weights were downloaded, and the gateway's health response does not prove inference readiness.

## Restart the local services

Use separate terminal sessions. Check the table's ports first to avoid duplicate listeners. In each terminal, use the synthetic project as the working directory.

Dashboard and gateway:

```sh
cd /tmp/moro-audit-20261002/dev
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m moro.main dashboard --host 127.0.0.1 --port 8501 --gateway
```

Alternate UI entry point (optional duplicate application, retained to verify both supported entry points):

```sh
cd /tmp/moro-audit-20261002/dev
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m moro.main ui --host 127.0.0.1 --port 8765
```

Webhook using the implementation that actually exists:

```sh
cd /tmp/moro-audit-20261002/dev
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -c 'from moro.flywheel.webhook.receiver import start_webhook_receiver; start_webhook_receiver(host="127.0.0.1", port=8001)'
```

Ollama and Linux CPU environment, if stopped:

```sh
docker start moro-audit-20261002-ollama
docker start moro-audit-20261002-cpu-dev
```

One extraction cycle:

```sh
cd /tmp/moro-audit-20261002/dev
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m moro.main flywheel run --json
```

To reproduce the running hourly development loop:

```sh
cd /tmp/moro-audit-20261002/dev
while true; do
  /Users/mac/Dev/MoroAI/moro/.venv/bin/python -m moro.main flywheel run --json
  sleep 3600
done
```

This is a foreground development process, not a Codex scheduled automation. Extraction does not establish automatic alignment training or deployment.

## Stop only the audit services

PIDs can be reused. First inspect the command identity and listeners:

```sh
ps -p 17653,17668,17717,18077,18827 -o pid,ppid,command
lsof -nP -iTCP:8501 -iTCP:8765 -iTCP:8000 -iTCP:8001 -iTCP:11434 -sTCP:LISTEN
```

After confirming they are still the processes listed above, stop the dashboard (which owns the gateway), alternate UI, webhook, and extraction loop:

```sh
kill -TERM 17653 18077 17717 18827
docker stop moro-audit-20261002-ollama moro-audit-20261002-cpu-dev
```

If the gateway remains listening after the parent exits, verify PID 17668 still names `moro.dashboard.gateway:gateway_app`, then terminate that PID. Do not use `killall python`, global Docker stop commands, or delete unrelated containers. Stopping the loop may leave its sleeping child until that sleep expires; it cannot start another cycle once the parent is gone.

The initial installation/test container `moro-audit-20261002-cpu` is already exited and retained as evidence. The reusable local image is `moro-audit-20261002-cpu:verified`; the tag means verified for this narrow CPU test, not security-certified. Container state and image IDs are recorded in the environment snapshot. No Docker cleanup or unrelated service changes were performed.

## Reproduce verification

Core suite and lint in the original native environment:

```sh
cd /Users/mac/Dev/MoroAI/moro
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pip check
```

Separate Python 3.12 coverage environment: `/tmp/moro-audit-20261002/tooling`. Its dependencies were installed separately; the project's original `.venv` was not upgraded.

```sh
cd /Users/mac/Dev/MoroAI/moro
/tmp/moro-audit-20261002/tooling/bin/python -m coverage run --data-file=/tmp/moro-audit-20261002/coverage-repeat.data --source=moro -m pytest -q
/tmp/moro-audit-20261002/tooling/bin/python -m coverage report --data-file=/tmp/moro-audit-20261002/coverage-repeat.data
```

Real Linux CPU integration, with offline-model settings and training tests already set in the container environment:

```sh
docker exec moro-audit-20261002-cpu-dev python -m pytest /workspace/tests/integration -v -o cache_dir=/tmp/pytest-cache
docker exec moro-audit-20261002-cpu-dev python -m pip check
```

The real training test creates a tiny random local GPT-2 model, performs one LoRA step, checks train/validation loss, checkpoint and safetensors existence, reloads the adapter, and generates text. A socket-denial monkeypatch is active during training/evaluation. This establishes trainer execution and serialization on the tested CPU stack, not useful pretrained quality or GPU correctness.

Build the distribution:

```sh
cd /Users/mac/Dev/MoroAI/moro
/tmp/moro-audit-20261002/tooling/bin/python -m build --outdir /tmp/moro-audit-20261002/dist
```

The wheel/sdist build succeeds, but HTML and hook runtime assets are missing. Editable installs mask that distribution defect.

## What could not be made healthy without source fixes or different hardware

- **Repository Docker Compose stack:** actual Docker build fails at editable installation because `src` has not been copied yet. The webhook's configured ASGI object does not exist. Service URLs/config mounts have additional defects. Alternate audit containers enabled CPU/Ollama testing; they do not prove the repository stack starts correctly.
- **Native Intel macOS training:** the pinned Torch 2.8.0 distribution has no matching Intel-macOS wheel. Core CLI/dev works on the host. Training was verified in Linux CPU Docker instead.
- **CUDA/NF4/bitsandbytes/OOM recovery:** no supported CUDA GPU on this host. No accelerator memory or recovery claim was experimentally verified.
- **Apple Silicon/MPS/MLX/ROCm/multi-GPU:** this host is Intel; these configurations were not executed. MLX and a distributed training backend are not implemented in the reviewed backend.
- **Actual Ollama adapter deployment or vLLM serving:** no compatible pretrained base/adapter imported; vLLM CLI deployment is unsupported. The metadata-only deployment endpoints are not serving environments.
- **Real automatic DPO:** extraction exists but a concrete DPO bridge is not wired into normal CLI cycles.
- **Browser UX/offline assets:** HTTP delivery and API behavior were checked. Full browser rendering, keyboard accessibility and blocked-network UI behavior remain acceptance work.

The first Linux run was 17 passed / 1 failed because `git` was missing from the minimal audit container. Installing `git` corrected the environment; the final run was **18 passed, 3 warnings in 11.57 seconds**. Both logs are preserved.

## Files and reproducibility limits

Persistent report/evidence live in `docs/audits/2026-10-02/`. Disposable project state, probe scratch directories, dependency environments, test artifacts, original logs and built distributions live under `/tmp/moro-audit-20261002` or the CPU containers. Temporary directories are not durable backups.

Evidence `.txt` files preserve command output; the `.log` suffix was changed because the repository ignores `*.log`. Probe scripts are stored as `.py.txt` to identify them as audit evidence, not application modules. They target the synthetic audit project and should not be redirected to real/private projects. The committed-source inventory hashes allow comparison with later revisions. This audit made no security fixes and provides no production readiness certification.
