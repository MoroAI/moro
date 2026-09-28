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
import yaml


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
        {"messages": [{"role": "user", "content": "Hello"}, {"role": "assistant", "content": "Hi!"}]},
        {"messages": [{"role": "user", "content": "Test"}, {"role": "assistant", "content": "Response"}]},
    ]

    with open(project_dir / "data" / "raw" / "sample_data.jsonl", "w", encoding="utf-8") as f:
        for item in sample_data:
            f.write(json.dumps(item) + "\n")

    return project_dir


class TestCompletePipeline:
    """Test the complete pipeline end-to-end."""

    def test_data_compilation(self, initialized_project):
        """Test that data compilation works."""
        from moro.data.compiler import DataCompiler

        compiler = DataCompiler(initialized_project)

        dataset_id = compiler.compile_dataset(
            source_path=initialized_project / "data" / "raw" / "sample_data.jsonl",
            config={"format": "jsonl", "deduplicate": True},
        )

        assert dataset_id is not None
        assert (initialized_project / "data" / "compiled" / "train.jsonl").exists()

    def test_recipe_generation(self, initialized_project):
        """Test that recipe generation works."""
        from moro.recipes.engine import RecipeEngine

        engine = RecipeEngine(initialized_project)

        recipe = engine.generate_recipe(
            model_name="test-model-1.5b",
        )

        assert recipe is not None
        assert "model_name" in recipe
        assert "lora_r" in recipe
        assert "learning_rate" in recipe

    def test_training_execution(self, initialized_project):
        """Test that training execution works."""
        from moro.data.compiler import DataCompiler
        from moro.recipes.engine import RecipeEngine
        from moro.training.runner import TrainingRunner

        # First compile data
        compiler = DataCompiler(initialized_project)
        compiler.compile_dataset(
            source_path=initialized_project / "data" / "raw" / "sample_data.jsonl",
            config={"format": "jsonl"},
        )

        # Generate recipe
        engine = RecipeEngine(initialized_project)
        recipe = engine.generate_recipe(model_name="test-model")

        # Run training
        runner = TrainingRunner(initialized_project)
        results = runner.run_training(
            recipe=recipe,
            dataset_id="test_dataset",
        )

        assert results is not None
        assert results["status"] == "completed"
        assert "run_id" in results

    def test_evaluation_execution(self, initialized_project):
        """Test that evaluation execution works."""
        from moro.eval.harness import EvalHarness

        # Create a simple eval suite
        eval_suite = {
            "name": "test-suite",
            "cases": [
                {
                    "id": "test_1",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "expect": {"contains": ["Hi"]},
                },
            ],
        }

        eval_path = initialized_project / "eval" / "test_suite.yaml"
        with open(eval_path, "w", encoding="utf-8") as f:
            yaml.dump(eval_suite, f)

        # Run evaluation
        harness = EvalHarness(initialized_project)
        results = harness.run_evaluation(
            run_id="test_run",
            eval_suite_path=eval_path,
        )

        assert results is not None
        assert results["status"] == "completed"
        assert "pass_rate" in results

    def test_release_creation(self, initialized_project):
        """Test that release creation works."""
        from moro.release.manager import ReleaseManager

        # Create a fake run
        run_dir = initialized_project / "runs" / "test_run"
        run_dir.mkdir(parents=True)
        (run_dir / "model").mkdir()
        (run_dir / "model" / "config.json").write_text("{}")

        # Create release
        manager = ReleaseManager(initialized_project)
        results = manager.create_release(
            run_id="test_run",
            version="v0.1.0",
        )

        assert results is not None
        assert results["status"] == "created"
        assert (initialized_project / "releases" / "v0.1.0").exists()

    def test_flywheel_execution(self, initialized_project):
        """Test that flywheel execution works."""
        from moro.flywheel.orchestrator import FlywheelOrchestrator

        orchestrator = FlywheelOrchestrator(initialized_project)
        results = orchestrator.run_cycle()

        assert results is not None
        assert "status" in results

    def test_complete_pipeline(self, initialized_project):
        """Test the complete pipeline end-to-end."""
        from moro.data.compiler import DataCompiler
        from moro.eval.harness import EvalHarness
        from moro.recipes.engine import RecipeEngine
        from moro.release.manager import ReleaseManager
        from moro.training.runner import TrainingRunner

        # Step 1: Compile data
        compiler = DataCompiler(initialized_project)
        dataset_id = compiler.compile_dataset(
            source_path=initialized_project / "data" / "raw" / "sample_data.jsonl",
            config={"format": "jsonl"},
        )

        assert dataset_id is not None

        # Step 2: Generate recipe
        engine = RecipeEngine(initialized_project)
        recipe = engine.generate_recipe(model_name="test-model")

        assert recipe is not None

        # Step 3: Run training
        runner = TrainingRunner(initialized_project)
        training_results = runner.run_training(
            recipe=recipe,
            dataset_id=dataset_id,
        )

        assert training_results["status"] == "completed"

        # Step 4: Run evaluation
        eval_suite = {
            "name": "test-suite",
            "cases": [
                {
                    "id": "test_1",
                    "messages": [{"role": "user", "content": "Hello"}],
                },
            ],
        }

        eval_path = initialized_project / "eval" / "test_suite.yaml"
        with open(eval_path, "w", encoding="utf-8") as f:
            yaml.dump(eval_suite, f)

        harness = EvalHarness(initialized_project)
        eval_results = harness.run_evaluation(
            run_id=training_results["run_id"],
            eval_suite_path=eval_path,
        )

        assert eval_results["status"] == "completed"

        # Step 5: Create release
        manager = ReleaseManager(initialized_project)
        release_results = manager.create_release(
            run_id=training_results["run_id"],
            version="v0.1.0",
            eval_results=eval_results,
        )

        assert release_results["status"] == "created"

        # Verify all outputs exist
        assert (initialized_project / "data" / "compiled" / "train.jsonl").exists()
        assert (initialized_project / "runs" / training_results["run_id"]).exists()
        assert (initialized_project / "releases" / "v0.1.0").exists()
