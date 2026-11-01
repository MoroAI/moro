# P0-2 completed: upload containment and SQL identifiers

Continuation of the October 19 remediation, completed October 20, 2026. Branch: `codex/audit-remediation`; changes remain local and uncommitted. This report closes the scoped SEC-03/SEC-04 acceptance checks below, not the entire project backlog.

## Findings and changes

### Upload storage

The earlier implementation already generated random filenames, enforced a 10 MiB limit, validated full JSON/JSONL files and used hard-link publication to refuse overwrites. The remaining gaps were directory check/open races, unhandled storage collisions, absent CSV structure validation, blocking upload processing on the async route, and loss of display metadata/digests after the request.

[Upload store](../../../src/moro/dashboard/uploads.py):

- Opens `data` and `raw` relative to retained parent directory descriptors with `O_DIRECTORY | O_NOFOLLOW`. Creation is also relative to the opened parent. A deterministic parent-swap test proves that replacing the pathname with an external symlink does not redirect the write into that target.
- Keeps full UUID filenames, exclusive staging creation and atomic hard-link publication. Existing payloads, symlinks, sidecars and staging objects are preserved on collision. Collisions now return 409 rather than an unhandled server error.
- Reads at most 64 KiB per upload-copy step, caps stored content at 10 MiB, hashes actual uploaded bytes, and validates the complete content before publication. Validation is bounded by file size, but JSON parsing is not constant-memory streaming.
- Requires UTF-8 text without raw binary control bytes; JSON must be an object or nonempty array of objects; each nonblank JSONL record must be an object. Rejects explicit nonstandard JSON constants such as NaN. Excessive parser recursion returns 400 and cleans staging.
- Validates comma-delimited CSV with a strict parser, at least two unique nonempty header names, consistent row widths and at least one data row. Quoted commas and multiline fields work. Semicolon/tab dialects are not auto-detected because the current compiler also uses comma CSV.
- Stores private 0600 payload and hidden metadata files. Metadata records SHA-256, byte count, record count, timestamp, format and display name. Newly created data directories use mode 0700; existing directory permissions are not silently rewritten.
- Sanitizes the new `display_name` form field as metadata only, including control/format characters, path separators and a 120-character limit. Legacy `name` and original filename validation remain conservative: traversal-like values are rejected. Neither field selects the filesystem destination.
- Writes metadata before exposing the payload and removes owned temporary objects on ordinary failures. Metadata is not a dataset and cannot be previewed, compiled or deleted through dataset resolution. Reads reject symlink/nonregular/oversized metadata. Dataset deletion removes its sidecar as well.

The SHA-256 is the upload-time digest, not a signature or a promise that raw files are immutable. Compilation retains its independent snapshot integrity checks. Local filesystem administrators and the selected project root remain trusted.

### Dataset API behavior

[Dataset routes](../../../src/moro/dashboard/api/datasets.py):

- Upload copying and validation run through `asyncio.to_thread`, avoiding a synchronous copy/parser on the ASGI event loop. Framework multipart parsing still precedes the handler; the existing middleware separately caps the complete request at 16 MiB.
- Upload responses include `sha256`; listings preserve the display name, logical record count and `upload_sha256`. Legacy hand-placed files and older uploads without metadata remain usable.
- JSON preview now returns actual records; CSV counts exclude the header and count quoted multiline records correctly. JSONL preview limits count returned nonblank records rather than physical line numbers. The existing 1–100 preview bound remains.
- Dangling symlinks are filtered before listing sort/stat operations, preventing them from breaking the entire listing.
- Batch uploads report each file's outcome and successful count. If compilation fails after storage succeeds, the response identifies the saved dataset with `saved_compile_failed` and a 422 detail. A failed later file no longer hides previously saved files behind one undifferentiated request failure. Batches are intentionally not all-or-nothing transactions.
- Real compilation and immutable version handling are preserved. Live probes compile newly uploaded JSON through the actual compiler and verify the returned version ID.

### Browser initialization defect found during acceptance

[Dashboard template](../../../src/moro/dashboard/templates/mission_control.html): the widget advertised 500 MiB despite the server's 10 MiB limit. More significantly, Dropzone auto-discovery attached a default widget before the application initialized its configured instance. Browser console evidence showed `Dropzone already attached`; the configured size limit, auto-compile field and response handlers were therefore skipped, and a rejected upload rendered `[object Object]`.

Auto-discovery is now disabled immediately after the vendor script loads, before DOM-ready processing. The application creates the widget when the dataset tab opens. The UI uses the 10 MiB limit, displays server rejection/compilation-failure messages through text rendering, and refreshes the registry when a failed compilation nevertheless saved the source. The description states what validation actually checks and does not claim factual/privacy assurance. A real browser upload of malformed JSONL visibly displayed the server error; [screenshot](evidence/browser-upload-rejection.png).

### SQL identifier boundary

The earlier allowlist already blocked the original injection. This pass consolidates the contract into [immutable literal mappings](../../../src/moro/analytics/columns.py), covering ten numeric hyperparameters and eight experiment metrics that exist in the actual schema. Unsupported names, expressions, comments, case variants and control-character variants raise `AnalyticsColumnError` without echoing the submitted expression.

The [heatmap](../../../src/moro/analytics/visualizations.py) and [correlation query](../../../src/moro/analytics/tracker.py) interpolate only the resolved literal column values. [Compatibility exports](../../../src/moro/analytics/schema.py) delegate to the same mappings. The [HTTP handler](../../../src/moro/dashboard/mission_control.py) validates before initializing the analytics database and returns 400 for unsupported identifiers. This intentionally changes the previous invalid-column HTTP response from 422 to 400.

