"""
MoroAI Complete Pipeline Integration Test.

This test verifies that the entire MVP pipeline works end-to-end.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    temp_dir = tempfile.mkdtemp(prefix="moro_test_")
    project_root = Path(temp_dir)

    yield project_root

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def initialized_project(temp_project):
    """Create an initialized MoroAI project."""
    project_dir = temp_project / "test_project"

    # Create project structure
    project_dir.mkdir(parents=True)
    (project_dir / "data" / "raw").mkdir(parents=True)
    (project_dir / "data" / "compiled").mkdir(parents=True)
    (project_dir / "runs").mkdir(parents=True)
    (project_dir / "releases").mkdir(parents=True)
    (project_dir / "eval").mkdir(parents=True)
    (project_dir / ".moro").mkdir(parents=True)

    # Create config
    config_content = """project:
  name: test_project
  privacy_mode: local_only

dataset:
  source: ./data/raw/sample_data.jsonl
  format: jsonl

model:
  name: test-model
  quantization: nf4

training:
  learning_rate: 0.0002
  batch_size: 1
  epochs: 1
"""

    (project_dir / "moro.yaml").write_text(config_content)

    # Create sample data
    sample_data = [
        {
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi!"},
            ]
        },
        {
            "messages": [
                {"role": "user", "content": "Test"},
                {"role": "assistant", "content": "Response"},
            ]
        },
    ]

    with open(project_dir / "data" / "raw" / "sample_data.jsonl", "w", encoding="utf-8") as f:
        for item in sample_data:
            f.write(json.dumps(item) + "\n")

    return project_dir


class TestSDKContracts:
    """Contract tests; inference is mocked explicitly, never presented as real training."""

    def test_data_compilation_has_disjoint_versioned_splits(self, initialized_project):
        from moro.data.compiler import DataCompiler

        source = initialized_project / "data/raw/sample_data.jsonl"
        with source.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "messages": [
                            {"role": "user", "content": "Third distinct question"},
                            {"role": "assistant", "content": "Another useful answer"},
                        ]
                    }
                )
                + "\n"
            )
        version = DataCompiler(initialized_project).compile_dataset(source)
        destination = initialized_project / "data/versions" / version
        splits = [
            {
                json.loads(line)["id"]
                for line in (destination / f"{name}.jsonl").read_text().splitlines()
            }
            for name in ("train", "validation", "eval")
        ]
        assert all(splits)
        assert not (splits[0] & splits[1] or splits[0] & splits[2] or splits[1] & splits[2])

    def test_missing_dataset_cannot_train(self, initialized_project):
        from moro.core.errors import DatasetError
        from moro.training.runner import TrainingRunner

        with pytest.raises(DatasetError, match="No immutable dataset"):
            TrainingRunner(initialized_project).run_training()

    def test_missing_run_cannot_evaluate(self, initialized_project):
        from moro.core.errors import ExportError
        from moro.eval.harness import EvalHarness

        with pytest.raises(ExportError):
            EvalHarness(initialized_project).run_evaluation("missing", "eval/missing.yaml")

    def test_placeholder_model_cannot_release(self, initialized_project):
        from moro.core.errors import ExportError
        from moro.release.manager import ReleaseManager

        model = initialized_project / "runs/fake/model"
        model.mkdir(parents=True)
        (model / "config.json").write_text("{}")
        with pytest.raises(ExportError):
            ReleaseManager(initialized_project).create_release("fake", "v1", {"pass_rate": 1.0})
        assert not list((initialized_project / "releases").iterdir())

    def test_missing_deployment_cannot_claim_active(self, initialized_project):
        import asyncio

        from moro.core.errors import ExportError
        from moro.deploy.manager import DeploymentManager

        with pytest.raises(ExportError, match="No endpoint has been created"):
            asyncio.run(DeploymentManager(initialized_project).deploy_async("missing", "ollama"))
