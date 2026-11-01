# Remediation evidence index

Work began October 3; final implementation/runtime verification October 5, 2026. Baseline commit `bac72593964c5e7218b009824f7146998b6cdfaa`; local branch `codex/audit-remediation`. Evidence concerns the uncommitted working tree. Credentials/cookies are deliberately omitted. Original October 2 audit evidence remains separate.

| File | Meaning |
|---|---|
| [core-final-pass.log](core-final-pass.log) | Final native complete suite: 451 passed, 3 skipped. |
| [linux-final-pass.log](linux-final-pass.log) | Final Linux complete suite with real CPU integration: 454 passed. |
| [dataset-api-final.log](dataset-api-final.log) | 26 dashboard/API regression tests after compiled-preview fix. |
| [packaged-cpu-training.log](packaged-cpu-training.log) | Three real CPU lifecycle cases using installed final wheel. |
| [services-smoke.json](services-smoke.json) | 47 live HTTP checks plus exact image IDs, container users, health and loopback bindings. |
| [verify_services.py.txt](verify_services.py.txt) | Reproduction script; reads scratch token without recording it; inserts only synthetic feedback. Run with the native virtualenv after copying to a `.py` path. |
| [wheel-smoke.json](wheel-smoke.json) | Site-packages import path, assets, hook and CLI smoke outside checkout. |
| [wheel-final-build.log](wheel-final-build.log) | Final source/wheel build. |
| [distribution-hashes.json](distribution-hashes.json) | SHA-256 of final scratch distributions. Integrity inventory, not a signature. |
| [docker-verified-build.log](docker-verified-build.log) | Final Docker image build. |
| [compose-start.log](compose-start.log) | Final Compose recreation using rebuilt image. |
| [compose-verify.yml](compose-verify.yml) | Port-isolated Compose override used for verification. |
| [candidate-pip-check.log](candidate-pip-check.log) | Final installed Linux reference-stack dependency consistency. |
| [candidate-audit-final.json](candidate-audit-final.json) | Recorded 92-entry Python advisory scan: zero matches; CPU Torch version skipped by PyPI lookup. |
| [candidate-torch-audit.json](candidate-torch-audit.json) | Separate normalized Torch 2.14.1 advisory scan: zero matches, no skipped entry. |
| [candidate-torch.txt](candidate-torch.txt) | Normalized Torch scan input. |
| [candidate-audit-final.log](candidate-audit-final.log), [candidate-torch-audit.log](candidate-torch-audit.log) | Scanner command output. Absence of known matches is not absence of vulnerabilities. |
| [ruff-final.log](ruff-final.log), [format-final.log](format-final.log) | Lint/format results. |
| [current-source-inventory.json](current-source-inventory.json) | Current Python module hashes, line counts and top-level symbols. |
| [git-diff-stat.txt](git-diff-stat.txt), [working-tree-status.txt](working-tree-status.txt) | Tracked diff summary and untracked paths, including preserved original audit. |
| [SHA256SUMS](SHA256SUMS) | Hash inventory of evidence files, excluding itself. |

Earlier `cpu-training-candidate.txt` and `torch-audit.json` are retained intermediate evidence. Prefer final named logs above for current results. Warning/deprecation text and transient scratch paths are intentionally retained in raw logs. No full current coverage percentage is asserted; the original coverage report belongs to the original audit.

Read [validation](../VALIDATION.md) before interpreting CPU, gate, browser or advisory results. The [report](../REPORT.md) explains fixes and [ledger](../STATUS.md) identifies unresolved acceptance criteria.
