# Evaluation requirements for release

Adapter export, Ollama export, and deployment preparation check both the saved
run policy and the current project policy. A current policy cannot silently
weaken the policy recorded at training time. With no active requirements, export
is explicitly recorded as `not_required`, not an evaluated release.

Example current configuration:

```yaml
eval:
  suites:
    - path: ./eval/support-golden-v1.yaml
release:
  require:
    eval_suite: support-golden-v1
    min_pass_rate: 0.9
    safety_pass: true
```

`eval_suite` selects the suite's internal name from `eval.suites`. If omitted,
all configured suites are required whenever a threshold or safety requirement is
active. Suite names must be unique. The default required pass rate is 1.0;
`min_pass_rate` can explicitly set a threshold from 0 to 1. Every required suite
must meet it. Thresholds use case pass/fail, not the average partial-check score.

`safety_pass` requires at least one evaluated case tagged `safety` among the
selected suites, and every such case must pass. This is an authored test policy,
not a claim of comprehensive model safety. The generated project currently asks
for safety checks but its example support suite has none: users must design
appropriate checks before that policy can pass. No synthetic safety evidence is
generated automatically.

## Evidence requirements

Run the full suite with `moro eval run <suite> --run-id <run>` before exporting.
The newest result for each required run/suite must:

- Be a model-backed execution with recognized, nonempty checks on every case.
- Cover every case in the current suite, in order.
- Match the current adapter directory fingerprint and exact suite file hash.
- Have consistent run/result identities, case counts, and pass rate.

Old results without provenance, explicit stub responses, generation-only cases,
partial samples, changed artifacts, and changed suites block release. A newer
failing or invalid result is not bypassed in favor of an older passing result.
Rerun evaluation when evidence is stale. Checks are local; they do not download
models. JSON Schema evaluation requires the optional `moroai[eval]` extra and
validates the schema before loading the model.

The adapter manifest includes the release decision, policy snapshots, adapter
fingerprint, and accepted evaluation IDs/suite hashes. Ollama preparation writes
the same decision to `release_gate.json`. Copied adapter contents are checked
against the accepted fingerprint before the manifest is written.

## Deliberate limitations

`min_improvement` and `max_regression` currently block release with an explicit
unsupported-comparison error: paired baseline evidence is not implemented yet.
They are never silently ignored.

The local database is trusted, not signed or resistant to deliberate tampering.
Adapter hashing binds files including tokenizer metadata, but does not pin all
external base-model dependencies. Ollama preparation still references the live
adapter location and is not a self-contained immutable deployment package.
Concurrent modification, crash recovery, and whole-release transactional
publication require further work. Threshold checks do not establish statistical
significance, real-world safety, or useful task quality beyond the authored suite.
