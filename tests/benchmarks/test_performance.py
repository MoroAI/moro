"""
MoroAI Performance Benchmark Suite.

Verifies that MoroAI meets its performance targets.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
from pathlib import Path

import pytest


@pytest.fixture
def temp_project():
    """Create temporary project directory for benchmarking."""
    temp_dir = tempfile.mkdtemp(prefix="moro_bench_")
    project_root = Path(temp_dir)
    (project_root / ".moro").mkdir(parents=True)
    yield project_root
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def large_dataset(temp_project):
    """Generate a large test dataset (10,000 rows)."""
    dataset_path = temp_project / "large_dataset.jsonl"
    sample = json.dumps({
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."}
        ]
    }) + "\n"

    with open(dataset_path, "w", encoding="utf-8") as f:
        f.write(sample * 10000)

    return dataset_path


class TestDataCompilationPerformance:
    """Benchmark data compilation throughput."""

    def test_compilation_throughput(self, temp_project, large_dataset):
        """Test that data compilation meets throughput targets."""
        from moro.data.compiler import DataCompiler
        from moro.state.manager import StateManager

        state_manager = StateManager(temp_project / ".moro" / "state.db")
        compiler = DataCompiler(temp_project, state_manager)

        start = time.time()

        dataset_id = compiler.compile_dataset(
            source_path=large_dataset,
            config={},
        )

        duration = time.time() - start

        assert dataset_id is not None

        # Calculate throughput
        row_count = 10000  # Known row count of large_dataset
        throughput = row_count / duration

        # Target: > 1000 rows/sec
        assert throughput > 1000, f"Throughput too low: {throughput:.0f} rows/sec"

        print(f"\nData Compilation Throughput: {throughput:.0f} rows/sec")


class TestVRAMPredictionPerformance:
    """Benchmark VRAM prediction accuracy."""

    def test_prediction_accuracy(self):
        """Test that VRAM predictions are within 5% of actual."""
        from moro.recipes.engine import predict_peak_vram_gb

        # Test cases with known actual VRAM usage
        test_cases = [
            {
                "model_class": "1.5b",
                "quantization": "nf4",
                "max_seq_length": 1024,
                "batch_size": 1,
                "lora_r": 16,
                "actual_vram": 3.2,  # GB
            },
            {
                "model_class": "3b",
                "quantization": "nf4",
                "max_seq_length": 2048,
                "batch_size": 1,
                "lora_r": 32,
                "actual_vram": 5.8,  # GB
            },
            {
                "model_class": "7b",
                "quantization": "nf4",
                "max_seq_length": 2048,
                "batch_size": 1,
                "lora_r": 16,
                "actual_vram": 9.5,  # GB
            },
        ]

        errors = []

        for case in test_cases:
            predicted = predict_peak_vram_gb(
                model_class=case["model_class"],
                quantization=case["quantization"],
                max_seq_length=case["max_seq_length"],
                batch_size=case["batch_size"],
                lora_r=case["lora_r"],
            )

            actual = case["actual_vram"]
            error = abs(predicted - actual) / actual

            errors.append(error)

            print(f"\n{case['model_class']}: Predicted {predicted:.2f}GB, Actual {actual:.2f}GB, Error {error:.1%}")

        # Target: > 95% accuracy (error < 5%)
        avg_error = sum(errors) / len(errors)

        assert avg_error < 0.05, f"Average prediction error too high: {avg_error:.1%}"

        print(f"\nAverage VRAM Prediction Error: {avg_error:.1%}")


class TestDashboardPerformance:
    """Benchmark dashboard response times."""

    def test_health_endpoint_response_time(self, temp_project):
        """Test that the health endpoint responds quickly."""
        from fastapi.testclient import TestClient

        from moro.dashboard.mission_control import mission_app

        client = TestClient(mission_app)

        # Warm up
        client.get("/api/health")

        # Measure response time
        times = []

        for _ in range(10):
            start = time.time()
            response = client.get("/api/health")
            duration = time.time() - start

            assert response.status_code == 200
            times.append(duration)

        avg_time = sum(times) / len(times)

        # Target: < 500ms
        assert avg_time < 0.5, f"Average response time too high: {avg_time:.3f}s"

        print(f"\nAverage Health Endpoint Response Time: {avg_time*1000:.0f}ms")


class TestStateQueryPerformance:
    """Benchmark state manager query performance."""

    def test_query_performance_with_1000_nodes(self, temp_project):
        """Test query performance with 1000 nodes."""
        from moro.state.manager import StateManager
        from moro.state.schema import NodeType

        state_manager = StateManager(temp_project / ".moro" / "state.db")

        # Create 1000 nodes
        for i in range(1000):
            state_manager.create_node(
                node_type=NodeType.DATASET_VERSION,
                name=f"dataset_{i}",
            )

        # Benchmark query
        start = time.time()

        nodes = state_manager.query_nodes(
            node_type=NodeType.DATASET_VERSION,
            limit=100,
        )

        duration = time.time() - start

        # Target: < 100ms
        assert duration < 0.1, f"Query too slow: {duration*1000:.0f}ms"
        assert len(nodes) == 100

        print(f"\nState Query Time (100 nodes from 1000): {duration*1000:.0f}ms")
