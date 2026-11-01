# MoroAI: engineering, security, feature, and development-environment audit

**Date:** 2026-10-02. **Source revision:** `bac72593964c5e7218b009824f7146998b6cdfaa`.

**Companion design:** [Remediation blueprint](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/REMEDIATION_BLUEPRINT.md)

**Navigation:** [Module inventory](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/MODULE_INVENTORY.md) · [Environment runbook](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/RUNBOOK.md) · [Evidence index](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/README.md)

**Verdict:** MoroAI contains a useful, substantially implemented CLI for dataset preparation, LoRA training, deterministic evaluation, and guarded adapter packaging. It is **not ready to be represented as a secure, air-gapped, automatically self-healing production foundry**. The largest blockers are unauthenticated host command execution, arbitrary file writes, SQL injection, simulated results presented as completed work, and inconsistent governance across entry points.

The older `moro_deep_analysis.md` is not an accurate current defect list. Many of its CLI findings have been fixed. This audit rechecks the repository and supplied “Under the Hood” text against current code and fresh observations.

## 1. Scope, method, and evidence limits

I inventoried **132 Python source files / 20,489 source lines**, **46 test files / 6,897 test lines**, the dashboard HTML, packaging, Docker configuration, CI workflows, examples, project documentation, and the supplied feature description. The file appendix records source hashes, symbols, and measured statement coverage. I traced the CLI, dashboard, SDK/orchestrator, data, training, evaluation, release, deployment, feedback, and storage paths separately.

The security checks used loopback services and disposable synthetic projects. Command-execution probes printed harmless markers; filesystem probes wrote only inside audit temporary directories; the SQL probe retrieved an audit-created marker. No real credentials, private datasets, existing production models, or unrelated containers were used as test targets. Application source was not modified as part of this audit.

Evidence labels used below:

- **Observed:** reproduced by an actual command, HTTP request, or isolated function call.
- **Code-confirmed:** directly follows from the implementation, but its full operational impact was not exercised.
- **Gap:** required behavior is absent from the reviewed paths, or a claim lacks supporting evidence.
- **Recommendation:** proposed future behavior; not an assertion that it already exists.

A finite audit cannot establish the absence of every vulnerability. In particular, GPU behavior, model quality, real Ollama adapter import, large-data performance, browser compatibility, and regulatory compliance require separate acceptance work. The report distinguishes these from tested behavior. Follow-up fault-injection and HTTP probes are preserved in [deep-probes.json](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/deep-probes.json); controlled races and injected failures are explicitly identified below.

### Verification results

| Check | Result | What it establishes |
|---|---|---|
| Existing Python 3.14 environment, `pytest -q` | **414 passed, 1 skipped, 3 warnings**, 17.24 s | Current tests pass; optional real training skipped |
| Separate Python 3.12 environment with eval extra and coverage | **414 passed, 1 skipped**, 28.17 s | Core behavior also passes with fresh dependency resolution |
| Statement coverage | **71.38%**, 5,964 / 8,355 statements | Execution coverage, not assertion strength or branch coverage |
| Ruff lint | Pass | Selected E/F/I/UP checks only |
| Ruff format | Pass, 197 files | Formatting only |
| Existing environment `pip check` | Pass | Installed dependency constraints are consistent |
| Wheel + source distribution | Build succeeds | Artifacts build, but required runtime assets are missing |
| Bandit | 110 flags: 1 high, 20 medium, 89 low | Triage inputs; these are not 110 proven vulnerabilities |
| Installed-environment dependency audit | 1 unique advisory on `pip`; duplicate feed entries | Tooling issue; no claim that absent training packages were checked as installed |
| Declared train/CUDA pins audit | 20 unique package/advisory pairs across 4 packages | Advisory matches requiring reachability review; transitive training dependencies were not fully audited by this scan |
| Native Intel-macOS training resolution | Fails for `torch==2.8.0` | Pinned train extra has no matching Intel Mac wheel |
| Docker application image | Fails installing editable project before `src` exists | Repository Dockerfile is not currently buildable |
| Linux CPU integration | **18 passed, 3 warnings**, 11.57 s | Includes actual offline one-step LoRA training, checkpoint, saved safetensors, adapter reload and generation |

The Linux CPU stack used Python 3.11.17 and the repository's pinned Torch/Transformers/PEFT/TRL versions, with the CPU Torch wheel. The first integration run passed 17 tests, including actual training, but failed the lifecycle test because the minimal audit container lacked `git`. After installing `git`, all 18 passed. This environmental correction did not modify Moro source. The real-training test creates a tiny random GPT-2 model locally and denies socket connections during training/evaluation; it does not establish pretrained-model quality, large-model feasibility, GPU recovery, or all-application air-gap behavior. Dependency/image installation itself used the network.

`training/hf_backend.py` had 65.34% statement coverage in the core run, `export/gates.py` 86.30%, `dashboard/mission_control.py` 40.76%, and `runtime/orchestrator.py` 73.78%. A simulated runtime can have high coverage without exercising a trainer.

## 2. The actual architecture

There are multiple implementations of the same lifecycle stages with materially different guarantees.

| Stage | CLI path | Dashboard / SDK / runtime path | Consequence |
|---|---|---|---|
| Compile | `cli/data.py` → ingest / normalize / clean / split / immutable versions | `data/compiler.py` copies the source to train, validation, and eval | Data leakage and privacy behavior depend on entry point |
| Recipe | `suggest_recipe()` uses explicitly uncalibrated heuristics | `RecipeEngine.generate_recipe()` produces mostly fixed settings | “Hardware aware” does not describe every caller |
| Train | `HuggingFaceBackend` invokes real TRL SFTTrainer | REST training simulates 100 steps; sync/async runner classes simulate or record supplied metrics | A completed status can mean no training occurred |
| Evaluate | `eval/runner.py` loads a model, generates, scores, hashes evidence | `EvalHarness` invents pass counts; async harness passes every case | Evaluation success is not consistently evidence-backed |
| Release | CLI calls eligibility and release-gate checks | `ReleaseManager` omits those checks | Governance can be bypassed through alternate APIs |
| Deploy | CLI prepares an Ollama package and prints manual next steps | REST / `DeploymentManager` create metadata and declare running/completed | No runtime deployment is required for success |
| Feedback | CLI mines SQLite logs into DPO pairs | Convenience wrapper may count files × 5 | Feedback counts are not consistently real |

**Observed:** `MoroRuntimeOrchestrator.run_complete_pipeline('missing.jsonl', 'missing-model', 'missing.yaml', 'ollama')` reported all six phases completed in approximately 0.4 seconds, a 100% evaluation pass rate, and `success: true`. Foreign-key failures when registering release/deployment lineage were logged but did not fail the pipeline.

The HTML also has shortcuts that call real CLI commands through `/api/terminal/execute`. Therefore it would be inaccurate to say that every dashboard action is simulated. The problem is mixed semantics: some buttons run the real CLI, REST control endpoints simulate work, and charts/counters can still display invented values.

**Additional confirmed strengths:** the real training backend sets model/trainer/data seeds, disables cloud reporting and Hub pushes, and local-only model loading rejects `trust_remote_code=true`. The offline tiny-model test verifies that this specific training/evaluation path operates with socket connections denied. Those protections should be retained when unifying the services.

**Architectural recommendation:** extract one application-service layer around the real CLI implementations. CLI, REST, jobs, and SDK should invoke those same services. Make simulation an explicit mode with a separate namespace and artifact type that cannot satisfy release or deployment policies.

## 3. Supplied feature claims versus implementation

