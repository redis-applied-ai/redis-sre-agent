"""Integration tests for runtime_agent hosted AFS MCP wiring."""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest


def _runtime_agent_path() -> Path:
    return Path(__file__).resolve().parents[2] / "runtime_agent.py"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _afs_repo_root() -> Path:
    return _repo_root().parent / "agent-filesystem"


def _load_runtime_agent_module():
    module_path = _runtime_agent_path()
    spec = importlib.util.spec_from_file_location("runtime_agent_afs_integration_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _redis_connection_info(redis_url: str) -> tuple[str, str, str, int, bool]:
    parsed = urlparse(redis_url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 6379
    username = parsed.username or ""
    password = parsed.password or ""
    db = int((parsed.path or "/0").lstrip("/") or "0")
    tls = parsed.scheme == "rediss"
    return f"{host}:{port}", username, password, db, tls


def _write_afs_config(config_path: Path, *, redis_url: str) -> None:
    redis_addr, username, password, db, tls = _redis_connection_info(redis_url)
    payload = {
        "redis": {
            "addr": redis_addr,
            "username": username,
            "password": password,
            "db": db,
            "tls": tls,
        },
        "mode": "none",
        "currentWorkspace": "",
        "localPath": "",
        "mount": {
            "backend": "none",
            "readOnly": False,
            "allowOther": False,
            "mountBin": "",
            "nfsBin": "",
            "nfsHost": "127.0.0.1",
            "nfsPort": 20490,
        },
        "logs": {
            "mount": "/tmp/afs-mount.log",
            "sync": "/tmp/afs-sync.log",
        },
        "sync": {
            "fileSizeCapMB": 100,
        },
    }
    config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _unused_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Emitter:
    async def emit_async(self, *args, **kwargs) -> None:
        return None

    async def emit_tool_call_async(self, *args, **kwargs) -> None:
        return None


@pytest.fixture(scope="session")
def afs_control_plane_binary(tmp_path_factory: pytest.TempPathFactory) -> Path:
    output_dir = tmp_path_factory.mktemp("afs-control-plane-build")
    binary_path = output_dir / "afs-control-plane"
    subprocess.run(
        ["go", "build", "-o", str(binary_path), "./cmd/afs-control-plane"],
        cwd=_afs_repo_root(),
        check=True,
        capture_output=True,
        text=True,
    )
    return binary_path


@pytest.fixture
def afs_hosted_mcp(
    redis_url: str,
    afs_control_plane_binary: Path,
    tmp_path: Path,
):
    workspace_id = f"runtime-afs-{uuid4().hex[:8]}"
    afs_config_path = tmp_path / "afs.config.json"
    _write_afs_config(afs_config_path, redis_url=redis_url)
    redis_addr, redis_username, redis_password, redis_db, redis_tls = _redis_connection_info(
        redis_url
    )
    port = _unused_local_port()
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "AFS_AUTH_MODE": "trusted-header",
            "AFS_AUTH_TRUSTED_USER_HEADER": "X-Forwarded-User",
            "AFS_AUTH_TRUSTED_NAME_HEADER": "X-Forwarded-Name",
            "AFS_REDIS_ADDR": redis_addr,
            "AFS_REDIS_USERNAME": redis_username,
            "AFS_REDIS_PASSWORD": redis_password,
            "AFS_REDIS_DB": str(redis_db),
            "AFS_REDIS_TLS": "true" if redis_tls else "false",
        }
    )
    process = subprocess.Popen(
        [
            str(afs_control_plane_binary),
            "--listen",
            f"127.0.0.1:{port}",
            "--config",
            str(afs_config_path),
        ],
        cwd=_afs_repo_root(),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    health_url = f"http://127.0.0.1:{port}/healthz"
    deadline = time.time() + 30
    last_error = ""
    while time.time() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=5)
            raise RuntimeError(
                f"AFS control plane exited early with code {process.returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}"
            )
        try:
            response = httpx.get(health_url, timeout=1.0)
            if response.status_code == 200:
                break
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = str(exc)
        time.sleep(0.25)
    else:  # pragma: no cover - diagnostic path
        process.terminate()
        stdout, stderr = process.communicate(timeout=5)
        raise RuntimeError(
            f"AFS control plane did not become healthy: {last_error}\nstdout:\n{stdout}\nstderr:\n{stderr}"
        )

    workspace_response = httpx.post(
        f"http://127.0.0.1:{port}/v1/workspaces",
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-User": "runtime@example.com",
            "X-Forwarded-Name": "Runtime Test",
        },
        json={"name": workspace_id},
        timeout=10.0,
    )
    workspace_response.raise_for_status()

    token_response = httpx.post(
        f"http://127.0.0.1:{port}/v1/workspaces/{workspace_id}/mcp-tokens",
        headers={
            "Content-Type": "application/json",
            "X-Forwarded-User": "runtime@example.com",
            "X-Forwarded-Name": "Runtime Test",
        },
        json={"name": "Redis SRE runtime", "readonly": False},
        timeout=10.0,
    )
    token_response.raise_for_status()
    token_payload = token_response.json()
    token = token_payload["token"]

    yield SimpleNamespace(
        url=f"http://127.0.0.1:{port}/mcp",
        token=token,
        workspace_id=workspace_id,
        process=process,
    )

    process.terminate()
    try:
        process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=10)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_runtime_agent_dispatches_hosted_afs_file_tools(
    monkeypatch: pytest.MonkeyPatch,
    afs_hosted_mcp,
) -> None:
    monkeypatch.setenv(
        "SRE_AGENT_CONFIG",
        str(_repo_root() / "tmp/redis-sre-agent/config.runtime.yaml"),
    )
    monkeypatch.setenv("RAR_RUNTIME_AFS_MCP_URL", afs_hosted_mcp.url)
    monkeypatch.setenv("RAR_RUNTIME_AFS_MCP_TOKEN", afs_hosted_mcp.token)

    import redis_sre_agent.core.config as config_module

    importlib.reload(config_module)
    module = _load_runtime_agent_module()
    module._REDIS_BOOTSTRAP_COMPLETE = True

    emitter = _Emitter()

    current = await module.runtime_sre_agent({"tool": "workspace_current", "arguments": {}}, emitter)
    assert current["mode"] == "mcp"
    assert current["result"]["status"] == "success"
    assert current["result"]["data"]["workspace"] == afs_hosted_mcp.workspace_id
    assert current["result"]["data"]["readonly"] is False
    assert current["result"]["data"]["database"]

    content = "# TODO\n- wire hosted AFS MCP\n"
    write_result = await module.runtime_sre_agent(
        {
            "tool": "file_write",
            "arguments": {"path": "/notes/todo.md", "content": content},
        },
        emitter,
    )
    assert write_result["result"]["status"] == "success"
    assert write_result["result"]["data"]["path"] == "/notes/todo.md"
    assert write_result["result"]["data"]["workspace"] == afs_hosted_mcp.workspace_id
    assert write_result["result"]["data"]["created"] is True
    assert write_result["result"]["data"]["bytes"] == len(content)

    read_result = await module.runtime_sre_agent(
        {"tool": "file_read", "arguments": {"path": "/notes/todo.md"}},
        emitter,
    )
    assert read_result["result"]["status"] == "success"
    assert read_result["result"]["data"]["path"] == "/notes/todo.md"
    assert read_result["result"]["data"]["workspace"] == afs_hosted_mcp.workspace_id
    assert read_result["result"]["data"]["content"] == content
