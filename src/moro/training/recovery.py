"""
MoroAI 5-Step OOM Auto-Recovery Protocol.

When a CUDA Out-Of-Memory error occurs during training, MoroAI does not crash.
Instead, it executes this 5-step topological downgrade to reduce memory pressure
and automatically retries the training run.

The 5 steps, in order:
  1. Reduce max_seq_length → 75% (reduces KV-cache)
  2. Reduce micro-batch to 1 + double gradient_accumulation (maintains effective batch)
  3. Narrow LoRA target modules to attention-only (reduces adapter parameters)
  4. Halve LoRA rank r (directly reduces adapter VRAM)
  5. Switch to paged_adamw_8bit + force gradient_checkpointing (optimizer state offload)

Each step is logged for observability. The resulting config is persisted back to
moro.yaml with a "recovered" marker so the user sees exactly what changed.
"""

from __future__ import annotations

from moro.config.models import MoroConfig

# Conservative attention-only module set (minimum viable LoRA)
_ATTENTION_ONLY_MODULES = ["q_proj", "v_proj"]

# Full attention (without MLP)
_ATTENTION_FULL_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj"]


def apply_oom_recovery_protocol(
    config: MoroConfig,
    oom_context: str = "",
    step_limit: int = 5,
) -> tuple[MoroConfig, list[str]]:
    """
    Execute the Memory Governor's 5-Step OOM Auto-Recovery protocol.

    Args:
        config: Current training configuration.
        oom_context: Raw OOM error message string for context logging.
        step_limit: Maximum number of recovery steps to apply (default: all 5).

    Returns:
        (recovered_config, list_of_actions_taken)
        If no further downgrades are possible, actions_taken will contain
        a "Hardware limit reached" message.
    """
    recovered = config.model_copy(deep=True)
    actions_taken: list[str] = []
    steps_applied = 0

    # ── Step 1: Reduce Sequence Length ────────────────────────────────────────
    if steps_applied < step_limit:
        current_seq = recovered.dataset.max_seq_length
        if current_seq > 512:
            new_seq = max(512, int(current_seq * 0.75))
            if new_seq != current_seq:
                recovered.dataset.max_seq_length = new_seq
                actions_taken.append(
                    f"[Step 1] Reduced max_seq_length: {current_seq} → {new_seq} "
                    "(reduces KV-cache memory pressure)"
                )
                steps_applied += 1

    # ── Step 2: Reduce Micro-Batch + Scale Accumulation ───────────────────────
    if steps_applied < step_limit:
        if recovered.training.batch_size > 1:
            old_bs = recovered.training.batch_size
            old_acc = recovered.training.gradient_accumulation_steps
            new_acc = old_acc * old_bs  # Keep effective batch size constant
            recovered.training.batch_size = 1
            recovered.training.gradient_accumulation_steps = new_acc
            actions_taken.append(
                f"[Step 2] batch_size: {old_bs} → 1, "
                f"gradient_accumulation: {old_acc} → {new_acc} "
                "(effective batch size preserved)"
            )
            steps_applied += 1
        elif recovered.training.gradient_accumulation_steps < 64:
            old_acc = recovered.training.gradient_accumulation_steps
            new_acc = old_acc * 2
            recovered.training.gradient_accumulation_steps = new_acc
            actions_taken.append(
                f"[Step 2] Doubled gradient_accumulation_steps: {old_acc} → {new_acc}"
            )
            steps_applied += 1

    # ── Step 3: Narrow LoRA Target Modules ────────────────────────────────────
    if steps_applied < step_limit:
        current_targets = recovered.adapter.target_modules
        if isinstance(current_targets, list):
            # If more than 4 modules (i.e., includes MLP), narrow to attention-only
            if len(current_targets) > 4:
                recovered.adapter.target_modules = list(_ATTENTION_FULL_MODULES)
                actions_taken.append(
                    f"[Step 3] Narrowed target_modules: {len(current_targets)} → 4 "
                    "(attention-only, excluded MLP gate/up/down)"
                )
                steps_applied += 1
            # If still 4 (full attention), narrow to basic (q+v only)
            elif len(current_targets) > 2:
                recovered.adapter.target_modules = list(_ATTENTION_ONLY_MODULES)
                actions_taken.append(
                    f"[Step 3] Narrowed target_modules: {len(current_targets)} → 2 "
                    "(minimal q_proj + v_proj only)"
                )
                steps_applied += 1

    # ── Step 4: Halve LoRA Rank ────────────────────────────────────────────────
    if steps_applied < step_limit:
        current_r = recovered.adapter.r
        if current_r > 8:
            new_r = max(8, current_r // 2)
            new_alpha = new_r * 2
            recovered.adapter.r = new_r
            recovered.adapter.alpha = new_alpha
            actions_taken.append(
                f"[Step 4] Halved LoRA rank: r={current_r} → r={new_r}, "
                f"alpha={recovered.adapter.alpha // 2} → alpha={new_alpha} "
                "(directly reduces adapter VRAM)"
            )
            steps_applied += 1
        elif current_r > 4:
            new_r = 4
            new_alpha = 8
            recovered.adapter.r = new_r
            recovered.adapter.alpha = new_alpha
            actions_taken.append(
                f"[Step 4] Reduced LoRA rank to minimum: r={current_r} → r={new_r}"
            )
            steps_applied += 1

    # ── Step 5: Paged Optimizer + Gradient Checkpointing ─────────────────────
    if steps_applied < step_limit:
        changes = []
        if recovered.training.optimizer != "paged_adamw_8bit":
            old_opt = recovered.training.optimizer
            recovered.training.optimizer = "paged_adamw_8bit"
            changes.append(f"optimizer: {old_opt} → paged_adamw_8bit")
        if not recovered.training.gradient_checkpointing:
            recovered.training.gradient_checkpointing = True
            changes.append("gradient_checkpointing: False → True")
        if changes:
            actions_taken.append(
                f"[Step 5] Memory offloading: {'; '.join(changes)} "
                "(optimizer state offloaded to CPU)"
            )
            steps_applied += 1

    if not actions_taken:
        actions_taken.append(
            "No further automated downgrades available. Hardware limit reached. "
            "Consider using a smaller model or a machine with more VRAM."
        )

    return recovered, actions_taken


def summarize_recovery(actions: list[str]) -> str:
    """Format the recovery actions for display in the terminal / logs."""
    if not actions:
        return "No recovery actions taken."
    lines = ["OOM Auto-Recovery Protocol Applied:"]
    for action in actions:
        lines.append(f"  • {action}")
    return "\n".join(lines)