Tests replace database access with a fail-fast trap for each rejected input. Separate tests create a marker table, exercise valid queries without exposing it, verify every allowed column against SQLite's actual schema, and preserve correct experiment/target pairing when hyperparameters are missing. The pairing correction already existed and was retained.

## Differences from the supplied implementation sketch

The attachment was treated as a design proposal and checked against the repository:

1. Its async chunk generator was passed into a synchronous iterator consumer; the actual implementation uses the already-spooled upload file in a worker thread.
2. `exists()` followed by `os.replace()` does not guarantee no overwrite if another object appears between those operations. The existing exclusive hard-link publication is retained and tested with a collision planted at publication time.
3. A 1 MiB content sniff can miss invalid tails, misclassify a one-record JSONL file, or reject a valid JSON document longer than the prefix. The implementation validates the entire bounded file and accepts a single JSONL record.
4. Payload-first manifest creation can leave an exposed payload without metadata on manifest failure. This implementation publishes the payload last and rolls back owned files on ordinary exceptions. Crash/power-loss reconciliation is still a separate requirement.
5. Returning 501 for compile would remove already-working functionality. Real compilation remains enabled and tested. Existing IDs/raw sources remain compatible rather than hiding all legacy datasets.
6. A grep asserting zero SQL f-strings is not a security acceptance test: the sketch itself uses a SQL f-string. The relevant requirement is that untrusted names cannot become SQL expressions. Fixed structural conditions, generated `?` placeholders and resolved literal columns remain legitimate interpolation sites; query values are bound parameters.
7. The shared authentication/session middleware remains in place; the sketch's nonexistent `dashboard.auth` dependency is not introduced.

## Acceptance evidence

| Requirement | Evidence and outcome |
|---|---|
| Traversal and symlink resistance | [Upload acceptance tests](../../../tests/security/test_upload_containment.py): both parent components, deterministic parent swap, existing final symlink and dangling listing entry. Outside targets preserved. |
| No overwrite or leftover partials | Exact payload/metadata/staging collision tests, collision inserted at link time, interrupted reads, metadata-write failure, size overflow and malformed content. |
| Private and traceable uploads | Payload/sidecar mode tests; exact SHA-256/size; display metadata survives listing; sidecar resolution rejected; deletion removes owned pair. |
| Full-file content validation | Malformed JSON/binary tails beyond 1 MiB; scalar JSONL, mixed JSON arrays, CSV width/quote/header failures, invalid UTF-8 and parser recursion. |
| SQL inputs rejected before queries | [SQL acceptance tests](../../../tests/security/test_sql_identifiers.py): every public identifier position plus correlation; HTTP validation before DB construction; valid schema/query checks. |
| Requested focused suite | **73 passed** in the two requested test files. |
| Full native suite | **555 passed, 4 skipped**; native Python 3.14.6. Skips are Linux training-stack cases. |
| Installed Linux wheel suite | **559 passed**, including four offline real CPU training/reload/evaluation/release-mechanics cases. No GPU/model-quality conclusion follows from those tiny-model tests. |
| Live P0-2 behavior | **63 checks** across native, alternate and Compose dashboards; actual upload/list/preview/compile/delete, batch outcomes, file modes/digests, malformed input, size limits and SQL rejection. Preexisting raw files preserved. |
| Broader runtime regression | **91 checks** for authentication, typed operations, gateways, webhooks, replay handling and feedback extraction; seven owned containers running. |
| Final packaging | Wheel/sdist and web image rebuilt; installed module/template hashes checked against source. Ruff, JavaScript syntax and diff whitespace checks pass. |

Logs, scripts, exact image identity, dependency scan scope and source/distribution hashes are indexed in [evidence](evidence/README.md). Five native services and seven owned containers remain running; see the [current runbook](RUNBOOK.md).

## Remaining work and acceptance criteria

- **Crash durability and storage quotas:** power-loss tests, directory fsync policy, orphan staging/sidecar reconciliation, total storage quotas and per-actor/concurrency budgets. Acceptance: interrupted publication is recoverable and repeated authenticated uploads cannot exhaust the project's allocated disk/memory budget.
- **Large/legacy datasets:** bounded-memory record parsing, tokenizer-aware limits and consistent paging/counting for CLI-created files outside the upload cap. Acceptance: measured peak RSS and request latency remain bounded on the supported large-input corpus.
- **Data trust:** syntactic format acceptance does not validate conversation meaning, PII removal, malware-free contents or training suitability. Acceptance: independently labeled privacy/quality benchmarks and explicit review policy.
- **Analytics semantics:** duplicate heatmap cells currently overwrite rather than applying a documented aggregation; sparse loss-curve alignment and statistical confidence require a separate accuracy pass. Acceptance: deterministic aggregation and reviewed fixtures for missing/duplicate observations.
- **Environment reproducibility:** web dependencies can resolve differently between rebuilds. Final-image scans/hashes are retained, but full dependency/image locks, OS/browser scans and signatures remain unfinished.
- **Broader execution/production work:** durable workers/cancellation, actual GPU recovery, complete publication identity/comparative evidence, serving rollback, roles/TLS/CSP and recovery drills remain in the [broader ledger](../2026-10-19/STATUS.md).

The verified filesystem behavior is for macOS/Linux POSIX primitives, not a Windows certification or a boundary against a hostile local administrator. No commit, push, PR, production deployment or external publication was performed.
