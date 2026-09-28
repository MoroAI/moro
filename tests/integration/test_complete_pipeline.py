"""
MoroAI Complete Pipeline Integration Test.

This test verifies that the entire MoroAI pipeline works end-to-end:
1. Data compilation
2. Recipe generation
3. Training
4. Evaluation
5. Release
6. Deployment

Run with: pytest tests/integration/test_complete_pipeline.py -v
"""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest
import yaml

# ===================================================================
# FIXTURES
# ===================================================================


@pytest.fixture
def temp_project():
    """Create a temporary project directory."""
    temp_dir = tempfile.mkdtemp(prefix="moro_test_")
    project_root = Path(temp_dir)

    # Create project structure
    (project_root / "data" / "raw").mkdir(parents=True)
    (project_root / "data" / "dpo").mkdir(parents=True)
    (project_root / ".moro").mkdir(parents=True)
    (project_root / "runs").mkdir(parents=True)
    (project_root / "releases").mkdir(parents=True)
    (project_root / "eval").mkdir(parents=True)

    yield project_root

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_dataset(temp_project):
    """Create a sample dataset for testing."""
    dataset_path = temp_project / "data" / "raw" / "test_dataset.jsonl"

    samples = [
        {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the capital of France?"},
                {"role": "assistant", "content": "The capital of France is Paris."},
            ]
        },
        {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is 2 + 2?"},
                {"role": "assistant", "content": "2 + 2 equals 4."},
            ]
        },
        {
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is the boiling point of water?"},
                {
                    "role": "assistant",
                    "content": "Water boils at 100 degrees Celsius at sea level.",
                },
            ]
        },
    ]

    with open(dataset_path, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")

    return dataset_path


@pytest.fixture
def sample_eval_suite(temp_project):
    """Create a sample evaluation suite."""
    eval_path = temp_project / "eval" / "test_suite.yaml"

    eval_config = {
        "name": "test-suite",
        "version": "1",
        "cases": [
            {
                "id": "capital_france",
                "messages": [{"role": "user", "content": "What is the capital of France?"}],
                "expect": {"contains": ["Paris"]},
            },
            {
                "id": "math_addition",
                "messages": [{"role": "user", "content": "What is 2 + 2?"}],
                "expect": {"contains": ["4"]},
            },
        ],
    }

    with open(eval_path, "w", encoding="utf-8") as f:
        yaml.dump(eval_config, f)

    return eval_path


@pytest.fixture
def sample_config(temp_project):
    """Create a sample moro.yaml configuration."""
    config_path = temp_project / "moro.yaml"

    config = {
        "project": {
            "name": "test-project",
            "privacy_mode": "local_only",
        },
        "dataset": {
            "source": "./data/raw/test_dataset.jsonl",
            "format": "auto",
            "deduplicate": True,
            "pii_scan": True,
        },
        "model": {
            "name": "test-model",
            "quantization": "nf4",
        },
        "adapter": {
            "type": "lora",
            "r": 8,
            "alpha": 16,
            "target_modules": ["q_proj", "v_proj"],
        },
        "training": {
            "learning_rate": 0.0002,
            "batch_size": 1,
            "epochs": 1,
            "max_seq_length": 512,
        },
        "eval": {"suites": [{"path": "./eval/test_suite.yaml"}]},
        "release": {
            "require": {
                "min_improvement": 0.0,
                "safety_pass": True,
            }
        },
    }

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f)

    return config_path


# ===================================================================
# TESTS
# ===================================================================


