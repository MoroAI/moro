# Evidence index

Audit date: 2026-10-02. Evidence was generated against source revision `bac72593964c5e7218b009824f7146998b6cdfaa` using synthetic inputs. Raw results may include transient audit paths and scanner-reported findings; interpret them with the report. No scanner count is an independently proven vulnerability count.

## Main results

| Evidence | Purpose |
|---|---|
| [pytest.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/pytest.txt) | Original environment: 414 passed, 1 skipped |
| [coverage-tests.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/coverage-tests.txt) | Fresh Python 3.12 core test run |
| [coverage.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/coverage.json) | Statement coverage: 71.38%; detailed executed/missing lines |
| [cpu-integration-final.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cpu-integration-final.txt) | Final Linux integration: 18 passed including real offline training |
| [cpu-integration.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cpu-integration.txt) | Initial Linux run: missing git caused 1 environment failure; real training passed |
| [cpu-pip-check.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cpu-pip-check.txt) | CPU environment dependency consistency |
| [probes.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/probes.json) | Unauthenticated command execution, upload traversal, fake results, feedback loss, privacy probes |
| [additional-probes.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/additional-probes.json) | GGUF, recovery, preflight, robustness, VRAM and cache invalidation probes |
| [sql-probe.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/sql-probe.json) | SQL expression injection with a synthetic database marker |
| [schema-egress-probe.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/schema-egress-probe.json) | JSON Schema reference fetched a loopback HTTP resource |
| [runtime-probe.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/runtime-probe.json) | Missing-input pipeline false success and invalid model promotion |
| [cli-checks.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cli-checks.json) | Real CLI synthetic workflows, unsupported flags, plaintext SQLite, PII retention |
| [environment-final.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/environment-final.json) | Live service HTTP status, listeners, WS origin probe, container IDs |
| [wheel-assets.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/wheel-assets.json) | Built wheel contains no dashboard HTML or safety-hook script |
| [docker-build-isolated.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/docker-build-isolated.txt) | Actual Dockerfile build failure before source copy |
| [webhook-asgi.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/webhook-asgi.txt) | Configured webhook ASGI object missing |
| [macos-train-resolution.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/macos-train-resolution.txt) | Intel macOS cannot resolve pinned Torch wheel |
| [pip-audit-train.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/pip-audit-train.json) | Advisories for declared training pins; direct-only scan, duplicates retained |
| [pip-audit.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/pip-audit.json) | Installed original environment dependency audit |
| [bandit.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/bandit.json) | Static-analysis triage findings, not 110 proven vulnerabilities |
| [source-inventory.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/source-inventory.json) | All 132 Python modules: hashes, symbols, line counts, coverage |
| [openapi.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/openapi.json) | Actual dashboard OpenAPI: 70 paths / 72 HTTP operations |

## Follow-up depth checks

- [Fault-injection and HTTP results](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/deep-probes.json): stale-gate package publication, min/cap feedback loss, deployment hook after failed training, duplicate crash retries, epoch collision, symlink access, invalid config writes and zero-score replacement.
- [Reproduction script](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/deep_probes.py.txt), [output](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/deep-probes.txt), [implementation keyword inventory](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/implementation-gaps.txt). The keyword inventory is a review aid, not a defect count.

## Other evidence files

- [additional_probes.py.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/additional_probes.py.txt)
- [build.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/build.txt)
- [cli-checks-summary.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cli-checks-summary.txt)
- [cli-help.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cli-help.txt)
- [cli_checks.py.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cli_checks.py.txt)
- [coverage-summary.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/coverage-summary.txt)
- [cpu-git-install.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cpu-git-install.txt)
- [cpu-install.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/cpu-install.txt)
- [docker-layer-repro.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/docker-layer-repro.txt)
- [docker-pull.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/docker-pull.txt)
- [doctor.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/doctor.txt)
- [format.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/format.txt)
- [installed-requirements.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/installed-requirements.txt)
- [packages.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/packages.json)
- [pip-audit-train.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/pip-audit-train.txt)
- [pip-audit.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/pip-audit.txt)
- [probes.py.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/probes.py.txt)
- [ruff.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/ruff.txt)
- [train-requirements.txt](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/train-requirements.txt)

## Finding navigator

The report contains **43 numbered findings**, plus state, analytics, UI, packaging, CI and roadmap analysis. Severity reflects stated exposure and assumptions; it is not a computed CVSS score.

- **SEC-01:** Critical: unauthenticated shell execution
- **SEC-02:** Critical: the second terminal API also permits arbitrary code
- **SEC-03:** Critical: arbitrary upload path and overwrite
- **SEC-04:** High: SQL expression injection through analytics
- **SEC-05:** High: missing authentication, authorization, host/origin checks
- **SEC-06:** High: generated GGUF shell script executes config text
- **SEC-07:** High: release and promotion are not uniformly governed
- **SEC-08:** High: local-only mode does not cover evaluation schema retrieval
- **SEC-09:** High: browser assets contradict air-gap and privacy claims
- **SEC-10:** High: PII scanning is not automatic sanitization
- **SEC-11:** High: unauthenticated feedback and weak input controls
- **SEC-12:** High: pinned training dependencies have known advisory matches
- **SEC-13:** Medium/high: Git safety hook scans working-tree bytes, not staged bytes
- **SEC-14:** Medium/high: confidentiality and availability controls are incomplete
- **DAT-01:** High: the SDK compiler contaminates every split
- **DAT-02:** High: MI Guard does not establish “zero lost knowledge”
- **DAT-03:** High: ordering and default thresholds weaken filtering
- **DAT-04:** Medium: immutable snapshots still have incomplete input identity
- **DAT-05:** Medium: provenance fields are silently discarded or misleading
- **DAT-06:** Medium: text/Markdown ingestion is not a document-to-SFT compiler
- **DAT-07:** Medium: tokenization, scale, and leakage controls need work
- **TRN-01:** High: memory estimates disagree by entry point
- **TRN-02:** High: OOM recovery can retain the failed trainer's GPU memory
- **TRN-03:** High: recovery restarts, changes the objective, and loses effective-config provenance
- **TRN-04:** High: simulated runners must not be accepted as real training
- **TRN-05:** Medium/high: real training options and telemetry are incomplete
- **TRN-06:** Medium: hardware and preflight support is overstated
- **TRN-07:** Medium: durable jobs, resume, and resource coordination are missing
- **EVAL-01:** High: invented evaluation results
- **EVAL-02:** Medium/high: robustness grading rewards stable wrong answers
- **EVAL-03:** Medium: deterministic assertions need stronger task semantics
- **EVAL-04:** Medium/high: training/evaluation/export identities need stronger binding
- **EVAL-05:** Medium: comparative gates remain deliberately unimplemented
- **EVAL-06:** High: a real zero score is displayed as an 88% pass rate
- **REL-01:** High: cryptographic integrity is not cryptographic authenticity
- **REL-02:** Medium/high: export safety differs by format
- **REL-03:** Medium: merge/conversion correctness and resource budgets
- **REL-04:** High: deployments and gateway can fabricate success
- **REL-05:** Medium: real CLI deployment is preparation-only
- **FLY-01:** High: unread logs can be lost
- **FLY-02:** High: extraction is not a trained alignment loop
- **FLY-03:** Medium/high: synthetic preference rules can teach bad behavior
- **FLY-04:** High: crash retries duplicate pairs; reused epoch IDs corrupt file/DB agreement
