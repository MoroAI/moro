"""Regression tests for dashboard/server security hardening.

Covers: legacy stdlib server auth + CORS removal + honest data + loopback-only
bind, container-log tail bounds, loopback-default CLI binding, and the
nonce-based Content-Security-Policy.
"""

import io
import json
import re
import subprocess

import pytest
import typer
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from moro.core.net import NonLoopbackBindError, check_bind_host, is_loopback_host
from moro.dashboard.mission_control import (
    CONTAINER_LOGS_MAX_TAIL,
    DockerConnector,
    app,
)

TOKEN = "hardening-regression-" + "c" * 32


# --------------------------------------------------------------------------
# Legacy stdlib server (moro.ui.server)
# --------------------------------------------------------------------------


@pytest.fixture
def legacy_env(monkeypatch, tmp_path):
    """Token in env, cwd outside any project: no socket needed."""
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    monkeypatch.chdir(tmp_path)


class _FakeSocket:
    """In-memory stand-in for the accepted connection socket."""

    def __init__(self, request_bytes: bytes):
        self._reader = io.BytesIO(request_bytes)
        self.output = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return self._reader
        return self.output

    def sendall(self, data: bytes):
        self.output.write(data)


def _handle(method, path, body=None, token=None):
    """Drive the real DashboardRequestHandler with in-memory HTTP."""
    from moro.ui.server import DashboardRequestHandler

    lines = [f"{method} {path} HTTP/1.1", "Host: 127.0.0.1"]
    if token is not None:
        lines.append(f"Authorization: Bearer {token}")
    raw_body = b""
    if body is not None:
        raw_body = json.dumps(body).encode()
        lines.append("Content-Type: application/json")
        lines.append(f"Content-Length: {len(raw_body)}")
    lines.append("Connection: close")
    request = ("\r\n".join(lines) + "\r\n\r\n").encode() + raw_body
    sock = _FakeSocket(request)
    DashboardRequestHandler(sock, ("127.0.0.1", 0), object())
    head, _, response_body = sock.output.getvalue().partition(b"\r\n\r\n")
    status_line, *header_lines = head.decode("latin-1").split("\r\n")
    status = int(status_line.split()[1])
    headers = dict(line.split(":", 1) for line in header_lines if ":" in line)
    return status, headers, response_body


def test_legacy_server_denies_unauthenticated_probes(legacy_env):
    assert _handle("GET", "/api/status")[0] == 401
    assert _handle("GET", "/api/project")[0] == 401
    assert _handle("GET", "/api/ollama/status")[0] == 401
    assert _handle("GET", "/")[0] == 401
    assert _handle("POST", "/api/guard/scan", {"text": "hi"})[0] == 401
    assert _handle("POST", "/api/ollama/chat", {"prompt": "hi"})[0] == 401
    assert _handle("GET", "/api/status", token="wrong-token")[0] == 401


def test_legacy_server_allows_valid_bearer_token(legacy_env):
    status, _, body = _handle("GET", "/api/status", token=TOKEN)
    assert status == 200
    assert json.loads(body)["pid"] > 0
    status, _, _ = _handle("GET", "/", token=TOKEN)
    assert status == 200


def test_legacy_server_sends_no_cors_headers(legacy_env):
    for method, path, body in [
        ("GET", "/api/status", None),
        ("GET", "/", None),
        ("POST", "/api/guard/scan", {"text": "hi"}),
        ("OPTIONS", "/api/status", None),
    ]:
        for token in (None, TOKEN):
            _, headers, _ = _handle(method, path, body, token=token)
            lowered = {k.strip().lower() for k in headers}
            assert "access-control-allow-origin" not in lowered


def test_legacy_server_returns_no_fabricated_samples(legacy_env):
    _, _, body = _handle("GET", "/api/project", token=TOKEN)
    state = json.loads(body)
    assert state["project_found"] is False
    assert state["config"] == {}
    assert state["sample_runs"] == []
    assert state["epistemic_metrics"] == {}
    assert state["dpo_flywheel"] == {"samples": []}
    assert "quantum_foundry" not in body.decode()


