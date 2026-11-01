"""Compose services expose pinned images, healthchecks, and resource limits."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

COMPOSE_FILE = Path(__file__).resolve().parent.parent / "docker-compose.yml"


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(COMPOSE_FILE.read_text())


def test_ollama_image_is_digest_pinned(compose):
    image = compose["services"]["ollama"]["image"]
    assert "@sha256:" in image
    assert ":latest" not in image


@pytest.mark.parametrize(
    "service,probe",
    [
        ("dashboard", "http://127.0.0.1:8501/api/health"),
        ("gateway", "http://127.0.0.1:8000/health"),
        ("webhook", "http://127.0.0.1:8001/health"),
    ],
)
def test_http_services_probe_public_health_endpoints(compose, service, probe):
    check = compose["services"][service]["healthcheck"]["test"]
    assert probe in " ".join(check)
    assert "webhook/stats" not in " ".join(check)


def test_flywheel_health_proves_recent_cycles(compose):
    flywheel = compose["services"]["flywheel"]
    assert "flywheel.heartbeat" in flywheel["command"]
    check = " ".join(flywheel["healthcheck"]["test"])
    assert "flywheel.heartbeat" in check
    assert flywheel["healthcheck"]["retries"] >= 1


@pytest.mark.parametrize("service", ["ollama", "dashboard", "gateway", "webhook", "flywheel"])
def test_services_carry_cpu_memory_and_logging_limits(compose, service):
    definition = compose["services"][service]
    assert "cpus" in definition
    assert "mem_limit" in definition
    logging = definition.get("logging") or {}
    assert logging.get("driver") == "json-file"
    assert "max-size" in logging.get("options", {})


def test_dashboard_canonical_port_is_8501(compose):
    dashboard = compose["services"]["dashboard"]
    assert "8501:8501" in " ".join(dashboard["ports"])
    assert "--port 8501" in dashboard["command"]


def test_compose_config_validates():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("docker CLI is not available")
    result = subprocess.run(
        [docker, "compose", "-f", str(COMPOSE_FILE), "config", "--quiet"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
