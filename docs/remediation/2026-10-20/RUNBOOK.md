# P0-2 environment runbook — October 20, 2026

The synthetic development project remains at `/Users/mac/Dev/MoroAI/moro/.moro/dev/2026-10-19/project`. P0-2 logs and distributions are under its sibling `p0-2/` directory; the October 19 path is retained because this pass began there. The private installation token remains `project/.moro/web.token` (0600). Do not copy it into evidence or command-line arguments.

## Running services

| Runtime | Address / identity |
|---|---|
| Native dashboard | http://127.0.0.1:8501/ |
| Alternate dashboard | http://127.0.0.1:8765/ |
| Native gateway | http://127.0.0.1:8000 |
| Native ASGI webhook | http://127.0.0.1:8001/health |
| Native CLI HTTP receiver | http://127.0.0.1:8002/health |
| Compose dashboard | http://127.0.0.1:18501/ |
| Compose gateway | http://127.0.0.1:18000 |
| Compose webhook | http://127.0.0.1:18001/health |
| Native-facing / Compose Ollama | http://127.0.0.1:11434 / http://127.0.0.1:11435 |
| Feedback extraction loop | `moro-remediation-flywheel-1` |
| Linux CPU reference environment | `moro-audit-20261002-cpu-dev`, `/opt/moro-candidate/bin/python` |

All host-published service ports are loopback-only. Project Compose services run as host UID/GID 501:20; Ollama retains its upstream user. Ollama inventories were empty. The feedback loop extracts corrections; it does not run autonomous DPO training. GPU execution and production-model inference are not established.

## Start/restart

Native commands are unchanged from the [October 19 runbook](../2026-10-19/RUNBOOK.md#reproduce-native-startup). The two native dashboards were restarted for the updated Python handlers; templates are read on request. Native core/evaluation Python is the repository `.venv` (3.14.6). Linux training uses the installed wheel in `/opt/moro-candidate` (3.11), with source `PYTHONPATH` unset.

```sh
cd /Users/mac/Dev/MoroAI/moro
docker build -t moro-remediation:20261019-p02 .
MORO_PROJECT_DIR=/Users/mac/Dev/MoroAI/moro/.moro/dev/2026-10-19/project \
MORO_UID=$(id -u) MORO_GID=$(id -g) \
docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-20/evidence/compose.yml \
  --profile feedback up -d --no-build
```

The image tag retains the pass's start date. The exact final image ID is in the archived live-service results. An image tag alone is not a dependency lock.

## Reproduce verification

```sh
.venv/bin/python -m pytest tests/security/test_upload_containment.py tests/security/test_sql_identifiers.py -q
.venv/bin/python -m pytest -q
docker exec -w /tmp -e PYTHONPATH= -e MORO_TRAINING_TESTS=1 \
  moro-audit-20261002-cpu-dev /opt/moro-candidate/bin/python -m pytest \
  /workspace/tests -q -o cache_dir=/tmp/pytest-p02
.venv/bin/python docs/remediation/2026-10-20/evidence/verify_p02.py.txt
.venv/bin/python docs/remediation/2026-10-20/evidence/verify_services.py.txt
```

The live P0-2 script targets only the named synthetic project, creates temporary raw uploads, compiles immutable versions and removes its successful raw uploads through the API. It asserts that preexisting raw files remain unchanged. Compiled synthetic versions remain for provenance. If interrupted, use returned dataset IDs to inspect any leftover synthetic uploads before deleting them. The broader script adds three synthetic feedback records per successful run and extracts eligible corrections. Both scripts write fresh results under `.moro/dev/2026-10-19/p0-2/`; archived evidence is preserved.

The browser upload form now displays 10 MiB per file. Entire requests are bounded at 16 MiB, including multipart overhead. `display_name` is sanitized metadata; the older `name` field still rejects path-like values. Invalid SQL identifiers now return 400. Partial batch compilation failures identify saved files rather than implying a rollback.

## Scoped shutdown

Native: Ctrl-C in each owning terminal, or inspect `lsof -nP -iTCP:8501 -iTCP:8765 -iTCP:8000 -iTCP:8001 -iTCP:8002 -sTCP:LISTEN`, verify the PID's command, and SIGTERM only the intended Moro process.

```sh
docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-20/evidence/compose.yml --profile feedback down
docker stop moro-audit-20261002-cpu-dev moro-audit-20261002-ollama
```

Do not add `--volumes` unless intentionally deleting retained Ollama data. Leave unrelated Docker/Supabase projects untouched. The old container system Python remains historical; it is not the patched reference environment.