class TestStateManagement:
    """Test the unified state manager."""

    def test_state_db_initialization(self, temp_project):
        """Test that the state database is created correctly."""
        from moro.state.schema import initialize_state_db

        db_path = temp_project / ".moro" / "state.db"
        conn = initialize_state_db(db_path)

        assert db_path.exists()

        # Check tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "nodes" in tables
        assert "edges" in tables
        assert "model_registry" in tables
        assert "operation_log" in tables
        assert "service_state" in tables

        conn.close()

    def test_node_creation_and_query(self, temp_project):
        """Test creating and querying nodes."""
        from moro.state.manager import StateManager
        from moro.state.schema import NodeStatus, NodeType

        db_path = temp_project / ".moro" / "state.db"
        manager = StateManager(db_path)

        # Create a node
        node_id = manager.create_node(
            node_type=NodeType.DATASET_VERSION,
            name="test_dataset_v1",
            payload={"tokens": 1000, "samples": 100},
            status=NodeStatus.COMPLETED,
        )

        assert node_id is not None
        assert node_id.startswith("data")

        # Query the node
        node = manager.get_node(node_id)

        assert node is not None
        assert node["name"] == "test_dataset_v1"
        assert node["status"] == "completed"

        # Query by type
        nodes = manager.query_nodes(node_type=NodeType.DATASET_VERSION)

        assert len(nodes) == 1
        assert nodes[0]["node_id"] == node_id

    def test_edge_creation_and_lineage(self, temp_project):
        """Test creating edges and tracing lineage."""
        from moro.state.manager import StateManager
        from moro.state.schema import EdgeType, NodeType

        db_path = temp_project / ".moro" / "state.db"
        manager = StateManager(db_path)

        # Create nodes
        source_id = manager.create_node(
            node_type=NodeType.RAW_SOURCE,
            name="raw_data.jsonl",
        )

        dataset_id = manager.create_node(
            node_type=NodeType.DATASET_VERSION,
            name="dataset_v1",
        )

        # Create edge
        manager.create_edge(
            source_node_id=source_id,
            target_node_id=dataset_id,
            edge_type=EdgeType.DERIVED_FROM,
        )

        # Trace lineage
        lineage = manager.trace_lineage(dataset_id)

        assert lineage is not None
        assert lineage["node_id"] == dataset_id

    def test_model_registry(self, temp_project):
        """Test the model registry."""
        from moro.state.manager import StateManager

        db_path = temp_project / ".moro" / "state.db"
        manager = StateManager(db_path)

        # Register a model
        model_id = manager.register_model(
            model_name="test-model",
            version="v1.0.0",
            base_model="Qwen/Qwen2.5-1.5B-Instruct",
            quantization="nf4",
            adapter_type="lora",
            lora_rank=8,
        )

        assert model_id is not None

        # Query the model
        model = manager.get_model("test-model", "v1.0.0")

        assert model is not None
        assert model["model_name"] == "test-model"
        assert model["version"] == "v1.0.0"
        assert model["base_model"] == "Qwen/Qwen2.5-1.5B-Instruct"

        # List models
        models = manager.list_models()

        assert len(models) == 1
        assert models[0]["model_id"] == model_id