| Supplied claim | Current evidence | Required correction or work |
|---|---|---|
| Shannon entropy, token-pair PPMI, dense embeddings | Compression ratio and glossary-overlap density; no token-pair probability estimation or embedding computation in the compiler | Describe these as heuristics; implement and validate true estimators only if justified |
| Cosine/Jaccard boundary clustering | Exact hashes and lowercase/whitespace-normalized hashes | Implement semantic/near-duplicate clustering, with a measured rare-fact recall budget |
| MI Guard preserves knowledge from dedup pruning | Deduplication happens before MI Guard; duplicates never reach it | Correct the claim and design protected-cluster handling if needed |
| Exact peak VRAM, megabyte accuracy, zero OOM | Several inconsistent estimators; the main planner itself warns estimates are uncalibrated | Replace guarantees with calibrated estimates and uncertainty ranges |
| Five-stage live recovery, checkpoint rollback, no data loss | Single restart after applying config reductions; no checkpoint resume; model load is outside the recovery try block | Implement bounded, checkpoint-aware recovery and record effective configuration |
| Semantic LLM judge and Wasserstein drift | No corresponding implementation in the evaluated paths | Missing features, not release barriers currently enforced |
| Adversarial robustness | Perturbation machinery exists, but grading can reward consistently wrong answers | Separate accuracy, stability, and semantic validity of perturbations |
| Automatic DPO alignment | Preference-pair mining exists; no concrete DPOTrainer bridge is wired into normal CLI cycles | Implement trainer, dataset validation, held-out eval, and an independent promotion policy |
| React + Tailwind + SSE Mission Control | FastAPI and HTML with Alpine/HTMX/CDN scripts; polling and backend WebSocket routes | Correct stack and telemetry description; bundle assets locally |
| Cryptographic signed SBOM / RSA release signature | SHA-256 hashes and JSON manifests on some CLI export paths; no signing/verifying infrastructure | Distinguish integrity hashes from authenticity signatures and an SBOM |
| One-command merge → quantize → Ollama registration | `moro deploy` prepares an adapter package; it does not run `ollama create` | Add actual runtime import/verification or document preparation-only behavior |
| vLLM / Docker serving | CLI rejects non-Ollama targets; other manager paths return metadata | Implement serving adapters and integration tests before advertising support |
| Strict zero outbound / encrypted SQLite / automatic sanitization | Model-loader local-cache restrictions exist; UI loads third-party scripts, SQLite is plain, PII scan is advisory | Narrow privacy promises to implemented boundaries |

The supplied command examples are not all executable. Fresh CLI probes rejected `doctor --privacy`, `recipe generate`, `release verify`, `data build --mi-guard-threshold`, and `train --auto-heal` with exit code 2. `data build` also has no supplied `--source`/`--output` options; recipe uses `--max-seq-length`, and deploy uses `--tag`, not the supplied `--name`. Default ports differ across docs and entry points.

## 4. Security: trust boundaries and prioritized findings

### Threat model

Assets include private prompts/completions, raw datasets, rejected data, adapters/base weights, evaluation evidence, filesystem access, environment credentials, Docker privileges, and production-model selection. Attackers could be an unauthenticated network caller where ports are exposed, a hostile web origin reaching localhost where browser policy permits, a malicious dataset/config/suite author, a poisoned feedback sender, or a compromised dependency/model artifact.

Loopback binding reduces network exposure but does not authenticate callers. Conversely, this audit did not demonstrate that every browser allows public-to-local requests: private-network access, mixed-content policy, and browser versions matter. The application should enforce its own boundary instead of relying on those differences.

### SEC-01 — Critical: unauthenticated shell execution

**Observed.** `/api/terminal/execute` checks whether the command starts with `moro`, `docker ps`, `docker logs`, or `curl`, then executes it with `shell=True`. A harmless `moro --help; printf MORO_AUDIT_SHELL_MARKER` request returned the marker without credentials.

The prefix is not a shell grammar boundary. Operators, substitution, pipelines, and redirections remain executable. The process inherits the server user's privileges and environment. On the developer host this can reach files and Docker access available to that account; it is not automatically root, but the impact is broad. `curl` alone also permits arbitrary outbound requests and output-file writes.

**Fix:** remove arbitrary shell execution from the web API. Expose typed operations with fixed executable/argument lists, explicit allowed project resources, bounded output, cancellation, and authorization. If an administrative terminal remains necessary, isolate it into a separate opt-in authenticated service with restricted OS permissions.

**Acceptance:** all shell metacharacter payloads are rejected; no general interpreter is exposed; unauthorized requests fail before starting a process. Source: [src/moro/dashboard/mission_control.py:714](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:714).

### SEC-02 — Critical: the second terminal API also permits arbitrary code

**Observed.** `/api/system/terminal/execute` permits commands starting with `python`, `pytest`, or `moro`. It does not use a shell, but a request executing `python3 -c print(673829)` returned `673829` without credentials. A Python interpreter is itself arbitrary code execution; replacing `shell=True` alone will not secure the application. Caller-controlled `cwd` and inherited environment expand access.

**Fix:** apply the SEC-01 command boundary to both routes; do not treat a binary-name allowlist that contains an interpreter as a sandbox. Source: [src/moro/dashboard/api/system.py:190](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:190).

### SEC-03 — Critical: arbitrary upload path and overwrite

**Observed.** Uploading an allowed `.txt` multipart file with `name=../../audit-marker.unsupported` wrote outside `data/raw` and accepted an otherwise unsupported destination suffix. The code validates the original filename extension but writes to the unvalidated `name`. A second in-process HTTP probe confirmed that an existing symlink in `data/raw` lets upload overwrite a synthetic target outside the project; the preview endpoint also returned that external target's content. The symlink probe requires a preexisting link and does not establish that upload can create one. Absolute paths also require rejection. The multiple-upload route directly uses the uploaded filename.

Impact includes overwriting config or other writable files and, together with other capabilities, compromising subsequent execution. The probe used only an audit marker, not actual sensitive files.

**Fix:** server-generated storage IDs, metadata-only display names, extension/content validation of the actual stored object, exclusive creation, resolved containment and symlink protections, streaming size limits, and atomic publication. Add traversal, absolute-path, collision, and symlink tests. Source: [src/moro/dashboard/api/datasets.py:185](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/datasets.py:185).

### SEC-04 — High: SQL expression injection through analytics

**Observed.** `/api/analytics/viz/hyperparameter-heatmap` forwards `x_param`, `y_param`, and `metric` into an f-string SQL query. The harmless expression `learning_rate || (SELECT value FROM audit_marker LIMIT 1)` returned a marker from a separately created table in the audit analytics database.

This proves unintended reads through SQL expression injection. It does not establish arbitrary multi-statement execution or host code execution. SQLite's single-statement API does not prevent expression injection.

**Fix:** map a closed enum of public metric names to fixed SQL identifiers. Bind data values; do not attempt to parameterize identifiers as values. Review the similar `metric_name` interpolation in tracker correlation queries. Sources: [src/moro/analytics/visualizations.py:117](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/visualizations.py:117), [src/moro/analytics/tracker.py:539](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/tracker.py:539).

### SEC-05 — High: missing authentication, authorization, host/origin checks

**Observed / code-confirmed.** The served OpenAPI has 70 paths / 72 HTTP operations and no declared security schemes. Protected state-changing functionality has no global authentication layer. Synthetic requests could upload, start a simulated run, declare a deployment, execute commands, and ingest feedback without authentication. A preflight accepted `https://untrusted.invalid` with credentials enabled, an unexpected Host header received HTTP 200, and a WebSocket upgrade from that origin received 101.

Dashboard Docker routes can list/start/stop containers by supplied ID; they are not restricted to Moro-owned container labels. I did not stop any real container to test this. Config writes, model promotion/deletion, raw-data previews, analytics, and logs need distinct permissions.

