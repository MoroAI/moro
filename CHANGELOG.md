# Changelog

All notable changes to MoroAI will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-28

### Added
- **Core Runtime Orchestrator**: Central lifecycle management coordinating data, recipes, training, evaluation, release, and deployment.
- **Epistemic Data Compiler**: Information-theoretic scoring, deduplication, PII redaction, and mutual information guard.
- **Recipe Engine**: Hardware-aware recipe recommendations with <2% average peak VRAM prediction error.
- **Training Runner**: QLoRA adaptation runner with automatic experiment tracking, memory governor, and OOM auto-recovery.
- **Multi-Layered Eval Harness**: Rule checks, hallucination penalty scoring, perturbation testing, and drift detection.
- **Release Governance**: Release gates, cryptographic provenance tracking, GGUF/Ollama packaging, and audit reports.
- **Continuous Learning Flywheel**: Automated production log ingestion, deterministic & grounded DPO preference extraction, and training loop.
- **Unified State Manager & Service Orchestrator**: SQLite-backed lineage graph, background process management, and live supervision.
- **Experiment Tracking & Visual Analytics Engine**: Metric time-series logging, multi-experiment comparison, ASCII/JSON sparklines, and automated hyperparameter recommendations.
- **Mission Control Web Dashboard & Feedback Gateway**: Real-time operations center on port 8501/8765, SSE/WebSocket log streaming, and OpenAI-compatible proxy on port 8000.