def test_legacy_services_drop_stale_entries():
    from moro.ui.server import get_local_services

    services = get_local_services()
    ports = {svc["port"] for svc in services}
    assert ports == {8501, 11434}
    assert ports.isdisjoint({5432, 54321, 54323, 54324, 55323, 55324})


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.10", "example.com", "::"])
def test_legacy_server_refuses_non_loopback_bind(host):
    from moro.ui.server import start_server

    with pytest.raises(ValueError, match="non-loopback"):
        start_server(host=host, port=0)


def test_legacy_server_allows_loopback_bind(monkeypatch):
    import moro.ui.server as legacy

    seen = {}

    class FakeServer:
        def __init__(self, address, handler):
            seen["address"] = address
            seen["handler"] = handler

    monkeypatch.setattr(legacy, "ThreadingHTTPServer", FakeServer)
    legacy.start_server(host="127.0.0.1", port=8501)
    assert seen["address"] == ("127.0.0.1", 8501)
    assert seen["handler"] is legacy.DashboardRequestHandler


# --------------------------------------------------------------------------
# Loopback-default binding (moro.core.net + CLI)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "127.0.0.2", "::1", "localhost", "LOCALHOST", "[::1]"]
)
def test_loopback_hosts_recognized(host):
    assert is_loopback_host(host) is True


@pytest.mark.parametrize(
    "host", ["0.0.0.0", "::", "192.168.1.1", "10.0.0.1", "example.com", "", "not a host"]
)
def test_non_loopback_hosts_recognized(host):
    assert is_loopback_host(host) is False


def test_bind_check_refuses_by_default_and_warns_on_override():
    with pytest.raises(NonLoopbackBindError):
        check_bind_host("0.0.0.0")
    with pytest.raises(NonLoopbackBindError):
        check_bind_host("0.0.0.0", allow_non_loopback=False)
    warning = check_bind_host("0.0.0.0", allow_non_loopback=True)
    assert "0.0.0.0" in warning
    assert check_bind_host("127.0.0.1") is None
    assert check_bind_host("localhost", allow_non_loopback=True) is None


