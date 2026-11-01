# October 19 evidence index

Evidence comes from the local `codex/audit-remediation` working tree, based on `bac72593964c5e7218b009824f7146998b6cdfaa`. It is a snapshot of an uncommitted workspace. No credentials, project token file, browser cookies or customer data are intentionally included. Runtime verification uses synthetic data.

## Final acceptance evidence

| Artifact | Scope / result |
|---|---|
| [Native suite](core-tests.log) | Python 3.14.6: 482 passed, 4 training-stack skips, 3 warnings. |
| [Installed-wheel suite](linux-wheel-tests.log) | Linux Python 3.11: 486 passed, 15 warnings, after the aiohttp patch and final wheel installation. Includes four real offline CPU training/reload/evaluation/release-mechanics cases. |
| [Wheel provenance](installed-wheel.json) | Operations and training imports resolve to site-packages; HTML/Alpine packaged; aiohttp 3.14.4 and Torch 2.14.1+cpu. |
| [Live service checks](services-smoke.json) | Timestamped 91 HTTP checks and seven owned container states, exact image IDs, users and port bindings. |
| [Smoke script](verify_services.py.txt) | Reads the private local token without recording it; checks live authentication, operation routes, compile/preview, webhook replay and feedback consistency. Each run adds synthetic feedback and compiled versions. |
| [Lint](ruff.log), [format](format.log), [JavaScript syntax](javascript-syntax.log) | Ruff passes; 220 Python files formatted; JavaScript syntax check succeeds (empty log means no diagnostic, not independent proof of runtime behavior). |
| [Shell scan](shell-check.json) | AST check for literal `shell=True`; this limited check is not a whole-program injection or taint analysis. |
| [Wheel/sdist build](build.log), [Docker build](docker-build.log) | Final distribution and web image builds completed. |
| [Distribution hashes](distribution-hashes.json) | SHA-256 of the final local wheel/sdist in `.moro/dev/2026-10-19/dist/`; hashes detect changes, not trusted publisher identity. |
| [Source inventory](source-inventory.json) | 138 Python modules with hashes, line counts and top-level symbols. Inventory is not proof of exhaustive review coverage. |
| [Dependency consistency](linux-pip-check.log) | Current Linux reference environment reports no broken requirements. |

The [source-mounted Linux suite](linux-tests.log) and [targeted UI suite](ui-tests.log) are intermediate checks. The final installed-wheel suite above is authoritative for the patched reference environment. Test warnings are retained. Tiny-model release tests deliberately use permissive test gates; their success does not establish model quality or production gate thresholds.

## Dependency scan scope

- [Before remediation](training-audit.json), [scanner log](training-audit.log): 92 entries, three aiohttp 3.14.3 matches, one skipped Torch local-version entry.
- [Final training scan](training-audit-final.json), [log](training-audit-final.log), [exact lookup input](training-normalized-requirements.txt): 91 external packages, zero known matches, zero skipped entries. The local Moro distribution is excluded. Torch's `+cpu` suffix is removed only for advisory lookup; the installed runtime remains 2.14.1+cpu.
- [Web-image scan](web-audit.json), [log](web-audit.log), [exact input](web-image-requirements.txt): 32 external Python packages, zero known matches, zero skipped entries. The final rebuild resolved FastAPI 0.149.0 instead of 0.147.0. This scan was refreshed against the final image freeze; the earlier scan/input/log are retained with the `intermediate-` prefix. This observed drift demonstrates that the image is not dependency-locked.

These are advisory database matches at scan time. They do not cover OS libraries, all browser assets, GPU binaries, future disclosures or malicious model files. The inputs are complete resolved package lists for these scopes, but are not hash-locked reproducible environment specifications. Advisory sources are linked in the [report](../REPORT.md).

## Browser evidence

- [Authenticated real operations](browser-operations.png): compilation and immutable dataset preview.
- [Missing evaluation](browser-missing-evaluation.png): explicit missing-record state.
- [Recorded feedback](browser-feedback.png): persisted synthetic pairs and provenance.

Captures document selected visible states. The latest smoke run adds more synthetic records, so current totals may exceed screenshot totals. The UI is not a substitute for the raw acceptance tests and live service responses.

## Runtime and reproduction

[Compose override](compose.yml), [Compose startup](compose-start.log) and [feedback-loop output](feedback-service.log) accompany the [runbook](../RUNBOOK.md), which includes native/Compose commands, environment limitations and scoped shutdown instructions. All published service ports bind loopback. The extraction loop is not a training worker.

Run the saved smoke script from the repository with `.venv/bin/python docs/remediation/2026-10-19/evidence/verify_services.py.txt`. It intentionally targets the persistent synthetic project at the absolute path recorded in the script and writes fresh results to `.moro/dev/2026-10-19/services-smoke.json`; it does not overwrite this archived result.

For advisory scan reproduction, use `pip-audit --no-deps --disable-pip -r INPUT -f json -o OUTPUT` with the retained requirements file and a separate output path. A future scan can legitimately produce different findings.

[SHA256SUMS](SHA256SUMS) covers every file in this evidence directory except the manifest itself. It provides integrity comparison within this local snapshot, not a signature or attestation.