class TestExperimentTracking:
    """Test the experiment tracking system."""

    def test_experiment_db_initialization(self, temp_project):
        """Test that the experiment database is created correctly."""
        from moro.analytics.schema import initialize_experiment_db

        db_path = temp_project / ".moro" / "analytics.db"
        conn = initialize_experiment_db(db_path)

        assert db_path.exists()

        # Check tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

        assert "experiments" in tables
        assert "hyperparameters" in tables
        assert "metrics" in tables
        assert "eval_results" in tables
        assert "model_outputs" in tables
        assert "recommendations" in tables

        conn.close()

    def test_experiment_lifecycle(self, temp_project):
        """Test the complete experiment lifecycle."""
        from moro.analytics.tracker import ExperimentTracker

        db_path = temp_project / ".moro" / "analytics.db"
        tracker = ExperimentTracker(db_path)

        # Create experiment
        experiment_id = tracker.create_experiment(
            name="test_run_001",
            base_model="test-model",
            dataset_id="dataset_001",
            dataset_name="test_dataset",
            tags=["test", "integration"],
        )

        assert experiment_id is not None
        assert experiment_id.startswith("exp")

        # Start experiment with hyperparameters
        tracker.start_experiment(
            experiment_id=experiment_id,
            hyperparameters={
                "learning_rate": 0.0002,
                "batch_size": 1,
                "epochs": 3,
                "lora_r": 8,
                "lora_alpha": 16,
                "target_modules": ["q_proj", "v_proj"],
            },
            gpu_name="NVIDIA RTX 3060",
            gpu_vram_gb=12.0,
        )

        # Log metrics
        for step in range(10):
            tracker.log_metrics(
                experiment_id=experiment_id,
                step=step,
                train_loss=2.0 - (step * 0.1),
                grad_norm=1.0 + (step * 0.01),
                learning_rate=0.0002,
                vram_allocated_gb=8.0 + (step * 0.1),
            )

        # Complete experiment
        tracker.complete_experiment(
            experiment_id=experiment_id,
            final_train_loss=1.1,
            final_eval_loss=1.2,
            eval_pass_rate=0.85,
            eval_delta=0.15,
            peak_vram_gb=9.5,
            total_steps=10,
            tokens_per_second=150.0,
        )

        # Verify experiment
        experiment = tracker.get_experiment(experiment_id)

        assert experiment is not None
        assert experiment["status"] == "completed"
        assert experiment["final_train_loss"] == 1.1
        assert experiment["eval_pass_rate"] == 0.85
        assert experiment["eval_delta"] == 0.15

        # Verify metrics
        metrics = tracker.get_metrics(experiment_id)

        assert len(metrics) == 10
        assert metrics[0]["step"] == 0
        assert metrics[0]["train_loss"] == 2.0
        assert metrics[9]["step"] == 9
        assert metrics[9]["train_loss"] == 1.1

    def test_experiment_comparison(self, temp_project):
        """Test comparing multiple experiments."""
        from moro.analytics.tracker import ExperimentTracker

        db_path = temp_project / ".moro" / "analytics.db"
        tracker = ExperimentTracker(db_path)

        # Create two experiments
        exp1_id = tracker.create_experiment(
            name="run_001",
            base_model="test-model",
        )

        exp2_id = tracker.create_experiment(
            name="run_002",
            base_model="test-model",
        )

        # Start with different hyperparameters
        tracker.start_experiment(
            experiment_id=exp1_id,
            hyperparameters={
                "learning_rate": 0.0002,
                "lora_r": 8,
            },
        )

        tracker.start_experiment(
            experiment_id=exp2_id,
            hyperparameters={
                "learning_rate": 0.0001,
                "lora_r": 16,
            },
        )

        # Complete with different results
        tracker.complete_experiment(
            experiment_id=exp1_id,
            eval_delta=0.10,
        )

        tracker.complete_experiment(
            experiment_id=exp2_id,
            eval_delta=0.15,
        )

        # Compare
        comparison = tracker.compare_experiments([exp1_id, exp2_id])

        assert comparison is not None
        assert len(comparison["experiments"]) == 2

        # Check hyperparameter differences
        hp_diffs = comparison["hyperparameter_differences"]

        assert "learning_rate" in hp_diffs
        assert "lora_r" in hp_diffs

        # Best experiment should be exp2 (higher eval_delta)
        assert comparison["best_experiment_id"] == exp2_id