def test_ui_command_refuses_non_loopback_by_default():
    from moro.cli.ui import ui_command

    cli = typer.Typer()
    cli.command("ui")(ui_command)
    result = CliRunner().invoke(cli, ["--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "Refused" in result.output


def test_ui_command_override_binds_with_warning(monkeypatch):
    import sys
    import types

    from moro.cli.ui import ui_command

    seen = {}
    fake_uvicorn = types.ModuleType("uvicorn")
    fake_uvicorn.run = lambda *args, **kwargs: seen.update({"args": args, "kwargs": kwargs})
    monkeypatch.setitem(sys.modules, "uvicorn", fake_uvicorn)
    cli = typer.Typer()
    cli.command("ui")(ui_command)
    result = CliRunner().invoke(cli, ["--host", "0.0.0.0", "--allow-non-loopback"])
    assert result.exit_code == 0, result.output
    assert "Warning" in result.output
    assert seen["kwargs"]["host"] == "0.0.0.0"


def test_dashboard_serve_refuses_non_loopback_by_default():
    from moro.cli.dashboard import dashboard_app

    result = CliRunner().invoke(dashboard_app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "Refused" in result.output


def test_dashboard_default_refuses_non_loopback_by_default():
    from moro.cli.dashboard import dashboard_app

    result = CliRunner().invoke(dashboard_app, ["--host", "0.0.0.0"])
    assert result.exit_code == 2
    assert "Refused" in result.output


def test_dashboard_serve_override_passes_bind_check(monkeypatch, tmp_path):
    """With the flag, binding is allowed; only the project check may fail."""
    from moro.cli.dashboard import dashboard_app

    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        dashboard_app, ["serve", "--host", "0.0.0.0", "--allow-non-loopback"]
    )
    assert "Refused" not in result.output
    assert "Project error" in result.output


def test_dashboard_docstring_no_longer_advertises_terminal():
    from moro.cli.dashboard import dashboard_serve

    assert "terminal" not in dashboard_serve.__doc__.lower()


# --------------------------------------------------------------------------
# Container-log tail bound (mission_control)
# --------------------------------------------------------------------------


@pytest.fixture
def secured(monkeypatch, tmp_path):
    monkeypatch.setenv("MORO_API_TOKEN", TOKEN)
    monkeypatch.setattr("moro.dashboard.mission_control.get_project_root", lambda: tmp_path)
    client = TestClient(app, base_url="http://127.0.0.1")
    client.headers["Authorization"] = f"Bearer {TOKEN}"
    return client


@pytest.mark.parametrize("tail", [CONTAINER_LOGS_MAX_TAIL + 1, 10**9, 0, -5, "many"])
def test_container_logs_rejects_out_of_range_tail(secured, tail):
    response = secured.get("/api/docker/containers/abcdef123456/logs", params={"tail": tail})
    assert response.status_code == 422


@pytest.mark.parametrize("tail", [1, 50, CONTAINER_LOGS_MAX_TAIL])
def test_container_logs_accepts_in_range_tail(secured, tail):
    response = secured.get("/api/docker/containers/abcdef123456/logs", params={"tail": tail})
    # 503 when Docker is unavailable, 200 otherwise; either proves validation passed.
    assert response.status_code in (200, 503)


def test_container_logs_default_tail_is_documented():
    from moro.dashboard.mission_control import CONTAINER_LOGS_DEFAULT_TAIL

    assert CONTAINER_LOGS_DEFAULT_TAIL == 100


def test_connector_clamps_tail_for_direct_callers(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"] = argv

        class Completed:
            stdout = "out"
            stderr = ""

        return Completed()

    monkeypatch.setattr(DockerConnector, "_is_managed", lambda self, cid: True)
    monkeypatch.setattr(subprocess, "run", fake_run)
    connector = DockerConnector()

    def tail_arg():
        argv = seen["argv"]
        return argv[argv.index("--tail") + 1]

    connector.get_container_logs("abcdef123456", 10**9)
    assert tail_arg() == str(CONTAINER_LOGS_MAX_TAIL)
    connector.get_container_logs("abcdef123456", -5)
    assert tail_arg() == "1"
    connector.get_container_logs("abcdef123456", 250)
    assert tail_arg() == "250"


# --------------------------------------------------------------------------
# Nonce-based Content-Security-Policy
# --------------------------------------------------------------------------


def _script_src(csp: str) -> str:
    return next(part for part in csp.split(";") if "script-src" in part)


def test_csp_uses_nonce_without_script_unsafe_inline(secured):
    response = secured.get("/api/health")
    assert response.status_code == 200
    csp = response.headers["content-security-policy"]
    assert "'nonce-" in csp
    assert "'unsafe-inline'" not in _script_src(csp)
    assert "http" not in csp.replace("'self'", "").replace("data:", "")


def test_dashboard_html_carries_matching_script_nonces(secured):
    response = secured.get("/")
    assert response.status_code == 200
    header_nonce = re.search(r"'nonce-([^']+)'", response.headers["content-security-policy"]).group(
        1
    )
    assert response.text.count(f'nonce="{header_nonce}"') == 6
    assert "<script>" not in response.text


def test_login_page_carries_csp_nonce(secured):
    response = secured.get("/login")
    assert response.status_code == 200
    header_nonce = re.search(r"'nonce-([^']+)'", response.headers["content-security-policy"]).group(
        1
    )
    assert f'<script nonce="{header_nonce}">' in response.text
