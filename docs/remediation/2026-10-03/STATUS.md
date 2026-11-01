# Remediation ledger — work started October 3; updated October 5, 2026

**Latest continuation:** [October 20 P0-2 report](../2026-10-20/REPORT.md). Previous [October 19 report](../2026-10-19/REPORT.md), [acceptance status](../2026-10-19/STATUS.md), and [current runbook](../2026-10-19/RUNBOOK.md). The table below retains October 5 evidence and behavior; October 19 supersedes terminal-route responses (now authenticated 404), dependency scans and environment locations.

Branch: `codex/audit-remediation`. Baseline: `bac72593964c5e7218b009824f7146998b6cdfaa`. Changes are local and uncommitted. The original October 2 audit and its evidence are preserved as historical findings.

**Implemented** means the narrow defect has a correction and regression coverage. **Partial** means the original finding's wider acceptance criteria remain unmet. **Open** means no complete implementation is available. None of these labels certifies production security or model quality. See [validation](VALIDATION.md), [technical report](REPORT.md), and [runbook](RUNBOOK.md).

| Finding | Status | Correction and remaining acceptance criteria |
|---|---|---|
| SEC-01 | Implemented | Primary terminal endpoint returns 410; authenticated requests cannot execute shell text. Regression patches subprocess to reject accidental invocation. |
| SEC-02 | Implemented | Second terminal endpoint also returns 410. Both paths are tested together. |
| SEC-03 | Implemented | Generated upload names, bounded streaming, validated formats, no-follow/exclusive creation. Traversal, overwrite, symlink and oversize regressions. Local filesystem administrators remain trusted. |
| SEC-04 | Implemented | Analytics uses explicit identifier allowlists; injected expressions rejected; correlation pairs aligned. Other visualization aggregation correctness is separate work. |
| SEC-05 | Partial | Installation token, signed expiring sessions, host and exact-origin validation cover HTTP/WS. Still need actor identities, roles, permission matrix, revocation, TLS deployment design and multi-user isolation tests. |
| SEC-06 | Implemented | Conversion names/quantization validated; generated shell arguments quoted; subprocess timeout; f16 handling corrected. Real converter matrix remains REL-03. |
| SEC-07 | Partial | Promotion, SDK release and Ollama publication check recorded evidence; copied adapters checked against gated digest. Still need one publication service for every format and final-artifact evaluation. |
| SEC-08 | Implemented | JSON Schema uses an explicit empty external-resource registry. Regression forbids network retrieval while allowing local schema references. |
| SEC-09 | Partial | Browser assets packaged locally with version/license inventory. Still need a CSP without inline/eval exceptions, browser dependency advisory assessment, and complete offline UI verification. |
| SEC-10 | Partial | Explicit flag/redact/reject/quarantine policy; full private-key block redaction. Default flag preserves content. Need labeled multilingual PII/secret corpus and measured recall/false positives; cover logs, exports and retention end to end. |
| SEC-11 | Partial | Required API key, bounded/validated requests, transactional idempotency and server-derived sender metadata. Need per-actor credentials, quotas, key rotation lifecycle and poisoning/review controls. |
| SEC-12 | Partial | Updated pinned training reference stack; real CPU tests pass; installed Python advisory scan and normalized Torch scan have zero known matches. CUDA, browser assets, OS image scanning and full dependency locks remain. |
| SEC-13 | Implemented | Safety hook scans staged blobs, including tests; installed wheel contains hook; unrelated hooks preserved. Worktree/core.hooksPath portability needs a broader platform matrix. |
| SEC-14 | Partial | Authentication and request/upload limits implemented. Need retention/deletion policy, encrypted backups, disk quotas, concurrency limits and recovery drills. |
| DAT-01 | Implemented | SDK/API invoke the real immutable compiler; missing source fails; splits are distinct; no sample manufacturing. Real SDK CPU lifecycle verifies compiled version binding. |
| DAT-02 | Partial | Removed fabricated vector-density score and qualified heuristic claims. Need labeled rare-fact retention study, adversarial jargon controls and downstream held-out comparisons before making knowledge-preservation claims. |
| DAT-03 | Partial | Normalized duplicates remain together even when deduplication is disabled; explicit group IDs supported. Filtering order/default zero threshold, semantic duplicates, contradictory evidence and calibrated thresholds remain. |
| DAT-04 | Implemented | Build identity includes glossary bytes and compiler file hashes; canonical source identity; source/glossary/compiler changes during publication rejected. Future tokenizer/transformation inputs must extend this inventory. |
| DAT-05 | Implemented | Source file/line/format/group metadata survives scoring; unmeasured grounding/coherence/authority/density are null. This preserves attribution, not factual verification. |
| DAT-06 | Open | Document parsing/OCR/tables/cited segments and reviewed document-to-SFT transformation remain absent. Acceptance: traceable source spans, extraction tests, permissions and reviewed supervision. |
| DAT-07 | Partial | Order-independent group splitting and normalized-content grouping implemented. Need real tokenizer/template counts, truncation policy, similarity checks, streaming compilation and peak-RSS benchmarks. |
| TRN-01 | Partial | Shared estimator; removed special benchmark constants; unknown size stays unknown. Need architecture-derived inputs and measured uncertainty bounds on independent GPU runs. |
| TRN-02 | Partial | Failed trainer/model/traceback references released before one retry; weak-reference CPU fault test proves trainer collection. Need actual CUDA allocated/reserved-memory recovery measurements. |
| TRN-03 | Partial | Bounded restart preserves architecture/sequence/objective settings and effective batch; requested/effective configs recorded. Need phase-specific recovery, exact checkpoint resume and immutable per-attempt lineage. |
| TRN-04 | Implemented | CLI, SDK and async adapters share real backend lifecycle; no fabricated losses/artifacts. Offline real CPU tests cover backend and SDK. |
| TRN-05 | Partial | Weight decay wired; adapter/seed/sequence analytics corrected; unknown telemetry stays null. Need objective/masking controls, real step events and supported-option coverage. |
| TRN-06 | Partial | Hardware-aware recipes avoid unsupported quantization/optimizer on CPU; missing release requirements no longer crash. Need free-memory/output-volume preflight and an executed CUDA/MPS/OS matrix. |
| TRN-07 | Partial | Per-project interprocess training lock; persistent run lookup; bounded orchestrator recovery; unsupported cancellation returns 409. Still need worker processes, durable jobs, heartbeat recovery, device admission and verified resume/cancel. |
| EVAL-01 | Implemented | Harness invokes inference/scorers and persists results; API rejects missing suites/runs. Real CPU test preserves a measured 0% result. |
| EVAL-02 | Partial | Strict robustness requires correctness; no empty A grade; entity/negation perturbations require relabeling and are excluded by default. Need reviewed labels, slice metrics and uncertainty estimates. |
| EVAL-03 | Open | Substring/schema assertions do not establish truth or safety. Need task-specific exact/structured/citation checks, expert labels, misuse tests and independently validated judges. |
| EVAL-04 | Partial | Dataset/run/gate/adapter identity flows through SDK/runtime and publication checks. Need resolved base/tokenizer/template/decode/runtime identity and post-transformation evaluation. |
| EVAL-05 | Open | Comparative gates fail closed. Need paired baseline/candidate evidence with identical settings, per-slice thresholds and confidence intervals. |
| EVAL-06 | Implemented | Zero scores remain zero; missing values remain null; no invented default model metadata. |
| REL-01 | Open | Hashes detect changes but do not authenticate publisher. Need signed attestations, trust roots, provenance/SBOM and verification/rotation policy. |
| REL-02 | Partial | Atomic staged SDK bundles, verified adapter copying, safer GGUF script and Ollama digest binding. Need uniform final-artifact policy across all formats. |
| REL-03 | Open | Real merge/conversion equivalence, quantization quality budgets and peak-memory/disk envelopes remain unverified. |
| REL-04 | Implemented | Unsupported SDK/dashboard deployment fails explicitly; gateway forwards real requests and backend errors; inventory and usage come from backend. Success path is mocked in unit tests; live empty-backend failure path verified. |
| REL-05 | Open | Live deployment controller, ownership, readiness, rollback and post-deploy quality verification remain unimplemented. |
| FLY-01 | Implemented | Undersized batches retain pending logs; capped batches acknowledge only persisted source IDs; extraction/persistence/ack use one SQLite transaction. |
| FLY-02 | Partial | Extracted is distinct from trained; trainer failure prevents deploy; deployment requires opt-in and gate. Need actual DPO training bridge and held-out safety/regression evidence. |
| FLY-03 | Partial | Default extraction uses explicit human corrections; synthetic heuristics opt-in and labeled unreviewed. Need reviewer workflow, poisoning controls and curated preference-quality validation. |
| FLY-04 | Partial | Stable pair IDs, exclusive epoch files, transaction rollback and reused-epoch rejection. Hard crashes can leave orphan files; need reconciliation and crash-injection recovery tests before claiming exactly-once publication. |

## Additional corrected contracts

- Config writes validate strict models, require ETag/If-Match and atomically replace the file; stale writers receive 412 and missing preconditions 428.
- Compiled-version previews verify their inventory; corrupt snapshots return 409. Snapshot deletion/recompilation through the raw-data API returns 409. Preview limits are 1–100.
- Docker builds from the actual source before installation, runs project services without root and binds host ports to loopback. The webhook ASGI entry point exists.
- Wheel contains dashboard templates, local browser assets and packaged hook. CI installs evaluation dependencies and runs a dedicated real CPU job; release publishing failures are no longer ignored.

## Priority of remaining work

1. **Execution/state:** durable isolated worker, actual cancellation/resume, device admission, crash reconciliation.
2. **Evidence identity:** resolved model/tokenizer/runtime identity, paired comparative gates, final-artifact evaluation, unified publication.
3. **Data trust:** calibrated quality/PII policies, tokenizer-aware compilation, reviewed preference pipeline and document ingestion.
4. **Operations:** roles/TLS/quotas/retention, full dependency and container provenance, signed release attestations, verified serving rollback.

The original module inventory remains the baseline inventory; it is not represented as a new line-by-line audit of every changed file.
