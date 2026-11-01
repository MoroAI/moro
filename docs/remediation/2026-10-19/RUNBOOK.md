# Running development environments — October 19, 2026

**October 20 continuation:** [P0-2 report](../2026-10-20/REPORT.md), [current environment runbook](../2026-10-20/RUNBOOK.md), and [evidence](../2026-10-20/evidence/README.md). The dated results below are retained as historical evidence.

The old `/tmp` environments had disappeared. Current synthetic project and logs are persistent under the ignored repository directory:

`/Users/mac/Dev/MoroAI/moro/.moro/dev/2026-10-19/`

Project: `project/`. Token: `project/.moro/web.token` (0600). Use the token file's current contents for browser sign-in, bearer API requests, or the webhook's `X-API-Key`. No token is included in these documents. Signed browser sessions expire after eight hours. Webhook workers cache the key and must be restarted after rotation.

| Service | URL / runtime | State verified |
|---|---|---|
| Native dashboard | http://127.0.0.1:8501/ | Authenticated browser operations work |
| Alternate dashboard | http://127.0.0.1:8765/ | HTTP authentication/operations work |
| Native gateway | http://127.0.0.1:8000 | Actual empty model inventory; missing-model failure |
| Native ASGI webhook | http://127.0.0.1:8001/health | Authentication, replay protection and persistence |
| CLI HTTP webhook | http://127.0.0.1:8002/health | Same ingestion checks through stdlib HTTP receiver |
| Native-facing Ollama | http://127.0.0.1:11434 | Existing owned audit container, empty inventory |
| Compose dashboard | http://127.0.0.1:18501/ | Rebuilt current application image |
| Compose gateway | http://127.0.0.1:18000 | Compose Ollama proxy |
| Compose webhook | http://127.0.0.1:18001/health | Same scratch feedback database |
| Compose Ollama | http://127.0.0.1:11435 | Healthy, empty inventory |
| Compose feedback loop | `moro-remediation-flywheel-1` | Runs correction extraction hourly; no autonomous training |
| Linux CPU environment | `moro-audit-20261002-cpu-dev` | `/opt/moro-candidate/bin/python`, real offline CPU tests |

All published ports are loopback-only. Compose project services use this host's UID/GID 501:20; image default is UID 10001. Ollama retains its upstream image user. Unrelated Docker/Supabase projects were not intentionally changed; Docker Desktop startup may restart their existing restart-policy services.

## Reproduce native startup

Use separate terminals, all with the project directory as cwd:

```sh
cd /Users/mac/Dev/MoroAI/moro/.moro/dev/2026-10-19/project
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m uvicorn moro.dashboard.mission_control:mission_app --host 127.0.0.1 --port 8501
# Same command with port 8765 starts the alternate dashboard.
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m uvicorn moro.dashboard.gateway:gateway_app --host 127.0.0.1 --port 8000
/Users/mac/Dev/MoroAI/moro/.venv/bin/python -m uvicorn moro.flywheel.webhook.receiver:webhook_app --host 127.0.0.1 --port 8001
/Users/mac/Dev/MoroAI/moro/.venv/bin/moro flywheel serve --host 127.0.0.1 --port 8002
```

The repository `.venv` is an editable Python 3.14.6 core/evaluation environment. Do not infer GPU training support from its ability to serve the dashboard.

## Reproduce Compose startup

```sh
cd /Users/mac/Dev/MoroAI/moro
docker build -t moro-remediation:20261019 .
MORO_PROJECT_DIR=/Users/mac/Dev/MoroAI/moro/.moro/dev/2026-10-19/project \
MORO_UID=$(id -u) MORO_GID=$(id -g) \
docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-19/evidence/compose.yml \
  --profile feedback up -d --no-build
```

The override uses Compose `!override` to avoid native-port conflicts and sets the built image for every project service. The exact verified image digest is recorded in `evidence/services-smoke.json`. Ollama remains `latest`; image digest pinning and OS package scanning remain open.

## Tests and installed wheel

```sh
cd /Users/mac/Dev/MoroAI/moro
.venv/bin/python -m pytest -q
# Run the installed wheel rather than the source-mounted version:
docker exec -w /tmp -e PYTHONPATH= -e MORO_TRAINING_TESTS=1 \
  moro-audit-20261002-cpu-dev /opt/moro-candidate/bin/python -m pytest \
  /workspace/tests -q -o cache_dir=/tmp/pytest-oct19
```

Final distributions are in `.moro/dev/2026-10-19/dist/`. The Linux wheel was force-reinstalled with dependencies supplied by the existing reference environment, including the patched aiohttp 3.14.4. `pip check` verifies consistency. The container's system Python is the older audit environment; use only `/opt/moro-candidate/bin/python` for current training checks.

## Safe shutdown

- Native: Ctrl-C in each owning terminal. If detached, inspect `lsof -nP -iTCP:8501 -iTCP:8765 -iTCP:8000 -iTCP:8001 -iTCP:8002 -sTCP:LISTEN`, verify each PID's command with `ps -p PID -o command=`, then SIGTERM only the matching Moro process. Do not use broad Python/process kills.
- Compose: from the repository, use `docker compose -p moro-remediation -f docker-compose.yml -f docs/remediation/2026-10-19/evidence/compose.yml --profile feedback down`. Omit `--volumes` to retain Ollama data.
- Separate owned containers: `docker stop moro-audit-20261002-cpu-dev moro-audit-20261002-ollama`.
- Leave unrelated Docker projects and volumes untouched.

## Data and compatibility notes

The project contains only synthetic verification records. Smoke checks add synthetic feedback and compile sample conversations. The shared feedback database is `data/production_logs.db`; old `.moro/production.db` files are retained but require explicit migration if they contain desired records. Source fingerprints are location-dependent, so host and container compilation can create separate immutable versions of the same mounted source. This is expected and must not be mistaken for identical portable build identity.

Both terminal routes now return authenticated 404 rather than 410. All general API calls still require authentication, including requests to removed routes. The operation API rejects unsupported fields instead of ignoring them. Starting training awaits actual execution; closing the page or cancelling an HTTP await does not prove that the backend stopped. `stop_job` explicitly returns 409 until process cancellation is implemented.