class TestRuntimeOrchestrator:
    """Test the runtime orchestrator."""

    def test_orchestrator_initialization(self, temp_project, sample_config):
        """Test that the orchestrator initializes correctly."""
        from moro.runtime.orchestrator import MoroRuntimeOrchestrator

        orchestrator = MoroRuntimeOrchestrator(temp_project)

        assert orchestrator is not None
        assert orchestrator.project_root == temp_project

    def test_execution_context_creation(self, temp_project, sample_config):
        """Test creating execution contexts."""
        from moro.runtime.orchestrator import (
            ExecutionPhase,
            ExecutionState,
            MoroRuntimeOrchestrator,
        )

        orchestrator = MoroRuntimeOrchestrator(temp_project)

        context = orchestrator.create_execution(
            phase=ExecutionPhase.DATA_COMPILATION,
            config={"test": True},
        )

        assert context is not None
        assert context.execution_id.startswith("exec")
        assert context.state == ExecutionState.INITIALIZING
        assert context.phase == ExecutionPhase.DATA_COMPILATION

    def test_execution_lifecycle(self, temp_project, sample_config):
        """Test the complete execution lifecycle."""
        from moro.runtime.orchestrator import (
            ExecutionPhase,
            ExecutionState,
            MoroRuntimeOrchestrator,
        )

        orchestrator = MoroRuntimeOrchestrator(temp_project)

        context = orchestrator.create_execution(
            phase=ExecutionPhase.DATA_COMPILATION,
            config={"test": True},
        )

        # Track progress
        progress_messages = []
        context.add_progress_callback(lambda ctx, msg, pct: progress_messages.append(msg))

        # Simulate execution
        async def run_test():
            async def phase_handler(ctx):
                ctx.report_progress("Step 1", 25)
                await asyncio.sleep(0.01)
                ctx.report_progress("Step 2", 50)
                await asyncio.sleep(0.01)
                ctx.report_progress("Step 3", 100)
                return {"result": "success"}

            result = await orchestrator.execute_phase(context, phase_handler)
            return result

        result = asyncio.run(run_test())

        assert result is not None
        assert result["result"] == "success"
        assert context.state == ExecutionState.COMPLETED
        assert len(progress_messages) >= 3

    def test_error_recovery(self, temp_project, sample_config):
        """Test error recovery mechanisms."""
        from moro.runtime.orchestrator import (
            ExecutionPhase,
            MoroRuntimeOrchestrator,
        )

        orchestrator = MoroRuntimeOrchestrator(temp_project)

        context = orchestrator.create_execution(
            phase=ExecutionPhase.TRAINING,
            config={"batch_size": 4},
        )

        # Simulate OOM error on first attempt, success on second
        attempt_count = [0]

        async def run_test():
            async def phase_handler(ctx):
                attempt_count[0] += 1

                if attempt_count[0] == 1:
                    # Simulate OOM error
                    raise RuntimeError("CUDA out of memory")

                return {"result": "success"}

            result = await orchestrator.execute_phase(context, phase_handler)
            return result

        result = asyncio.run(run_test())

        # Should have recovered and succeeded
        assert result is not None
        assert result["result"] == "success"
        assert attempt_count[0] == 2  # Two attempts
        assert context.config["batch_size"] == 2  # Halved by recovery


class TestServiceOrchestrator:
    """Test the service orchestrator."""

    def test_service_definitions(self, temp_project):
        """Test that services are defined correctly."""
        from moro.services.orchestrator import ServiceOrchestrator
        from moro.state.schema import initialize_state_db

        state_db = temp_project / ".moro" / "state.db"

        # Initialize state DB first
        initialize_state_db(state_db)

        orchestrator = ServiceOrchestrator(temp_project, state_db)

        assert "ollama" in orchestrator.services
        assert "webhook" in orchestrator.services
        assert "dashboard" in orchestrator.services
        assert "gateway" in orchestrator.services

    def test_service_status(self, temp_project):
        """Test getting service status."""
        from moro.services.orchestrator import ServiceOrchestrator
        from moro.state.schema import initialize_state_db

        state_db = temp_project / ".moro" / "state.db"

        initialize_state_db(state_db)

        orchestrator = ServiceOrchestrator(temp_project, state_db)

        statuses = orchestrator.get_status()

        assert len(statuses) == 4

        for status in statuses:
            assert "name" in status
            assert "running" in status
            assert "healthy" in status


# ===================================================================
# END-TO-END PIPELINE TEST
# ===================================================================


