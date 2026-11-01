# October 19 continuation: operation boundaries, truthful UI and live environments

**October 20 continuation:** [P0-2 report](../2026-10-20/REPORT.md), [current environment runbook](../2026-10-20/RUNBOOK.md), and [evidence](../2026-10-20/evidence/README.md). The dated results below are retained as historical evidence.

This pass implements and verifies the intent of the supplied P0-1 execution plan against the existing remediation branch. It preserves the earlier work and historical evidence. Changes remain local and uncommitted on `codex/audit-remediation`.

## What was completed

### Terminal removal and strict operations

Both legacy terminal routes are now absent from the application route table and OpenAPI. Authenticated requests return **404**; unauthenticated API requests still encounter the global authentication boundary and return **401**. The terminal widget, command submission code and false “Command executed” fallback were removed from the browser UI.

The new [operation router](../../../src/moro/dashboard/operations.py) exposes only six registered names:

| Operation | Actual behavior |
|---|---|
| `list_datasets` | Returns recorded/raw datasets with bounded pagination; maximum 500 returned entries. |
| `preview_dataset` | Resolves a real dataset, verifies immutable snapshots and returns at most 100 sample rows. |
| `compile_dataset` | Awaits the real compiler and returns the immutable version ID. |
| `start_training` | Awaits the real training service; returns its recorded outcome only after completion. |
| `get_job_status` | Looks up an existing training run; it does not invent a queued job. |
| `stop_job` | Unknown run: 404. Recorded run: 409 because verified process cancellation is not implemented. |

Schemas reject unknown fields, path-like IDs, incorrect scalar types and out-of-range limits. A `command`, unsupported `recipe_id` or unsupported `dry_run` cannot be silently ignored. Validation errors omit submitted input values. Unknown operation names return 404. Handlers call existing application functions, with no shell/interpreter dispatch.

The attached sketch was not copied literally: its `_service_*`, `start_real_training` and job-service imports did not exist, its schemas did not actually forbid extra fields, and its WebSocket query token would expose credentials in URLs. The current shared security middleware was retained: no `MORO_AUTH_DISABLED` bypass, no secret printing and no query-token authentication. Browser WebSockets use signed session cookies with host/origin checks. The proposed five-request timing ratio is not evidence of constant-time authentication; tests instead exercise acceptance/rejection and the implementation continues using `hmac.compare_digest`.

Evidence: [operation acceptance tests](../../../tests/test_operations.py), [existing boundary tests](../../../tests/test_security_boundaries.py), [live checks](evidence/services-smoke.json). Both `subprocess.run` and `subprocess.Popen` are replaced with fail-fast functions in the removed-route test. The four real offline CPU cases now include training through the HTTP operation endpoint, adapter reload, real evaluation and gate/package mechanics. These are tiny-model execution tests, not quality benchmarks or proof of GPU behavior.

### Feedback database and UI correctness

The continuation exposed an additional functional defect: CLI/webhook ingestion used `data/production_logs.db`, while the dashboard convenience orchestrator and flywheel monitor read `.moro/production.db`. The feedback API could report 12 generated pairs and return sample preferences when storage was empty. It could therefore appear successful without observing the ingested records.

The dashboard orchestrator, monitor, status and pair preview now read the same default `data/production_logs.db` as the webhook/CLI. Pair previews query recorded rows with a bounded SQL limit. Empty storage returns zero/empty lists. Extraction is awaited off the event loop and returns the real epoch/result, without made-up fallback IDs or counts. A new integration test ingests a correction through the receiver, observes it through the dashboard, extracts exactly one pair, checks the original source log ID, verifies the monitor count, and verifies that a second cycle skips it.

Source: [feedback API](../../../src/moro/dashboard/api/flywheel.py), [orchestrator](../../../src/moro/flywheel/orchestrator.py), [dashboard monitor](../../../src/moro/dashboard/mission_control.py). Legacy `.moro/production.db` files are **preserved, not automatically merged**. Existing deployments that intentionally used that old location need an explicit migration with duplicate/epoch reconciliation. Custom CLI/webhook `--db` paths also require matching deployment configuration; this correction establishes the shared default, not universal database discovery.

Browser inspection found additional hardcoded UI evidence that API tests alone had missed: registered model names, robustness/pass rates, training history/loss curves, VRAM, throughput, preference examples, hardware size and readiness claims. Those panels now display recorded API data, an explicit unmeasured/empty state, or an error. The overview no longer substitutes positive sample counts before its first response. A request failure clears the overview and displays an error instead of retaining a success-looking fallback. Unsupported CLI actions give instructions instead of pretending to execute.

Source: [dashboard template](../../../src/moro/dashboard/templates/mission_control.html). Real browser verification covered sign-in, dataset listing, compilation, immutable preview, empty registry/Ollama inventory, missing evaluation evidence and recorded synthetic feedback. The new operation panel uses text rendering for returned data; it does not inject response content as HTML. Broader UI/accessibility and all error-path testing remain open.

