# P0-2 evidence — October 20, 2026

These are snapshots from the local uncommitted `codex/audit-remediation` branch. The synthetic project and raw logs persist under `.moro/dev/2026-10-19/`; the date in that directory records when this continuation began. No token, cookie or customer data is intentionally included.

## Tests and runtime

| Artifact | Result / meaning |
|---|---|
| [Focused acceptance suite](acceptance-tests.log) | 73 passed in the two supplied P0-2 test-file locations. |
| [Full native suite](core-tests.log) | 555 passed, 4 skipped, 3 warnings; Python 3.14.6. |
| [Installed-wheel suite](linux-wheel-tests.log) | 559 passed, 15 warnings; Linux Python 3.11, source `PYTHONPATH` unset. Includes four real offline CPU lifecycle cases. |
| [P0-2 HTTP checks](live-p02.json), [summary](live-p02.log) | 63 checks across three dashboards. Exact container images/ports recorded; raw upload files cleaned up and preexisting raw file names preserved. |
| [Broader HTTP checks](services-smoke.json), [summary](services-smoke.log) | 91 checks across dashboard/auth/operation/gateway/webhook/feedback paths; seven owned containers running. |
| [Browser screenshot](browser-upload-rejection.png) | Actual malformed JSONL selected through the browser file chooser; readable server error after fixing Dropzone initialization order. This is not an exhaustive browser test suite. |
| [Ruff](ruff.log), [format](format.log), [JavaScript syntax](javascript-syntax.log), [diff whitespace](diff-check.log) | Static checks passed. Empty syntax/whitespace logs mean no diagnostics. |
| [Shell scan](shell-check.json) | No literal `shell=True` keywords in source AST; not a complete command-injection analysis. |

The four CPU cases use a tiny local model and test-only release thresholds. They verify execution mechanics, not model quality or GPU recovery. Test deprecation/trainer warnings remain visible in raw logs. The [targeted UI suite](ui-tests.log) is an intermediate check; final full-suite logs and browser capture take precedence.

## Packaging and dependency evidence

- [Distribution build](build.log) and [distribution hashes](distribution-hashes.json): final wheel/sdist reside in `.moro/dev/2026-10-19/p0-2/dist/`.
- [Docker build](docker-build.log), [Compose startup](compose-start.log), [Compose override](compose.yml): final project image tag `moro-remediation:20261019-p02`. Exact final image identity is in the live-check artifacts.
- [Installed-wheel source hashes](installed-wheel.json) and [image source hashes](image-source-hashes.json): upload module, SQL mapping module and dashboard template resolve to packaged paths and match current source bytes.
- [Source inventory](source-inventory.json): all Python modules with SHA-256, line counts and top-level symbols. This is an inventory, not a claim of exhaustive line-by-line review.
- [Dependency consistency](linux-pip-check.log): no broken reference-environment requirements.
- [Final web-image requirements](web-image-requirements.txt), [advisory scan](web-audit.json), [scanner log](web-audit.log): 32 external Python packages, zero known matches, zero skipped entries. The local Moro distribution is excluded and is tested separately. The scan uses the final image's actual resolved package versions.

Web dependencies changed during rebuilds, so this pass refreshed the web scan rather than reusing a prior result. The earlier [training scan](../../2026-10-19/evidence/training-audit-final.json) is historical; this pass reinstalled application code with `--no-deps` and does not claim a new training-stack advisory scan. OS/browser/CUDA scans, full locks and signing remain open. Absence of advisory matches is not proof that no vulnerabilities exist.

## Reproduce

See the [runbook](../RUNBOOK.md). [P0-2 probe script](verify_p02.py.txt) and [broader service script](verify_services.py.txt) read the private project token locally without printing it. The P0-2 script creates synthetic immutable compiled versions and removes its own raw uploads; the broader script adds/extracts synthetic feedback. Running them is a mutation of the named scratch project, not a read-only check. New results go to `.moro/dev/2026-10-19/p0-2/`, preserving this archive.

The [SHA256SUMS](SHA256SUMS) manifest covers the evidence files except itself. These hashes provide local integrity comparison, not a trusted signature or reproducible-build attestation.
