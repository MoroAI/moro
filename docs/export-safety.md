# Adapter export safety

Adapter export requires a fresh destination: `<out>/adapter` must not already
exist, even as a dangling symbolic link. Choose a new `--out` directory for each
export. Existing exports are never automatically deleted or replaced.

The exporter resolves paths before checking whether source and destination
overlap. Identical paths, nested paths, and symbolic-link aliases that overlap
are rejected before copying. Symbolic links inside the source adapter are also
rejected; materialize those files before exporting.

Files are copied into a temporary directory within the output directory, then
published with a directory rename. A failed copy does not expose a partial
`adapter` directory, and temporary staging files are cleaned up on ordinary
exceptions. The source adapter remains unchanged.

## Run eligibility

Both `moro export` formats and `moro deploy --target ollama` require a completed
run belonging to the current recorded project. With no run ID, selection uses the
latest completed run; a newer failed run does not hide it. An invalid selected
run is rejected rather than silently falling back to an older artifact.

The saved `config.json` must validate and match the run's recorded configuration
hash, model name, and quantization. Exported model identity comes from this
snapshot, not the current `moro.yaml`. Adapter manifests also record the requested
model revision; a branch name such as `main` is not a resolved immutable revision.
Historical runs without this evidence are blocked, with no invented replacement.

The adapter must have readable LoRA metadata with a positive integer rank and
nonempty `adapter_model.safetensors` or `adapter_model.bin` weights. Linked adapter
files are rejected. These are structural checks for the current unsharded training
output, not tensor deserialization, base-model compatibility checks, or proof of
quality. No model download or GPU is needed for these checks. Configuration hashing
uses the saved JSON fields without inserting new schema defaults; broader schema
evolution will still require a migration strategy.

Unsupported deployment targets, including the GGUF placeholder, now return failure.

These guarantees do not cover the entire release lifecycle.
Manifest/model-card publication, concurrent writers, abrupt process termination,
source modification during export, and tensor validity still need separate handling.
Evaluation requirements are now enforced as described in [release gates](release-gates.md).
Export success alone does not establish general model quality.

Regression coverage is in `tests/test_export_safety.py`, including overlapping
paths, existing destinations, links, simulated copy failure, and independent copies.
