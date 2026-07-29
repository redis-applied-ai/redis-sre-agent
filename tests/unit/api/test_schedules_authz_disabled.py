"""US-006: scheduling is disabled when infrastructure authorization is enabled.

Both halves are covered: creation/trigger surfaces refuse, and the scheduler execution loop
no-ops so a pre-existing schedule cannot fire unscoped. auth_status exposes the flag for the UI.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from redis_sre_agent.api.schedules import (
    create_schedule,
    trigger_schedule_now,
    update_schedule,
)
from redis_sre_agent.core.auth import auth_status
from redis_sre_agent.core.config import settings
from redis_sre_agent.core.docket_tasks import scheduler_task


@pytest.fixture
def authz_on(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)


async def test_create_schedule_refused_when_authz_on(authz_on):
    # Guard fires before touching the request body or Redis.
    with pytest.raises(HTTPException) as ei:
        await create_schedule(SimpleNamespace())
    assert ei.value.status_code == 400


async def test_trigger_schedule_refused_when_authz_on(authz_on):
    with pytest.raises(HTTPException) as ei:
        await trigger_schedule_now("sched-1")
    assert ei.value.status_code == 400


async def test_update_schedule_refused_when_authz_on(authz_on):
    # Modifying an existing schedule is a scheduling surface too -> refuse under authz (Bugbot).
    # Guard fires before touching the request body or Redis.
    with pytest.raises(HTTPException) as ei:
        await update_schedule("sched-1", SimpleNamespace())
    assert ei.value.status_code == 400


async def test_mcp_module_app_refuses_to_serve_when_authz_enabled(monkeypatch):
    # The module-level ASGI `app` (uvicorn ...:app) must also refuse under authz, not just
    # get_http_app(). The guard runs at ASGI startup/request time (Bugbot).
    from redis_sre_agent.mcp_server import server as mcp_server

    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)

    async def _noop(*a, **k):
        return {}

    for scope_type in ("lifespan", "http", "websocket"):
        with pytest.raises(RuntimeError):
            await mcp_server.app({"type": scope_type}, _noop, _noop)


async def test_scheduler_task_noops_when_authz_on(authz_on):
    result = await scheduler_task()
    assert result.get("status") == "skipped"
    assert result.get("reason") == "infrastructure_authorization_enabled"


def test_auth_status_exposes_authz_flag(authz_on):
    assert auth_status()["infrastructure_authorization_enabled"] is True


def test_auth_status_flag_false_by_default(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    assert auth_status()["infrastructure_authorization_enabled"] is False


def test_mcp_refuses_to_serve_when_authz_enabled(monkeypatch):
    # MCP has no authenticated principal this phase -> it must refuse to serve under authz
    # rather than run unscoped or silently fail-closed.
    from redis_sre_agent.mcp_server import server as mcp_server

    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", True)
    with pytest.raises(RuntimeError):
        mcp_server._refuse_if_authz_enabled()

    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    mcp_server._refuse_if_authz_enabled()  # authz off -> serves normally (no raise)
