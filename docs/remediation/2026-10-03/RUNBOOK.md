# Development environments and shutdown — October 5, 2026

These are local development services using synthetic data. The scratch project is `/tmp/moro-remediation-20261003/project`; it is separate from the repository's project data. Temporary directories may disappear after reboot or cleanup. No remote deployment or model download was performed.

## Active services

| Environment | Endpoint | Purpose |
|---|---|---|
| Native dashboard | http://127.0.0.1:8501/login | Current editable source, single-project administrator UI |
| Alternate native dashboard | http://127.0.0.1:8765/login | Same UI/project on alternate port |
| Native gateway | http://127.0.0.1:8000 | Authenticated Ollama proxy |
| Native webhook | http://127.0.0.1:8001/health | Feedback receiver; ingestion requires key and idempotency header |
| Existing audit Ollama | http://127.0.0.1:11434 | Running, no installed models |
| Compose dashboard | http://127.0.0.1:18501/login | Built image, same scratch project |
| Compose gateway | http://127.0.0.1:18000 | Built image, Compose Ollama |
| Compose webhook | http://127.0.0.1:18001/health | Built image feedback receiver |
| Compose Ollama | http://127.0.0.1:11435 | Running, no installed models |

The token is in `/tmp/moro-remediation-20261003/project/.moro/web.token`, mode 0600. It was rotated after browser verification; the temporary verification credential is invalid. Enter that file's current content in the login form. API calls use `Authorization: Bearer <token>`; webhook ingestion uses `X-API-Key: <token>` plus a stable `Idempotency-Key` of 16–128 ASCII characters. Do not paste tokens into committed examples or evidence.

Default configuration uses one shared project administrator token. Rotation invalidates sessions; restart webhook workers after rotation because their configuration caches the key. Project services share the synthetic scratch filesystem; this is not tenant isolation. Feedback smoke checks insert synthetic records in `data/production_logs.db` and repeat identical submissions to verify replay protection.

## Native start and stop

The current native services were started from the scratch project using:

```sh
cd /tmp/moro-remediation-20261003/project
/tmp/moro-remediation-20261003/venv/bin/python -m uvicorn moro.dashboard.mission_control:mission_app --host 127.0.0.1 --port 8501
# Separate terminal, same cwd; use port 8765 for the alternate dashboard.
/tmp/moro-remediation-20261003/venv/bin/python -m uvicorn moro.dashboard.gateway:gateway_app --host 127.0.0.1 --port 8000
/tmp/moro-remediation-20261003/venv/bin/python -m uvicorn moro.flywheel.webhook.receiver:webhook_app --host 127.0.0.1 --port 8001
```

Logs are `/tmp/moro-remediation-20261003/{dashboard,alternate-ui,gateway,webhook}.log`. Startup log headers contain current PIDs. Use Ctrl-C in the owning terminal, or inspect `lsof -nP -iTCP:8501 -iTCP:8765 -iTCP:8000 -iTCP:8001 -sTCP:LISTEN`, verify each process command with `ps -p PID -o command=`, then send SIGTERM only to the matching Moro uvicorn process. Do not use blanket Python/process kills.

## Compose start and stop

The verified image tag is `moro-remediation:20261004` (rebuilt with final code October 5; exact image ID is in `evidence/services-smoke.json`). The saved override avoids conflicting with native service ports. Compose 2.40.3 was used; the override uses `!override` for ports.

```sh
cd /Users/mac/Dev/MoroAI/moro
docker build -t moro-remediation:20261004 .
MORO_PROJECT_DIR=/tmp/moro-remediation-20261003/project \
MORO_UID=$(id -u) MORO_GID=$(id -g) \
docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-03/evidence/compose-verify.yml up -d --no-build

docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-03/evidence/compose-verify.yml ps
```

The explicit UID/GID allows writes to this host-owned scratch directory; the image defaults to UID 10001. Dashboard/gateway/webhook run without root and publish only loopback ports. Ollama uses its upstream image; it is not covered by the project-service nonroot claim, and its image tag remains `latest`.

To stop this Compose stack without deleting its volumes:

```sh
cd /Users/mac/Dev/MoroAI/moro
docker compose -p moro-remediation -f docker-compose.yml \
  -f docs/remediation/2026-10-03/evidence/compose-verify.yml down
```

Do not add `--volumes` unless intentionally deleting model data. Do not stop unrelated Docker/Supabase projects. The older owned audit Ollama container is separate: `docker stop moro-audit-20261002-ollama` stops port 11434.

## Verified Linux training environment

Container: `moro-audit-20261002-cpu-dev`, source mounted read-only at `/workspace`. Use **`/opt/moro-candidate/bin/python`**. The container's original system Python retains the older audit dependency stack and is not the remediated runtime.

```sh
docker exec -e PYTHONPATH=/workspace/src -e MORO_TRAINING_TESTS=1 \
  moro-audit-20261002-cpu-dev /opt/moro-candidate/bin/python -m pytest \
  /workspace/tests -q -o cache_dir=/tmp/candidate-pytest-cache
```

The final wheel is installed in this environment; unset `PYTHONPATH` to exercise that installed copy. Native core venv: `/tmp/moro-remediation-20261003/venv`. Isolated wheel venv: `/tmp/moro-remediation-20261003/wheel-venv`. Final distributions: `/tmp/moro-remediation-20261003/final-dist/`. These scratch environments are development evidence, not immutable deployment artifacts.

To stop the idle owned CPU container: `docker stop moro-audit-20261002-cpu-dev`. No GPU/MPS training environment was started. The optional Compose `feedback` profile was not enabled: extraction is not an implemented autonomous training/deployment controller. Enabling a polling loop would not prove that missing feature works.

## Expected behavior and compatibility changes

- Anonymous dashboard visits go to login; API requests require credentials.
- Both browser terminals return 410. Run trusted CLI commands locally.
- Config mutations require a current ETag via If-Match; old clients must refresh before writing.
- Chunked mutations without Content-Length are rejected by dashboard/gateway middleware.
- Webhook requests require authentication and stable idempotency keys; contradictory reuse returns 409.
- Missing data/models/evaluation and unsupported deployment fail. Empty inventories are normal here.
- Stop/cancel and exact resume are not implemented; do not treat cancellation of an HTTP request or async awaiter as backend termination.
- Compiled dataset versions are immutable; preview verifies hashes; deleting them through the raw dataset API returns 409.
- Default privacy policy flags rather than removes detected content. Default preference extraction uses human corrections, not synthetic rating rules.

Use the [validation record](VALIDATION.md) for verified behavior and the [ledger](STATUS.md) for the remaining implementation work.