**Fix:** local bootstrap token/session authentication; explicit loopback hosts and exact UI origins; WebSocket authentication/origin validation; CSRF protection if cookie sessions are used; viewer/operator/admin roles; project-scoped objects; Docker resource allowlists. CORS is a browser policy, not authorization. [FastAPI's CORS guidance](https://fastapi.tiangolo.com/tutorial/cors/) recommends explicit allowed origins.

Sources: [src/moro/dashboard/mission_control.py:410](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/mission_control.py:410), [src/moro/dashboard/gateway.py:27](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:27), [src/moro/dashboard/api/system.py:262](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/system.py:262).

### SEC-06 — High: generated GGUF shell script executes config text

**Observed.** `write_gguf_script()` interpolates project name, paths, and quantization into double-quoted shell assignments. A synthetic project name containing command substitution created an audit marker when the generated script was run—even though conversion subsequently exited because llama.cpp was absent.

**Fix:** validate project slugs and quantization enums, serialize shell literals with proper quoting, or eliminate generated shell in favor of fixed argument-vector execution. Treat paths as untrusted data too: a legitimate path can contain shell-significant characters. Source: [src/moro/export/gguf.py:17](/Users/mac/Dev/MoroAI/moro/src/moro/export/gguf.py:17).

### SEC-07 — High: release and promotion are not uniformly governed

**Observed.** `ReleaseManager.create_release_async()` accepts a missing run and `pass_rate: 0`, reporting completed. `float(eval_data.get('pass_rate') or 1.0)` replaces a valid zero with one. Even a nonzero low score is only rejected if negative. The synchronous method has no gate checks. Version/run strings are also joined into paths without the CLI's deployment-directory validation.

**Observed.** Promoting a nonexistent model through `StateManager` returned true and removed the current production designation from every model. There is no verification of the selected model's existence before demotion, no affected-row check, and no invocation of the CLI artifact-bound release gate.

**Fix:** one promotion/release service; verify target existence, immutable artifacts, actual eval evidence and policy before any mutation; transactional per-project/per-model deployment slots; require row counts; leave current production unchanged on failure. Sources: [src/moro/release/manager.py:48](/Users/mac/Dev/MoroAI/moro/src/moro/release/manager.py:48), [src/moro/state/manager.py:448](/Users/mac/Dev/MoroAI/moro/src/moro/state/manager.py:448), [src/moro/dashboard/api/models.py:165](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:165).

### SEC-08 — High: local-only mode does not cover evaluation schema retrieval

**Observed with the eval extra.** A JSON Schema `$ref` to a loopback audit HTTP server caused `score_case()` to fetch `/audit-schema`. This path calls `jsonschema.validate()` without an offline resolver or an allowlisted reference registry. It has no privacy-mode argument.

A supplied suite can therefore cause outbound HTTP independently of local model loading; internal endpoints can be targeted depending on the resolver's supported schemes and environment. Only a local marker endpoint was tested, not external or cloud metadata services.

**Fix:** prohibit remote references or prebundle schema resources in an explicit in-memory registry; propagate a single network policy throughout evaluation. Add a socket-denial test for schemas, not only model loading. Source: [src/moro/eval/scorers.py:71](/Users/mac/Dev/MoroAI/moro/src/moro/eval/scorers.py:71).

### SEC-09 — High: browser assets contradict air-gap and privacy claims

**Code-confirmed.** The dashboard loads Tailwind, HTMX, Alpine, Chart.js, xterm, and Dropzone from public CDNs. Some references use floating versions. There is no integrity metadata or restrictive CSP in the shown page/server configuration. Third-party scripts execute in the dashboard origin, which can call its powerful local endpoints and read responses.

This proves an external dependency and an avoidable trust relationship. It does **not** prove that any CDN currently exfiltrates data. The page also cannot deliver its full interactive behavior in a strict disconnected environment without cached assets.

**Fix:** vendor exact assets into the wheel, enforce CSP, remove inline dynamic execution as necessary, and run an offline browser acceptance test with external requests blocked. Source: [src/moro/dashboard/templates/mission_control.html:9](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/templates/mission_control.html:9).

### SEC-10 — High: PII scanning is not automatic sanitization

**Observed.** A synthetic dataset built with `pii_scan: true` retained `audit0@example.com` in the compiled snapshot. `cli/data.py` calls `scan_rows`, not `redact_rows`; defaults set scanning false. Explicit `moro guard redact` is a separate operation.

`redact_text()` removes only a PEM private-key header, leaving its body and footer. A fake key-body marker survived the redactor. Regex matching also has expected limitations for international phone numbers, names, addresses, split/encoded tokens, Unicode obfuscation, and unusual credential formats. The guard's “safe for training” message overstates what a regex scan can prove. Scan snippets may print the very sensitive content they identify.

**Fix:** explicit `privacy.action = flag|quarantine|redact|reject` policy, conservative defaults for private deployments, parser-aware full-block secret redaction, metadata consistency, masked diagnostics, and language/domain-specific evaluation. Retain false-positive review and measured false-negative rates. Sources: [src/moro/cli/data.py:110](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py:110), [src/moro/data/privacy.py:25](/Users/mac/Dev/MoroAI/moro/src/moro/data/privacy.py:25), [src/moro/cli/guard.py:83](/Users/mac/Dev/MoroAI/moro/src/moro/cli/guard.py:83).

### SEC-11 — High: unauthenticated feedback and weak input controls

**Observed / code-confirmed.** Webhook authentication is optional and absent by default. It accepted a synthetic correction with no key. No replay identity, HMAC signature, sender authorization, request-size cap, batch cap enforcement, rating bounds, or robust payload schema is applied in the handler. `batch_size` is stored but not used to constrain submitted batches.

The standard-library `HTTPServer` is single threaded; an unbounded/incomplete request-body read can monopolize ingestion. These are resource-exhaustion risks inferred from code, not stress-tested on the user's machine. Feedback also persists raw prompts, completions, context, and corrections with no retention or redaction policy.

**Fix:** required local auth or authenticated ingestion identity, request limits/timeouts, validated models, idempotency keys, bounded queues, separate quarantine, retention/deletion controls, and provenance per feedback actor. Human correction is a preference signal, not proof of factual truth. Source: [src/moro/flywheel/webhook/receiver.py:108](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/webhook/receiver.py:108).

### SEC-12 — High: pinned training dependencies have known advisory matches

**Observed scanner result:** 20 unique package/advisory pairs were reported for declared training pins: torch (8), transformers (10), datasets (1), accelerate (1). The raw scan contains duplicate advisory entries; they were deduplicated. Some feed entries omit fixes, and not every affected feature is used by Moro. This is not a claim that 20 remotely exploitable paths were proven.

One independently verified example: the upstream PyTorch advisory lists versions through 2.9.1 as affected by a malicious checkpoint issue even with `weights_only=True`; Moro pins 2.8.0. That specific issue lists 2.10.0+ as patched. [PyTorch advisory GHSA-63cw-57p8-fm3p](https://github.com/pytorch/pytorch/security/advisories/GHSA-63cw-57p8-fm3p).

Moro accepts nonempty `.bin` adapter artifacts structurally, and “local” model files are not necessarily trustworthy. Prefer safetensors and validate tensor structure; avoid pickle-based artifacts from untrusted authors. This is consistent with [PyTorch's model-security guidance](https://github.com/pytorch/pytorch/blob/main/SECURITY.md).

**Fix:** review each advisory against used features, update a compatible tested stack, lock transitive dependencies with hashes, scan that full lock, and retain hardware/serialization regression tests. Do not blindly jump all packages to latest without compatibility testing. The installed Mac environment also has a pip advisory match; its training packages are absent. Upstream pages for some scanner identifiers were unavailable, so the evidence retains their status as feed reports rather than independently confirmed exploits.

### SEC-13 — Medium/high: Git safety hook scans working-tree bytes, not staged bytes

**Code-confirmed.** The hook obtains staged filenames, then opens those paths in the working tree. A staged secret with an unstaged sanitized replacement can pass; the committed blob differs from the scanned content. Broad substring exemptions for test/mock/fixture paths skip real content too. Some file extensions are skipped. The advertised unsafe-eval-config check is not implemented.

Hook installation can overwrite an existing direct hook despite an unused `force` parameter. Installed-wheel behavior is additionally broken because the script is not packaged.

**Fix:** scan `git show :path`/index blobs with NUL-safe filename handling, use exact reviewed test-fixture allowlists, preserve/chaining existing hooks, and run a separate server-side CI secret scan. Source: [scripts/hooks/pre_commit_safety_check.py:105](/Users/mac/Dev/MoroAI/moro/scripts/hooks/pre_commit_safety_check.py:105), [src/moro/cli/hooks.py:105](/Users/mac/Dev/MoroAI/moro/src/moro/cli/hooks.py:105).

### SEC-14 — Medium/high: confidentiality and availability controls are incomplete

**Observed:** newly created SQLite state has a `SQLite format 3` plaintext header. No application encryption is configured. That does not establish whether the host disk itself is encrypted; FileVault was not audited. JSONL snapshots, feedback, log output, SQLite WAL files, and model weights also need a documented confidentiality/backup/retention policy.

**Code-confirmed risks:** blocking subprocesses and SQLite/filesystem work inside `async def` endpoints can block the event loop; request sizes and list limits are not consistently bounded; regex evaluation has no execution deadline; background tasks have no durable queue; raw exception details may expose local paths. The legacy UI uses string interpolation into `innerHTML`, warranting an XSS review if retained. No browser XSS exploit was attempted.

**Fix:** bounded worker processes/jobs, quotas, timeouts and cancellation, safe text rendering, private file permissions, project access controls, masked logs, and a clear choice between host-disk encryption and application-level encrypted stores. Never label a plain SQLite file encrypted.

## 5. Data engineering and scientific validity

### DAT-01 — High: the SDK compiler contaminates every split

**Observed.** With a one-row source, `DataCompiler` produced byte-identical train, validation, and evaluation files. It simply copies raw bytes; it does not normalize, redact, score, or deduplicate them, yet can register `pii_clean: true` and `deduplicated: true` from input booleans. CSV/JSON inputs copied into `train.jsonl` may not even be JSONL. A missing path manufactures a sample and reports counts rather than failing.

Existing validation/eval files are preserved on later calls, while train is overwritten, so snapshots can mix data generations. This path feeds dashboard compilation and the runtime orchestrator. Replace it with the real compiler service and reject missing/unsupported inputs. Source: [src/moro/data/compiler.py:29](/Users/mac/Dev/MoroAI/moro/src/moro/data/compiler.py:29).

### DAT-02 — High: MI Guard does not establish “zero lost knowledge”

`calculate_domain_ppmi()` computes unique glossary-token density × 10. It does not estimate `P(w1,w2)/(P(w1)P(w2))`. `calculate_zlib_entropy()` is compressed-size/raw-size, not Shannon entropy or perplexity; short strings can exceed 1 due to compression overhead. “Resnik IC” divides token occurrence count by document count, mixes whitespace and regex tokenization, and does not estimate a consistent document probability. `local_vector_density` is always 0.5.

The guard uses fixed thresholds; glossary density must reach 50% or the rarity score must reach 8. With the frequency-one lower bound, the latter generally requires on the order of `exp(8)` documents, so behavior changes substantially with corpus size. Jargon stuffing or random rare tokens may trigger preservation without factual value. Multiword glossary entries do not intersect a set of individual word tokens.

**Required validation:** a labeled corpus of rare facts, boilerplate, duplicates, conflicting facts, jargon spam, and multilingual examples; measure precision/recall, rare-fact retention, false preservation, and downstream quality. Compare against simple baselines and evaluate on held-out data. Preserve heuristic names honestly until this evidence exists. Source: [src/moro/data/quality.py:66](/Users/mac/Dev/MoroAI/moro/src/moro/data/quality.py:66).

### DAT-03 — High: ordering and default thresholds weaken filtering

Deduplication precedes MI scoring, so the guard cannot save anything removed as a duplicate. Classifications such as `NOISY_OUTLIER` do not themselves remove a row; filtering checks the composite quality score, whose default minimum is zero. The composite score is largely completeness/length/repetition/formatting and glossary density. Therefore a noise label can coexist with acceptance.

Near-dedup handles case and whitespace, not paraphrases or shared-document boundaries. Add policy for normalized duplicates, semantic clusters, contradiction preservation, group-aware split assignment, and explicit reasons for every exclusion. Source: [src/moro/data/clean.py:83](/Users/mac/Dev/MoroAI/moro/src/moro/data/clean.py:83).

### DAT-04 — Medium: immutable snapshots still have incomplete input identity

The CLI snapshot design is a real improvement: unique directories, staged publication, file inventories, source recheck, config canonicalization, split hashes, and run binding exist. However the build key includes the glossary path but not its bytes; it omits compiler implementation identity beyond a constant `compiler: 1`. Changing the glossary left the key unchanged in an isolated probe. An implicit root `domain_glossary.txt` can also override an explicitly configured glossary.

Include glossary bytes/hash, normalizer/scorer policy version, tokenizer/chat template identities if used, and other transformation inputs. Keep source/import fingerprint semantics consistent. Source: [src/moro/data/versions.py:20](/Users/mac/Dev/MoroAI/moro/src/moro/data/versions.py:20), [src/moro/cli/data.py:81](/Users/mac/Dev/MoroAI/moro/src/moro/cli/data.py:81).

### DAT-05 — Medium: provenance fields are silently discarded or misleading

Normalization passes source-file/line/format keys into `DatasetRowMetadata`, but those keys are not declared and its `extra` dictionary is not automatically populated. Cleaning replaces metadata with new scoring metadata. Source string remains, but row-level location metadata is lost. PII scanning occurs after metadata generation and updates top-level flags, leaving `metadata.pii_detected`/privacy flags inconsistent. Domain-quality scores default to 1.0 and authority defaults to “official” without verification.

Preserve explicit provenance separately from derived metrics; use unknown/null for unmeasured grounding/coherence/authority; update privacy metadata atomically. Sources: [src/moro/data/normalize.py:52](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:52), [src/moro/data/models.py:76](/Users/mac/Dev/MoroAI/moro/src/moro/data/models.py:76).

### DAT-06 — Medium: text/Markdown ingestion is not a document-to-SFT compiler

Readers accept TXT/Markdown, but normalization rejects text-only rows for SFT. This is a reasonable restriction, but conflicts with broad “uncurated enterprise data in, ready model out” wording. There is no implemented PDF/DOCX parsing, OCR, table preservation, chunk citation, document hierarchy, multilingual extraction pipeline, or verified QA synthesis here.

Clarify supported schemas now. Add document ingestion only with source permissions, traceable segments, evaluation, and user review; do not automatically turn arbitrary prose into ground truth. Sources: [src/moro/data/ingest.py:7](/Users/mac/Dev/MoroAI/moro/src/moro/data/ingest.py:7), [src/moro/data/normalize.py:131](/Users/mac/Dev/MoroAI/moro/src/moro/data/normalize.py:131).

### DAT-07 — Medium: tokenization, scale, and leakage controls need work

Token counts are word estimates optimized for English, not the actual model tokenizer or chat template. Length rejection can lose useful data, while actual training truncation can remove target answers. Full row lists, global counters, normalized copies and JSON arrays are memory-resident. JSON input applies a limit after full parsing. Splits are deterministic for the same input order and seed, but not group-aware or invariant to ordering changes.

Add tokenizer-aware length accounting, a documented long-example strategy, deterministic group/document/time splits, cross-split similarity checks, streaming/staged processing and peak-RSS benchmarks. Benchmark realistic diversity and privacy/scoring work; the current compiler throughput test mostly measures line counting and copying.

## 6. Hardware, recipes, and training

### TRN-01 — High: memory estimates disagree by entry point

The principal planner is transparent that its memory estimate is an uncalibrated heuristic. The backend dry-run uses a separate model-name heuristic with fixed overheads. `predict_peak_vram_gb()` has hardcoded branches around three benchmark cases: a 1.5B model with sequence length 1024 and rank 16 returned **3.15 GB for batch size 1 and 100, even with quantization `none`**. Unknown names default differently in different paths. `validate_project()` assumes unknown model size is 1.5B, undermining the planner's safer unknown state.

Use one estimator based on actual architecture/config, training precision, quantization implementation, target modules, sequence distribution, optimizer, attention kernels, checkpointing, and available—not total—memory. Fit conservative uncertainty bounds to measured load/train/eval/save peaks on independent hardware runs. A test comparing hardcoded answers against three fixed constants does not establish prediction accuracy. Sources: [src/moro/recipes/rules.py:37](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/rules.py:37), [src/moro/recipes/engine.py:219](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/engine.py:219), [src/moro/training/hf_backend.py:76](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:76), [tests/benchmarks/test_performance.py:86](/Users/mac/Dev/MoroAI/moro/tests/benchmarks/test_performance.py:86).

### TRN-02 — High: OOM recovery can retain the failed trainer's GPU memory

The handler deletes local `model` but keeps `trainer`, which still refers to that model, optimizer, and allocations; the active exception traceback may retain more. `empty_cache()` cannot free tensors with live references. The handler then loads another model. This is a code-confirmed memory-lifetime defect; CUDA reproduction was not possible on this host.

Use an isolated worker process per attempt, or fully tear down trainer/optimizer/model/traceback references before reconstruction. Capture allocation diagnostics and verify that failure-recovery memory returns close to baseline before retry. Source: [src/moro/training/hf_backend.py:297](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:297).

### TRN-03 — High: recovery restarts, changes the objective, and loses effective-config provenance

Only `trainer.train()` is inside the recovery handler. Loading, preparation, saving, and final evaluation OOMs are outside it. A broad `"alloc"` substring can misclassify other runtime errors. All available downgrade steps are applied together, followed by one new training call with no checkpoint resume. Reducing rank/target modules changes adapter architecture; shortening the entire sequence limit changes available supervision. At batch size one, doubling accumulation changes effective batch without lowering activation peak.

The original CLI config/hash are saved before training. The returned recovery actions do not replace the saved effective configuration or bind it to final adapter rank/targets. This creates inaccurate provenance even if training succeeds. The recovery docstring also promises a `moro.yaml` update that is not performed here.

**Fix:** precise OOM classification, per-phase handling, bounded attempts, distinguish resumable batch/checkpointing changes from retraining with a new architecture, immutable attempt records, effective config hash, RNG/optimizer/scheduler state, and parent-child lineage. Verify adapter metadata against the effective config at export. Sources: [src/moro/training/recovery.py:30](/Users/mac/Dev/MoroAI/moro/src/moro/training/recovery.py:30), [src/moro/training/hf_backend.py:364](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:364), [src/moro/cli/train.py:93](/Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py:93).

### TRN-04 — High: simulated runners must not be accepted as real training

REST `/api/training/start` accepted a missing model, missing dataset and negative epochs, then completed in about four seconds with loss 0.2 and peak VRAM 4.49 GB on a host without PyTorch. `TrainingRunner` can complete with no steps, write a minimal config without weights and report loss 1.5. `AsyncTrainingRunner` sleeps and generates a loss curve.

Either remove these paths from production or explicitly type them as simulations. Jobs must invoke the real backend, fail if dependencies/data/model are absent, and verify actual saved tensors before completion. Sources: [src/moro/dashboard/api/training.py:137](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/training.py:137), [src/moro/training/runner.py:93](/Users/mac/Dev/MoroAI/moro/src/moro/training/runner.py:93), [src/moro/training/async_runner.py:65](/Users/mac/Dev/MoroAI/moro/src/moro/training/async_runner.py:65).

### TRN-05 — Medium/high: real training options and telemetry are incomplete

`training.weight_decay` is accepted and recorded but not passed into either SFTConfig construction. The objective uses all conversation tokens; assistant-only loss is not supported. Replay ratio / KL suggestions are not wired into the dataset or trainer objective. The CLI analytics snapshot reads LoRA fields from `cfg.training` rather than `cfg.adapter`, max length from the wrong section, and seed from the wrong section; these can record null/default values instead of actual settings. The Hugging Face backend does not wire a step callback into the analytics tracker.

Add explicit objective/masking controls, pass every supported setting, reject unused options, and use a structured effective-config object for both trainer and analytics. Surface measured tokens/sec only when measured; do not fill missing telemetry with constants. Sources: [src/moro/training/hf_backend.py:232](/Users/mac/Dev/MoroAI/moro/src/moro/training/hf_backend.py:232), [src/moro/cli/train.py:144](/Users/mac/Dev/MoroAI/moro/src/moro/cli/train.py:144), [src/moro/recipes/mixing.py:54](/Users/mac/Dev/MoroAI/moro/src/moro/recipes/mixing.py:54).

### TRN-06 — Medium: hardware and preflight support is overstated

GPU detection uses total memory; MPS uses 75% of total host RAM; disk checks `/` rather than the selected project/output filesystem. Quantized and 8-bit optimizer paths require CUDA; FP16/BF16 restrictions are explicit. No MLX, FSDP/multi-GPU orchestration, ROCm-specific validation, or demonstrated 70B support was found in the backend. Native Intel Mac installation of the pinned PyTorch version fails; the core CLI still works.

Preflight can mark CPU/MPS compatibility passed without ensuring the configured NF4/8-bit stack is usable. It validates a suite by presence of `cases` or `name`, rather than calling the strict suite loader. A config with omitted `release.require` crashes on `.safety_pass`; reproduced with the repository config. A missing source/suite may only warn while the output says ready.

Make preflight capability-based and fail on missing execution prerequisites. Publish a tested matrix with Python/OS/GPU/runtime versions, not model-size promises. Sources: [src/moro/hardware/detector.py:48](/Users/mac/Dev/MoroAI/moro/src/moro/hardware/detector.py:48), [src/moro/validation/engine.py:213](/Users/mac/Dev/MoroAI/moro/src/moro/validation/engine.py:213).

### TRN-07 — Medium: durable jobs, resume, and resource coordination are missing

CLI resume explicitly rejects use. Concurrent jobs have no common resource scheduler or lease. In-memory REST run/task dictionaries lose state on restart and diverge across workers. Filesystem discovery declares incomplete directories running and fills absent loss/VRAM with constants. There is no cross-worker cancellation protocol or reliable crash reconciliation.

Use persistent jobs with attempt IDs, process identity, heartbeat/lease expiry, explicit terminal states, checkpoint compatibility checks, GPU admission control and cancellation that terminates only the owned process group. Recovery in `MoroRuntimeOrchestrator` recursively retries connection/timeouts and batch-one OOM without a maximum; an isolated probe confirmed another retry is requested when the batch cannot shrink further. Source: [src/moro/runtime/orchestrator.py:326](/Users/mac/Dev/MoroAI/moro/src/moro/runtime/orchestrator.py:326).

## 7. Evaluation and release confidence

### EVAL-01 — High: invented evaluation results

The sync harness computes approximately 85% of case count without generation/scoring; missing suites still produce results. The async harness passes every case and records a fixed improvement of 0.15. An unknown REST run returned 90% pass rate from the cache fallback. These scores cannot be used for model selection, analytics, or release.

Replace every harness path with the real model-backed runner; return 404 for unknown runs and fail on missing suites. Explicit fixture results must carry `execution_kind=simulation` and cannot be promoted. Sources: [src/moro/eval/harness.py:132](/Users/mac/Dev/MoroAI/moro/src/moro/eval/harness.py:132), [src/moro/dashboard/api/evaluation.py:120](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/evaluation.py:120).

### EVAL-02 — Medium/high: robustness grading rewards stable wrong answers

**Observed:** a case that failed both the original and all perturbations received strict robustness 1.0 and grade **A (Excellent)** while raw correctness was zero. Outcome equality is stability, not understanding. Entity swaps and negation can change the correct answer, yet expectations are reused. Some adversarial examples therefore test an invalid oracle.

Report baseline accuracy, perturbed accuracy, conditional robustness on baseline-correct examples, and valid counterfactual labels separately. Require nonempty evaluable cases; do not turn missing measurements into robustness 1. Source: [src/moro/eval/robustness.py:40](/Users/mac/Dev/MoroAI/moro/src/moro/eval/robustness.py:40).

### EVAL-03 — Medium: deterministic assertions need stronger task semantics

Contains/regex/schema checks are useful and real. The strict loader rejects duplicate IDs, empty checks, malformed regex and schema syntax; the CLI gate rejects generation-only/stub evidence. However substring matches can pass negations or contradictory answers; schema validity does not establish factual correctness; no semantic LLM judge or Wasserstein implementation was found.

Add task-specific exact/structured accuracy, negative constraints, abstention/citation checks, domain experts' labels, multilingual slices, general-capability replay tests, safety misuse/prompt-injection cases and confidence intervals. Keep a sealed holdout separate from training and preference mining. A judge should be versioned and independently validated; its explanations should not be treated as ground truth.

### EVAL-04 — Medium/high: training/evaluation/export identities need stronger binding

The real runner hashes adapters and suites before and after evaluation, which protects useful invariants. Base weights, resolved revision, tokenizer/chat-template, generation config and runtime dependencies are not fully bound into the evaluation evidence. Unquantized evaluation of a quantized training setup also changes memory requirements. Final merged/GGUF artifacts are not reevaluated after transformation.

Capture resolved base commit and weight inventory, tokenizer/template hashes, evaluator implementation/version and decode config. Record transformation lineage and run post-merge/quantization/runtime smoke and quality tests. An adapter evaluation is evidence for that adapter/base configuration, not automatically every converted binary.

### EVAL-05 — Medium: comparative gates remain deliberately unimplemented

`eval compare` exists, but the release gate explicitly blocks configured `min_improvement`/`max_regression` because it cannot validate matching baseline-comparison evidence. This is safe failure, not a working comparative release gate. Define and persist paired comparison evidence with identical suite/decode setup and a clear per-slice regression policy. Source: [src/moro/export/gates.py:25](/Users/mac/Dev/MoroAI/moro/src/moro/export/gates.py:25).

### EVAL-06 — High: a real zero score is displayed as an 88% pass rate

**Observed through the in-process HTTP API.** A synthetic filesystem release with `metadata.json` recording `eval_results.pass_rate = 0.0` appeared in `/api/models/` with `eval_pass_rate = 0.88`. The fallback uses `pass_rate or 0.88`, replacing a measured failure with an invented success value. This is distinct from a missing-result placeholder: valid adverse evidence is overwritten in the presentation model.

**Fix:** preserve numeric zero; represent missing evidence as null with an explicit availability state. Do not infer a base model, LoRA rank or quantization from hardcoded defaults. Comparisons must require compatible measured evidence and must not announce a winner when data is missing. Acceptance tests must cover zero, null, unknown model, empty registry and a real measured score. Source: [src/moro/dashboard/api/models.py:86](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/models.py:86).

## 8. Export, provenance, deployment, and serving

### REL-01 — High: cryptographic integrity is not cryptographic authenticity

There are useful canonical config and artifact hashes, but no signature generation/verification, signing-key custody, issuer identity, revocation or trust roots. A user/process able to change both artifacts and the local database can rewrite evidence. JSON manifests are not automatically a standard SBOM, and “immutable” here generally means write-once-by-convention plus integrity checks, not immutable storage permissions or an external audit ledger.

Define the threat model, generate a versioned manifest covering data transforms, actual base weights, effective recipe, runtime/dependencies, eval evidence and all output bytes; optionally emit SPDX/CycloneDX and sign an attestation with a separately controlled key. Add offline verification. Do not invent an RSA signature string in documentation. Sources: [src/moro/core/hashing.py:49](/Users/mac/Dev/MoroAI/moro/src/moro/core/hashing.py:49), [src/moro/export/manifest.py:62](/Users/mac/Dev/MoroAI/moro/src/moro/export/manifest.py:62).

### REL-02 — Medium/high: export safety differs by format

Adapter export stages a copy, rejects overlapping paths and symlinks, and compares copied content with gate evidence. **Observed under controlled fault injection:** both `moro deploy` and `moro export --format ollama` exited successfully after the adapter changed immediately after the genuine release gate returned `passed`. Each published a package whose adapter hash differed from its accompanying passed gate hash. The helper verifies consistency during its own copy but does not bind that copy to the earlier gate. The identical injection into adapter-only export correctly failed. The probe reused structural test fixtures and mocked model inference; it tests real gate/packaging orchestration at a deterministic race boundary, not model quality or a naturally occurring race. Merged/GGUF paths lack equivalent whole-output staging, hashes, model cards, and artifact registration. They can overwrite an existing output directory and do not rerun the evaluation gate against final bytes.

Use a common immutable artifact transaction across formats, source-hash revalidation at the actual read/copy point, exclusive destination publication, and a completion marker only after manifest/evidence commit. The check-to-copy race was exercised using controlled mutation of synthetic fixture bytes; no live/private training artifact was modified. Source: [src/moro/cli/export.py:141](/Users/mac/Dev/MoroAI/moro/src/moro/cli/export.py:141), [src/moro/cli/deploy.py:34](/Users/mac/Dev/MoroAI/moro/src/moro/cli/deploy.py:34).

### REL-03 — Medium: merge/conversion correctness and resource budgets

Merge loads unquantized base weights, potentially using much more RAM than training; no memory/disk preflight exists. It resolves the adapter's base reference without explicitly forwarding its revision into `resolve_model_reference`; tokenizer comes from the base rather than necessarily the training adapter's saved tokenizer. Safe-merge validation and logit equivalence tests are missing.

GGUF direct conversion expects executables at fixed paths, chooses a PATH Python rather than the current environment, has no timeout, and accepts unrestricted quantization/project strings. With `f16`, intermediate and final paths coincide. A mocked successful converter/quantizer reproduced the helper deleting the returned final file; the actual llama.cpp binary was not available, so its in-place conversion behavior is not claimed.

Validate conversion enums, retain F16 directly when requested, preserve tokenizer/template and base identity, detect supported llama.cpp build layout/version, and verify output existence/size/hash plus inference equivalence. Sources: [src/moro/export/merge.py:15](/Users/mac/Dev/MoroAI/moro/src/moro/export/merge.py:15), [src/moro/export/gguf.py:138](/Users/mac/Dev/MoroAI/moro/src/moro/export/gguf.py:138).

### REL-04 — High: deployments and gateway can fabricate success

REST deployment accepted a nonexistent runtime and model, returning `running`. The SDK deployment manager sleeps and returns endpoint metadata. Ollama pull/delete/test endpoints swallow failures and may return simulated/deleted/success statuses. The delete call uses an HTTP client convenience signature that does not support its `json` keyword in the tested dependency family; exceptions are swallowed rather than surfaced.

The gateway returned HTTP 200 with a canned assistant answer for an unavailable model. It ignores system/earlier messages, requested temperature/max tokens/stream behavior, invents token counts 10/20/30, and uses timestamp-second IDs. Its name promises feedback capture, but it does not persist interactions into the flywheel. Model listing is static.

Implement real runtime adapters with explicit prepared/importing/ready/failed states, timeouts, upstream error propagation, conversational fidelity, real usage accounting, streaming/cancellation/backpressure and opt-in privacy-aware feedback capture. Do not deploy automatically merely because metadata was written. Sources: [src/moro/dashboard/api/deployment.py:91](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/api/deployment.py:91), [src/moro/dashboard/gateway.py:82](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/gateway.py:82).

### REL-05 — Medium: real CLI deployment is preparation-only

The CLI honestly documents preparing local artifacts and requiring manual Ollama import. Its portable package includes the adapter but not a compatible base model; a Hugging Face ID is not automatically an Ollama tag. No successful adapter import or model quality test was established during this audit. The running Ollama audit instance has no downloaded model.

A real one-command flow needs architecture compatibility checks, explicit base resolution, import subprocess/API success checks, tag collision policy, model digest verification, inference smoke tests, rollback and actual endpoint readiness. Add vLLM/Docker targets only when their workers exist; current CLI support is Ollama packaging.

## 9. Feedback learning and data poisoning

### FLY-01 — High: unread logs can be lost

**Observed:** three corrected logs in one session, ingestion batch size one; one log was ingested and one pair emitted, but all three logs became processed. Additional probes confirmed: one valid pair below a minimum of three was acknowledged with no dataset written; a cap of one consumed three source logs but emitted only one pair, while `pairs_by_type` still reported three. `run_cycle()` marks by session ID instead of the fetched log IDs. Capping pairs also marks discarded/unwritten sources processed. Below-minimum epochs consume logs instead of accumulating them for a later threshold.

**Fix:** claim individual logs transactionally with a lease, use exact log IDs, distinguish rejected/deferred/consumed states, only acknowledge durable outputs, carry capped items forward, and recover after interruption. Test same-session pagination, concurrent workers and crashes between file write/DB commit/ack. Sources: [src/moro/flywheel/orchestrator.py:133](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:133), [src/moro/flywheel/ingestors/sqlite_ingestor.py:118](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/ingestors/sqlite_ingestor.py:118).

### FLY-02 — High: extraction is not a trained alignment loop

There is an abstract trainer bridge and optional deployment gate, but normal CLI wiring does not instantiate a concrete DPO trainer. The convenience wrapper can report five pairs for every feedback file without parsing it. Epochs can be marked completed before training, and training/deployment exceptions are swallowed. Deployment is attempted when `auto_deploy OR require_eval_gate`, so requiring an eval gate is not cleanly separated from authorizing deployment. With an injected trainer that raises and a recording deployment hook, `auto_deploy=false` / `require_eval_gate=true` still invoked deployment, returned `deployed=true`, and left the DB epoch `completed` with null training losses. These hooks were test doubles; no real runtime deployment occurred.

Implement a true DPO job with parent model identity, reference-model choice, beta/loss settings, tokenizer-aware chosen/rejected formatting, train/holdout isolation, resumed state, real artifact output and independent promotion. Require `auto_deploy` to authorize deployment and a passed gate separately. Source: [src/moro/flywheel/orchestrator.py:166](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:166).

### FLY-03 — Medium/high: synthetic preference rules can teach bad behavior

A negative rating without supporting context generates a generic insufficient-evidence response as “chosen.” Positive feedback creates “rejected” by shortening the response, teaching a length preference rather than correctness. Human corrections are always lifted to the confidence floor; the configured minimum does not reject them. Confidence is a heuristic, not calibrated probability. Random pair IDs and no transaction-wide source uniqueness enable duplication on retries. The SQL ingest query can exclude rule-violation-only logs with no rating/correction despite the extractor supporting that signal.

Add deduplication by source+policy+content, contributor provenance/trust, minimum evidence and human review for synthetic pairs, contradiction checks, controlled sampling and rate limits against poisoning. Evaluate verbosity/refusal bias and regressions before adoption. Never equate feedback volume with improvement. Source: [src/moro/flywheel/extractors/deterministic_extractor.py:136](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/extractors/deterministic_extractor.py:136).

### FLY-04 — High: crash retries duplicate pairs; reused epoch IDs corrupt file/DB agreement

**Observed under controlled failure injection.** After pair records/dataset were written, a synthetic failure before acknowledgement left the source pending. Retrying produced two preference records for the same source log and two datasets. Random pair IDs do not provide source-level idempotency.

A separate probe reused a completed epoch ID after inserting new feedback. `_write_dataset()` truncated/replaced the existing JSONL first, then the DB epoch INSERT raised `IntegrityError`. The file contained the new answer while the stored preference row still contained the old answer. This is a reproducible mismatch between the supposedly recorded dataset and its database evidence; the new log remained pending.

**Fix:** reserve epoch IDs before writing, prohibit overwrite, assign deterministic source/policy/content identities, claim logs with leases, atomically publish a staged dataset, and reconcile filesystem publication with DB state. Training/deployment should not begin until a verifiable dataset manifest is committed. A retry of the same operation must return the original result or resume the same attempt. Test crash boundaries at reservation, staging, publication, commit and acknowledgement. Sources: [src/moro/flywheel/orchestrator.py:183](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:183), [src/moro/flywheel/orchestrator.py:200](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:200).

## 10. State, analytics, UX, and maintainability

### State and consistency

The CLI uses `.moro/db.sqlite`; other components use `state.db`, `state_graph.db`, a separate registry store, `analytics.db`, `data/production_logs.db`, and `.moro/production.db`. The latter two split webhook/CLI feedback from the convenience dashboard flywheel. Run discovery expects `recipe.json`/`results.json`, while real CLI training writes `config.json`/`training_report.json`. A completed CLI run can therefore be displayed as running with guessed metrics.

The CLI database now has an additive version-1 migration; the previous report's claim of no migration is outdated. Other schemas still need explicit versioned migrations. Several cross-table lineage IDs lack foreign keys. Project lookup uses mutable project name. `StateGraphManager.get_ancestors()` has no visited set/depth guard and can loop forever on a cycle. Node replacement and generic payload updates do not make an append-only audit history.

Consolidate authoritative identities and repositories, make analytics a derived projection, provide migrations/backups/restore checks, enforce state transitions and foreign keys, and implement an outbox/reconciliation process across filesystem publication and database commits. Sources: [src/moro/storage/db.py:8](/Users/mac/Dev/MoroAI/moro/src/moro/storage/db.py:8), [src/moro/storage/state_graph.py:107](/Users/mac/Dev/MoroAI/moro/src/moro/storage/state_graph.py:107), [src/moro/flywheel/orchestrator.py:253](/Users/mac/Dev/MoroAI/moro/src/moro/flywheel/orchestrator.py:253).

### Analytics accuracy

Useful tracking and visualization abstractions exist. However loss-curve data uses a union of step labels with each experiment's unaligned raw values: runs logged at different steps can be plotted at the wrong x-coordinate. Use `{x: step, y: value}` points or reindex to the common grid. Correlation code drops null target/parameter values independently and slices arrays, potentially pairing different experiments. Join complete pairs by experiment ID before calculating correlations. Duplicate heatmap coordinates overwrite instead of aggregate. Recommendations from small observational runs are not causal evidence.

Persist real callbacks from the training backend and schema-check metrics; distinguish estimated/observed/missing values. Do not report GPU capacity as peak usage. Sources: [src/moro/analytics/visualizations.py:56](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/visualizations.py:56), [src/moro/analytics/tracker.py:580](/Users/mac/Dev/MoroAI/moro/src/moro/analytics/tracker.py:580).

### Dashboard reliability and usability

The source HTML serves successfully. It contains static baseline/DPO chart arrays, seeded “recent” logs, optimistic online defaults, and fallback models/metrics that obscure failures. The frontend polls overview every eight seconds; the advertised 120 messages/second SSE path is not present. Backend WebSockets do not establish that the frontend uses live training telemetry.

Dataset upload has no meaningful max-file limit; compilation errors can be printed and swallowed with no job state. The compile button also triggers `moro data build`, which reads the configured source rather than necessarily the newly uploaded dataset. Terminal shortcuts can run a long training command behind a 15-second request timeout; timeout is not a robust child-process cancellation mechanism. The Ollama shortcut uses `docker exec`, which the terminal prefix filter itself rejects. The eval comparison shortcut omits required inputs. Terminal control strings are double-escaped in the source and need real keyboard/browser verification.

Use explicit empty/unavailable/error/loading states, job IDs, durable progress, accessible labels/focus/error announcements, confirmation for genuinely destructive user actions, pagination and useful cancellation. Remove unrelated hardcoded local-service links. Browser rendering/accessibility and keyboard flows were code-reviewed, not fully browser-tested; they remain acceptance requirements. Source: [src/moro/dashboard/templates/mission_control.html:1600](/Users/mac/Dev/MoroAI/moro/src/moro/dashboard/templates/mission_control.html:1600).

### Configuration and API design

The core strict Pydantic config and split-ratio validation are meaningful strengths. REST training/config routes use separate permissive shapes; `PUT /api/system/config` writes arbitrary YAML without validating `MoroConfig`, backup, atomic replace, or revision precondition. An HTTP probe saved a negative batch size and unknown config field with status 200, replacing the previous file; a subsequent strict CLI load rejected it. The system config reader imports `load_config` from the wrong module and falls back to raw YAML, masking validation failures. Duplicate routes/prefixes, multiple dashboards, mixed async/sync APIs, and success-on-exception fallbacks increase maintenance cost.

Use shared request/domain schemas, one config service, explicit versioning, compare-and-swap updates, structured errors, and stable IDs. Avoid str/dict hybrid return values for runs and list/dict hybrid service status objects when ordinary typed models can express the contract. Add type checking to CI after defining these boundaries.

## 11. Development environments and distribution

### What was started

All service processes used the **synthetic audit project**, `/tmp/moro-audit-20261002/dev`, so probes did not pollute the repository's real training/feedback state.

| Environment / service | Address or artifact | State |
|---|---|---|
| Mission Control via `moro dashboard --gateway` | `http://127.0.0.1:8501` | Running; source HTML and APIs respond |
| Alternate `moro ui` entry point | `http://127.0.0.1:8765` | Running; same FastAPI app, compatible with service-status default |
| Feedback gateway | `http://127.0.0.1:8000/health` | Running; inference success is not established by health |
| Webhook | `http://127.0.0.1:8001/health` | Running via actual standard-library server fallback |
| Ollama | `http://127.0.0.1:11434/api/tags` | Running in dedicated loopback-published audit container; no pretrained models downloaded |
| Flywheel loop | `/tmp/moro-audit-20261002/flywheel-daemon.log` | Running hourly on synthetic project; extraction only |
| Linux Python 3.11 CPU stack | `moro-audit-20261002-cpu-dev` container | Running and reusable; all 18 integration tests passed |
| Repository Docker Compose stack | Docker build log | Blocked by repository build/startup defects; not claimed healthy |

These running services retain the audited vulnerabilities. Use only synthetic data while reviewing; do not expose them to a LAN or the internet. Loopback is a containment measure, not the security fix. The runbook records PIDs, stop commands and restart commands. Existing unrelated containers were left alone.

### Confirmed packaging/launch failures

1. **Dockerfile installs before source copy.** `pip install -e '.[train,dashboard]'` runs after only `pyproject.toml`/README have been copied. The actual Docker build and separate layer reproduction failed with `'src' does not exist or is not a directory`. LICENSE is also absent at this stage, and `dashboard` is not a declared extra.
2. **Wrong webhook server target.** Compose and service orchestration invoke `moro.flywheel.webhook.receiver:webhook_app`; no such ASGI app exists. Direct uvicorn startup exits with “Attribute webhook_app not found.” The working fallback is `moro flywheel serve` or `start_webhook_receiver()`.
3. **Container topology mismatch.** Dashboard connectors hardcode `127.0.0.1:11434`; inside a dashboard container that is not the separate Ollama container. Gateway uses `OLLAMA_BASE_URL`, but dashboard routes do not consistently do so.
4. **Incomplete volume/config layout.** Images do not copy `moro.yaml`; Compose does not mount it. Dashboard/gateway/flywheel volumes differ, and flywheel lacks releases/evaluation mounts for any actual downstream lifecycle. `MORO_PROJECT_ROOT` is declared but root helpers primarily use current directory/project discovery.
5. **Service “all” is incomplete.** Start-all lists dashboard/Ollama/webhook but omits gateway. Container name assumptions differ: `moro-ollama` versus Compose's `moroai-ollama`. Port listeners are sometimes treated as successful starts without service identity verification. Restart counters reset in `start_service`, undermining the intended maximum; PID files are not protected against reuse.
6. **Default port publishing is broad.** Compose uses `11434:11434`, etc., rather than loopback-specific bindings. Docker documents that explicit localhost publishing restricts access to the host; use it for local development. [Docker port-publishing documentation](https://docs.docker.com/engine/network/port-publishing/).
7. **Wheel omits runtime assets.** The built wheel contains no dashboard HTML and no safety-hook script. Editable-source tests miss this. Missing-template serving returns HTTP 200 with an error heading, which also weakens readiness checks.
8. **No reproducible complete dependency lock.** Top-level train pins coexist with broad runtime/dev dependencies, remote frontend version ranges and a latest Ollama image. Separate reference locks per CPU/CUDA/platform and pin serving/converter image digests.

A corrected development topology should have a lightweight CPU-only web image, an independently selected training worker image/profile, locally bundled frontend assets, mounted validated project config, one authoritative data root, loopback ports, configured service URLs, readiness probes and non-root container users. Do not install the full training stack in every web component merely to serve a dashboard.

## 12. Tests, CI, documentation, and release discipline

The suite is useful for core regressions but several tests verify simulated outputs rather than the advertised invariants. Dashboard tests assert status fields and nonempty default models; they do not require trained tensors, actual runtime import, authentication rejection, or fabricated-result rejection. The 10,000-row compiler benchmark uses the copy/count compiler, not the actual cleaning/scoring pipeline. VRAM “accuracy” tests compare three hardcoded expectations matched by special branches.

CI runs core tests on Python 3.10–3.12 and a separate pinned Linux CPU integration job. This is a strength. However the tag publication workflow has its own core-only test job and can publish independently of the training job. PyPI publishing uses `continue-on-error: true`, allowing a GitHub release after a failed package publication. Mutable action tags, absent dependency/secret scans, no built-wheel asset smoke, no Docker smoke, and no browser-offline tests leave important gaps. Pre-commit configuration is not proof that CI enforces the hooks.

**Required test layers:**

- Real service-level security tests: unauthenticated rejection, origin/Host restrictions, traversal/symlinks, SQL identifier rejection, body limits, read-only users, Docker scoping.
- Semantic contract tests: missing resources fail; simulation cannot become a real release; jobs cannot complete without valid artifacts; upstream failure remains failure.
- Data invariants: mutually exclusive group splits, privacy policy enforcement, deterministic content/provenance, glossary invalidation, tokenizer truncation safety.
- Real tiny-model tests: loss/weights/checkpoint/reload, trainer option propagation, effective recovery config and actual callbacks. Add GPU jobs for CUDA quantization and genuine OOM recovery.
- Release tests: same checked bytes are packaged, transformed artifacts are inventoried/evaluated, invalid promotions preserve production, no partial published releases.
- Distribution tests: install wheel outside source checkout, render dashboard assets offline, run hooks, build/start container profiles, verify health and model error paths.
- Feedback durability tests: exactly-once source accounting, no same-session over-ack, minimum/cap carryover, crash/retry/concurrency, poisoning and privacy filters.

README SDK imports include nonexistent `MoroProject` and `moro.training.engine.TrainingEngine`, and use compiler/recipe method signatures different from the actual classes. Its documented CPU test path is also wrong (`tests/test_training_cpu.py` versus `tests/integration/test_training_cpu.py`). Older engineering-status documents have stale test counts and contradictory milestones. Generate CLI examples from executable documentation tests and publish capability labels: implemented/tested, experimental, planned.

## 13. Prior-audit findings that are now fixed

Do not spend time reimplementing these without identifying a regression:

- Versioned canonical config hashing and legacy matching exist; current hashing tests pass.
- Core config rejects unknown fields; split-ratio checks and minimum split sizes exist.
- CLI dataset snapshots are separate version directories with hashes; `--force`, bounded limits, and rejection-reason artifacts exist.
- CLI runs bind dataset version and configured output directory; saved input/config evidence exists.
- CLI export rejects unsafe deployment tags/symlinks and incomplete runs; latest completed selection exists.
- Adapter export has real artifacts/manifests and DB registration; portable Ollama adapter copies exist.
- Runs list/show/compare, eval compare, recipe apply, merged/GGUF helpers and data inspect exist.
- CLI release gates reject stale/stub/generation-only evidence and check configured safety cases.
- An additive CLI database migration exists; project gitignore templates protect private inputs more broadly.

These fixes deserve preservation. The urgent task is to make alternative entry points obey their invariants.

## 14. Prioritized remediation with acceptance criteria

| Priority | Work package | Definition of done |
|---|---|---|
| P0 | Remove exposed command execution; add application authentication | Both terminal routes removed/replaced; unauthorized HTTP/WS cannot read private data or mutate state; no interpreter escape |
| P0 | Constrain uploads and SQL identifiers | Traversal/absolute/symlink/collision tests pass; size limits enforced; injection probe rejected |
| P0 | Eliminate false completion and fake evidence | Missing model/data/suite/runtime causes failure; simulation explicitly labeled and ineligible for release; no fabricated metrics in normal UI |
| P1 | Unify compiler/training/eval/release services | CLI and API produce equivalent evidence/artifacts and share one policy path |
| P1 | Repair privacy and network boundaries | Explicit enforceable privacy action; full PEM redaction; offline schema registry; bundled UI; socket-denial tests across supported offline workflows |
| P1 | Repair feedback durability and trust | Only consumed log IDs acknowledged; capped/deferred items retained; sender identity/idempotency and transactional retries |
| P1 | Repair package/container launch | Wheel contains HTML/hook assets; clean install works outside checkout; Docker builds; webhook target/URLs/config mounts correct |
| P1 | Update and lock training dependencies | Reviewed advisory inventory and compatible lock; real CPU/CUDA regression evidence; trusted tensor loading policy |
| P1 | Fix OOM lifecycle and provenance | Bounded attempts; old allocations released; effective config recorded; recovery/resume semantics independently verified |
| P1 | Uniform release and promotion governance | Missing/failed/stale eval blocks all interfaces; invalid promotion leaves current production intact; final output hashes verified |
| P2 | Correct science, analytics and benchmarks | One honest estimator; independent calibration; correct split/robustness oracles; aligned charts/correlations; no “unknown = good” defaults |
| P2 | Durable jobs and observability | Worker leases, cancellation, restart reconciliation, real per-step telemetry, structured masked logs and truthful readiness |
| P2 | Documentation and SDK contract | Every quickstart executes against built distributions; commands/ports/imports and capability claims match shipped code |

Suggested execution order: contain web privileges → make success truthful → unify application services → repair privacy/data/feedback invariants → distribution and dependency remediation → real hardware/runtime acceptance → advanced features. Adding more UI controls before these fixes would expand the untrusted surface and amplify misleading results.

## 15. Future features worth adding after correctness is established

These are product suggestions, not claims that every project must implement them immediately.

1. **A credible local adaptation workflow:** import → privacy review → versioned group split → capability-aware recipe → real job → comparison → gated package → verified runtime import. Make this path excellent before multi-runtime breadth.
2. **Data stewardship:** source license/consent/provenance, supported languages, document-level access, review queues, drift/contradiction reports, retention/deletion and lineage-aware rebuilds. Data quality should be inspectable, not compressed into a single magic score.
3. **Training controls:** assistant-only masking, explicit replay corpus and implemented mixing, configurable objectives, checkpoint resume, scheduler/optimizer controls, deterministic attempt records and resource scheduling. Add MLX/ROCm/multi-GPU only with dedicated backends and measured support.
4. **Evaluation depth:** task-specific metrics, versioned reference answers, calibrated local judge, correct counterfactual tests, forgetting/robustness/privacy probes and uncertainty intervals. Measure memorization and leakage empirically; PII preprocessing alone does not guarantee a model cannot leak.
5. **Production serving:** actual runtime adapters, request identity, conversation fidelity, streaming and cancellation, context budgets, prompt/template provenance, quotas, model reload/readiness, canary rollout and rollback. Separate inference availability from training-job availability.
6. **Governance:** standard artifact inventories/attestations, offline verifier, actor identity, protected signing keys, approvals according to the team's policy, immutable audit export and disaster recovery tests. Hashes are building blocks, not compliance certification.
7. **Controlled learning:** audited preference sources, human review where appropriate, poisoning defenses, real DPO training, held-out quality/regression/safety tests and explicit authorization before automated promotion.
8. **Operator experience:** local assets, accessible keyboard workflows, empty/error states, source-linked dataset previews, accurate progress and cost/memory estimates, reusable project profiles and a single consistent port/start command.

**Production-readiness decision:** permit development with synthetic/non-sensitive data under containment. Do not approve shared-network deployment, private enterprise data handling, automatic promotion, or published zero-OOM/air-gap/signed-certification guarantees on this evidence. Reassess after the P0/P1 acceptance tests pass and real hardware/runtime artifacts are independently verified.

## 16. Concrete remediation design

The [remediation blueprint](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/REMEDIATION_BLUEPRINT.md) specifies shared service boundaries, permission rules, job states, crash-safe publication, offline scope, scientific validation, a feature acceptance matrix and release gates for the remediation itself. It is a proposed implementation design, not shipped behavior.

## Evidence index

See the [evidence index](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/evidence/README.md) for baseline tests, coverage, scanner outputs, HTTP/function probes, CLI checks, source inventory, OpenAPI, packaging/build logs and CPU integration results. See the [module inventory](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/MODULE_INVENTORY.md) for every Python module and [runbook](/Users/mac/Dev/MoroAI/moro/docs/audits/2026-10-02/RUNBOOK.md) for service state and shutdown/restart instructions. Generated model/test files and dependency environments remain under `/tmp/moro-audit-20261002`, outside project source.
