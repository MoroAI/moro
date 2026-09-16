DEFAULT_GITIGNORE = """\
# MoroAI local state
.moro/

# Generated data and outputs
data/normalized/
data/splits/
runs/
releases/

# Python
__pycache__/
*.pyc
*.pyo
*.pyd
.venv/
venv/
.env
"""


def readme_template(project_name: str) -> str:
    return f"""\
# {project_name}

This is a MoroAI project.

## Getting started

1. Add raw data to `data/raw/`
2. Update `moro.yaml`
3. Run:

```bash
moro status
moro doctor
moro import ./data/raw/your-data.jsonl --name my-data
moro data build
moro recipe suggest
moro train
```

## Layout

- `moro.yaml` — project configuration
- `data/raw/` — raw input data
- `data/normalized/` — normalized dataset output
- `data/splits/` — train/validation/eval splits
- `eval/` — evaluation suites
- `runs/` — training runs
- `releases/` — packaged releases
"""


def default_moro_yaml(project_name: str) -> str:
    return f"""\
project:
  name: {project_name}
  privacy_mode: local_only
  seed: 42

dataset:
  source: ./data/raw/support.jsonl
  format: auto
  deduplicate: true
  pii_scan: false
  max_seq_length: 1024
  min_quality_score: 0.0
  validation_ratio: 0.1
  eval_ratio: 0.1

model:
  name: Qwen/Qwen2.5-1.5B-Instruct
  revision: main
  quantization: nf4
  trust_remote_code: false

adapter:
  type: lora
  r: 16
  alpha: 32
  dropout: 0.05
  target_modules: auto
  bias: none

training:
  output_dir: ./runs
  batch_size: 1
  gradient_accumulation_steps: 16
  learning_rate: 0.0002
  optimizer: paged_adamw_8bit
  gradient_checkpointing: true
  precision: auto
  epochs: 1.0
  warmup_ratio: 0.03
  logging_steps: 10
  save_steps: 100

eval:
  suites:
    - path: ./eval/support-golden-v1.yaml
  max_samples: null

release:
  export:
    - adapter
    - ollama
  require:
    safety_pass: true
"""


SAMPLE_EVAL_YAML = """\
name: support-golden-v1
version: "1"
description: Basic support assistant golden questions
cases:
  - id: reset_password
    messages:
      - role: user
        content: "How do I reset my password?"
    expect:
      contains:
        - "Settings"
        - "Security"
    tags:
      - account

  - id: refund_policy
    messages:
      - role: user
        content: "What is your refund policy?"
    expect:
      any_of_contains:
        - "refund"
        - "14 days"
    tags:
      - billing

  - id: contact_support
    messages:
      - role: user
        content: "How do I contact support?"
    expect:
      any_of_contains:
        - "email"
        - "chat"
        - "support"
    tags:
      - general
"""