### Dependency remediation found during this continuation

The refreshed training-environment scan identified three advisory matches in `aiohttp 3.14.3`. The project now pins `aiohttp 3.14.4` in the training extra, and the running Linux reference environment was upgraded. Upstream identifies 3.14.4 as the patched release for an initial request/header timeout issue, resource exhaustion cases, and shared-cookie Secure handling. Sources: [request timeout advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-5wr8-gcqf-gqf3), [resource exhaustion advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-2g87-pp6c-29x5), [cookie advisory](https://github.com/aio-libs/aiohttp/security/advisories/GHSA-494j-54xm-rwp3).

These were dependency matches, not three demonstrated remote exploits against Moro. The original and final scanner outputs are both retained. Final normalized training requirements remove the `+cpu` suffix solely for Torch advisory lookup and exclude the local Moro distribution; the application itself is tested/reviewed as source. This is not a hash lock or proof of binary equivalence. The final training scan reports **91 external packages, zero known matches and zero skipped entries**. The separate web-image Python scan reports **32 external packages, zero known matches and zero skipped entries**. A final-image comparison found FastAPI had resolved from 0.147.0 to 0.149.0 during rebuild; the web scan was refreshed against the final image. The earlier scan is preserved, and this drift is direct evidence that full dependency locking remains unfinished. Neither scan covers OS packages, every browser asset, optional CUDA binaries, future disclosures or malicious model artifacts.

## Validation and running environments

- Native Python **3.14.6**, Intel macOS: **482 passed, 4 skipped**. The skipped cases require the Linux training stack.
- Linux Python **3.11**, final installed wheel: **486 passed**, including four real offline CPU lifecycle cases. The backend imports from site-packages with source `PYTHONPATH` unset.
- **91 live HTTP checks** across native, alternate, Compose, ASGI webhook and CLI webhook services. They include both removed routes, authentication/origin rejection, operation validation, real compile/preview, missing evidence, webhook replay conflicts, extraction and matching monitor totals.
- Final wheel/sdist and Docker image built; lint, formatting, JavaScript syntax and diff whitespace checks passed. Warnings remain in FastAPI/Starlette and the CPU trainer; they are retained in the raw logs.
- Native dashboard, alternate dashboard, gateway, ASGI receiver and CLI receiver are running. Compose dashboard/gateway/webhook/Ollama and the optional feedback extraction loop are running. The existing owned native-facing Ollama and Linux CPU container are also running. [Runbook and shutdown instructions](RUNBOOK.md).

The feedback container runs extraction only, not an autonomous DPO trainer. Its loop now exits on command failure instead of sleeping past a failure. The real CPU environment is `/opt/moro-candidate`; the older system Python inside that container remains historical and must not be used as the remediated training stack. Ollama's tested inventories were empty; successful production-model serving and GPU training were not established.

The [evidence index](evidence/README.md) records exact logs, reproducibility details, package scan scope, artifact hashes and browser captures. The [current module inventory](evidence/source-inventory.json) enumerates Python modules and top-level symbols; it does not assert exhaustive line-by-line review.

## Remaining work and acceptance criteria

The [previous 43-finding ledger](../2026-10-03/STATUS.md) remains the broader backlog. This pass tightens SEC-01/02/05, revisits SEC-12, and fixes additional EVAL-06/REL-04/FLY-02 presentation and integration defects. It does not close every finding.

1. **Durable execution:** process-owning workers, persistent attempts/leases, cross-project device admission, crash reconciliation and verified cancellation/resume. The legacy training monitor still reads `.moro/training.lock` rather than the execution lock; readiness remains explicitly unverified. Acceptance: restart and hard-kill tests show correct state and terminate only owned processes.
2. **Publication evidence:** resolved base/tokenizer/template/runtime identity, compatible paired baseline comparisons and post-conversion evaluation. Acceptance: altered or mismatched artifacts cannot pass any publishing route.
3. **Data trust and scale:** tokenizer-aware lengths, streaming compilation, calibrated rare-fact/PII benchmarks, semantic leakage checks and reviewed preference provenance. Acceptance: independently labeled held-out measurements and bounded peak memory.
4. **Production security:** roles/scoped credentials, TLS configuration, restrictive CSP, request/storage quotas, retention, backup restoration, complete dependency locks and signed attestations. Acceptance: permission-matrix, abuse, recovery and signature-validation tests against an actual deployment.
5. **Serving:** actual backend ownership, readiness, successful inference, rollback and release-specific quality probes. Acceptance: a real deployed model produces measured outputs and rollback restores the prior verified release.

No commit, push, pull request, production deployment or external publication was performed.
