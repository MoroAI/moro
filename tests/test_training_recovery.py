"""Tests for the OOM Auto-Recovery Protocol."""

from moro.training.recovery import apply_oom_recovery_protocol, summarize_recovery


def _make_config():
    """Create a minimal MoroConfig-like object for testing."""
    import tempfile

    import yaml

    from moro.config.models import MoroConfig

    # Create a temporary file to use as dataset source
    tmpfile = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False)
    tmpfile.close()
    minimal_yaml = f"""
project:
  name: test_project
  seed: 42
  privacy_mode: local_only
model:
  name: Qwen2.5-1.5B
  quantization: nf4
adapter:
  r: 64
  alpha: 128
  dropout: 0.05
  target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj
  bias: none
training:
  epochs: 1
  batch_size: 4
  gradient_accumulation_steps: 4
  learning_rate: 0.0002
  optimizer: adamw_8bit
  gradient_checkpointing: false
  warmup_ratio: 0.03
  logging_steps: 10
  save_steps: 100
  precision: auto
dataset:
  source: {tmpfile.name}
  max_seq_length: 2048
  min_quality_score: 0.0
  deduplicate: true
release:
  require:
    min_improvement: 2.0
"""
    return MoroConfig.model_validate(yaml.safe_load(minimal_yaml))


def test_step1_reduces_seq_length():
    """Step 1: max_seq_length should be reduced by 25%."""
    config = _make_config()
    original_seq = config.dataset.max_seq_length  # 2048
    recovered, actions = apply_oom_recovery_protocol(config, step_limit=1)

    new_seq = recovered.dataset.max_seq_length
    assert new_seq < original_seq
    assert new_seq == max(512, int(original_seq * 0.75))
    assert any("[Step 1]" in a for a in actions)


def test_step2_reduces_batch_size():
    """Step 2: batch_size should go to 1, gradient_accumulation should scale up."""
    config = _make_config()
    original_bs = config.training.batch_size  # 4
    original_acc = config.training.gradient_accumulation_steps  # 4
    recovered, actions = apply_oom_recovery_protocol(config, step_limit=2)

    assert recovered.training.batch_size == 1
    assert recovered.training.gradient_accumulation_steps == original_acc * original_bs
    assert any("[Step 2]" in a for a in actions)


def test_step3_narrows_target_modules():
    """Step 3: Should narrow from 7 modules to 4 (attention-only)."""
    config = _make_config()
    assert len(config.adapter.target_modules) == 7  # pre-condition
    recovered, actions = apply_oom_recovery_protocol(config, step_limit=3)

    assert len(recovered.adapter.target_modules) <= 4
    assert any("[Step 3]" in a for a in actions)


def test_step4_halves_lora_rank():
    """Step 4: LoRA rank should be halved."""
    config = _make_config()
    original_r = config.adapter.r  # 64
    recovered, actions = apply_oom_recovery_protocol(config, step_limit=4)

    assert recovered.adapter.r <= original_r // 2
    assert recovered.adapter.r >= 8  # minimum
    assert any("[Step 4]" in a for a in actions)


def test_step5_enables_paged_optimizer():
    """Step 5: Should switch to paged_adamw_8bit and enable gradient checkpointing."""
    config = _make_config()
    assert config.training.optimizer != "paged_adamw_8bit"  # pre-condition
    assert not config.training.gradient_checkpointing  # pre-condition

    recovered, actions = apply_oom_recovery_protocol(config)

    assert recovered.training.optimizer == "paged_adamw_8bit"
    assert recovered.training.gradient_checkpointing is True
    assert any("[Step 5]" in a for a in actions)


def test_full_recovery_protocol():
    """All 5 steps should be applied and reported."""
    config = _make_config()
    recovered, actions = apply_oom_recovery_protocol(config)

    # All steps should have been applied
    assert len(actions) >= 5
    step_numbers = set()
    for a in actions:
        import re

        m = re.search(r"\[Step (\d)\]", a)
        if m:
            step_numbers.add(int(m.group(1)))
    assert step_numbers == {1, 2, 3, 4, 5}


def test_recovery_does_not_mutate_original():
    """The original config should not be modified."""
    config = _make_config()
    original_seq = config.dataset.max_seq_length
    original_bs = config.training.batch_size
    original_r = config.adapter.r

    recovered, _ = apply_oom_recovery_protocol(config)

    assert config.dataset.max_seq_length == original_seq
    assert config.training.batch_size == original_bs
    assert config.adapter.r == original_r


def test_summarize_recovery():
    """summarize_recovery should format actions for display."""
    actions = ["[Step 1] Reduced seq", "[Step 2] Reduced batch"]
    summary = summarize_recovery(actions)
    assert "OOM Auto-Recovery Protocol Applied" in summary
    assert "[Step 1]" in summary
    assert "[Step 2]" in summary


def test_summarize_no_actions():
    result = summarize_recovery([])
    assert result == "No recovery actions taken."
