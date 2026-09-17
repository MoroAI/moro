# Recipe planning

`moro recipe suggest` reads the nearest project's `moro.yaml`. Outside a project it uses hardware presets. `--config PATH` selects another configuration; an invalid explicit config is an error. `--model` and `--max-seq-length` take precedence over project settings.

```bash
moro recipe suggest
moro recipe suggest --config ./moro.yaml --model private/model-70B --json
moro recipe suggest --yaml-patch
```

`--yaml-patch` prints a partial configuration for manual review and merging. It does not write files or apply settings. Do not replace the entire `moro.yaml` with this partial output. `--json` includes the same patch plus the rationale, parameter-size source, memory breakdown, and fit status.

## Estimates and decisions

The chosen model is preserved even when it exceeds the budget. No model download, weight loading, or model substitution occurs. Explicit adapter modules and project batch size, accumulation, rank, quantization, optimizer, and precision are used. Sequence length is capped by the hardware profile. Non-CUDA suggestions use unquantized fp32 weights and adamw_torch.

An explicit positive `num_parameters` in a local model's `config.json` takes precedence over a size suffix such as `1.5B` or `500M` in the final model-name component. Most model configurations do not provide this field. Missing or unrecognized sizes remain unknown; they are never assigned an arbitrary small model size. Sizes above 13B are not truncated to 13B.

Memory components cover weights, activations, adapters, optimizer state, and planning headroom. The formulas are uncalibrated heuristics adapted from the design reference. They do not model every architecture, kernel, cache, allocator, or quantization implementation. They must not be used as measured peak-memory guarantees. Runtime profiling is still required for hardware validation.

- `estimated_fit`: the heuristic estimate is within the CUDA budget.
- `over_budget`: the estimate exceeds the budget; reduce settings or explicitly choose another model.
- `unknown`: insufficient model-size or device-budget information, or CPU/MPS fit is unverified.

Confidence never exceeds `medium` without measured validation. Unknown families additionally warn that target modules need verification. CPU/MPS suggestions report an estimated total memory value when possible, but report dedicated VRAM as `null`.

## Output compatibility

`estimated_vram_gb` is now nullable when VRAM cannot be meaningfully estimated. JSON consumers should also inspect `fit` and `parameter_source`. New fields include `estimated_memory_gb`, `memory_breakdown_gb`, `target_vram_gb`, `reasons`, and `config_patch`.

The planner does not yet apply patches automatically, inspect tensor shapes, measure free device memory, or perform runtime memory probes. The training dry-run still uses a separate rough estimator; its value is not a validation of this planner's estimate.
