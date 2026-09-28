# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

The MoroAI team takes security vulnerabilities seriously. We appreciate your efforts to responsibly disclose your findings.

If you believe you have discovered a vulnerability in MoroAI:

1. **Do not create a public issue.**
2. Send an email to **security@moroai.dev** (or **team@moroai.dev**) with the subject `[SECURITY VULNERABILITY] <Summary>`.
3. Include detailed steps to reproduce the issue, along with affected versions and any proof-of-concept scripts.
4. We will acknowledge receipt within 48 hours and provide updates as the issue is investigated and patched.

## Local Privacy & Data Boundary

MoroAI is designed from the ground up as a **local-first** platform:
- Data ingested by `moro import` and `moro data build` stays local on disk.
- In `privacy_mode: local_only`, network requests to remote model registries or telemetry endpoints are blocked.
- PII redaction rules protect sensitive identifiers from entering fine-tuning datasets.
