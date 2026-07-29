"""US-006: scheduling is disabled when infrastructure authorization is enabled.

Both halves are covered: creation/trigger surfaces refuse, and the scheduler execution loop
no-ops so a pre-existing schedule cannot fire unscoped. auth_status exposes the flag for the UI.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from redis_sre_agent.api.schedules import create_schedule, trigger_schedule_now
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


async def test_scheduler_task_noops_when_authz_on(authz_on):
    result = await scheduler_task()
    assert result.get("status") == "skipped"
    assert result.get("reason") == "infrastructure_authorization_enabled"


def test_auth_status_exposes_authz_flag(authz_on):
    assert auth_status()["infrastructure_authorization_enabled"] is True


def test_auth_status_flag_false_by_default(monkeypatch):
    monkeypatch.setattr(settings, "infrastructure_authorization_enabled", False)
    assert auth_status()["infrastructure_authorization_enabled"] is False