class TestCompletePipeline:
    """Test the complete pipeline end-to-end."""

    def test_complete_pipeline_execution(
        self,
        temp_project,
        sample_dataset,
        sample_eval_suite,
        sample_config,
    ):
        """Test the complete pipeline from data to deployment.

        This is the ultimate integration test that verifies
        every subsystem works together.
        """
        from moro.runtime.orchestrator import MoroRuntimeOrchestrator

        orchestrator = MoroRuntimeOrchestrator(temp_project)

        # Run the complete pipeline
        results = asyncio.run(
            orchestrator.run_complete_pipeline(
                data_source=sample_dataset,
                target_model="test-model",
                eval_suite=sample_eval_suite,
                deploy_target=None,  # Skip deployment for test
            )
        )

        # Verify pipeline completed
        assert results is not None
        assert results["success"] is True
        assert "pipeline_id" in results

        # Verify all phases completed
        phases = results["phases"]

        assert "data_compilation" in phases
        assert "recipe_generation" in phases
        assert "training" in phases
        assert "evaluation" in phases
        assert "release" in phases

        # Verify each phase succeeded
        for phase_name, phase_result in phases.items():
            assert phase_result["status"] == "completed", f"Phase {phase_name} failed"
            assert "duration" in phase_result

        # Verify data compilation produced a dataset
        data_result = phases["data_compilation"]
        assert "dataset_id" in data_result

        # Verify training produced an experiment
        training_result = phases["training"]
        assert "experiment_id" in training_result

        # Verify evaluation produced results
        eval_result = phases["evaluation"]
        assert "eval_id" in eval_result
        assert "pass_rate" in eval_result

        # Verify release produced a release
        release_result = phases["release"]
        assert "release_id" in release_result


# ===================================================================
# PERFORMANCE BENCHMARK TEST
# ===================================================================


class TestPerformanceBenchmarks:
    """Test that performance meets requirements."""

    def test_state_manager_performance(self, temp_project):
        """Test that state operations complete within time limits."""
        from moro.state.manager import StateManager
        from moro.state.schema import NodeType

        db_path = temp_project / ".moro" / "state.db"
        manager = StateManager(db_path)

        # Benchmark node creation
        start = time.time()

        for i in range(100):
            manager.create_node(
                node_type=NodeType.DATASET_VERSION,
                name=f"dataset_{i}",
            )

        duration = time.time() - start

        # Should complete 100 node creations in under 1 second
        assert duration < 1.0, f"Node creation too slow: {duration}s"

        # Benchmark node query
        start = time.time()

        nodes = manager.query_nodes(node_type=NodeType.DATASET_VERSION, limit=100)

        duration = time.time() - start

        # Should query 100 nodes in under 0.5 seconds
        assert duration < 0.5, f"Node query too slow: {duration}s"
        assert len(nodes) == 100

    def test_experiment_tracker_performance(self, temp_project):
        """Test that experiment tracking meets performance requirements."""
        from moro.analytics.tracker import ExperimentTracker

        db_path = temp_project / ".moro" / "analytics.db"
        tracker = ExperimentTracker(db_path)

        # Benchmark metric logging
        experiment_id = tracker.create_experiment(
            name="perf_test",
            base_model="test-model",
        )

        start = time.time()

        for step in range(1000):
            tracker.log_metrics(
                experiment_id=experiment_id,
                step=step,
                train_loss=2.0 - (step * 0.001),
            )

        duration = time.time() - start

        # Should log 1000 metrics in under 2 seconds
        assert duration < 2.0, f"Metric logging too slow: {duration}s"

        # Benchmark metric retrieval
        start = time.time()

        metrics = tracker.get_metrics(experiment_id)

        duration = time.time() - start

        # Should retrieve 1000 metrics in under 0.5 seconds
        assert duration < 0.5, f"Metric retrieval too slow: {duration}s"
        assert len(metrics) == 1000
