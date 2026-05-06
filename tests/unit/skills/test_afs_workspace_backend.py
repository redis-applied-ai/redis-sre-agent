"""Tests for the runtime-backed AFS workspace skill backend."""

from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest

from redis_sre_agent.skills.afs_workspace_backend import (
    AFSWorkspaceSkillBackend,
    _parse_event_stream_payload,
)


class _FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code
        self.request = httpx.Request("GET", "https://skills.internal")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad status", request=self.request, response=httpx.Response(self.status_code))

    def json(self) -> object:
        return self._payload


class _FakeAsyncClient:
    def __init__(self, *, responses: list[_FakeResponse], **kwargs: object) -> None:
        self.responses = responses
        self.kwargs = kwargs
        self.calls: list[tuple[str, str, object | None]] = []

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        return None

    async def request(self, method: str, path: str, params: object | None = None) -> _FakeResponse:
        self.calls.append((method, path, params))
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_afs_workspace_skill_backend_list_get_and_resource() -> None:
    responses = [
        _FakeResponse(
            {
                "data": {
                    "skills": [
                        {
                            "skillSlug": "redis-maintenance-triage",
                            "displayName": "Redis Maintenance Triage",
                            "description": "Check maintenance mode first.",
                            "version": "v1",
                            "resources": [{"path": "references/checklist.md"}],
                        }
                    ],
                    "total": 1,
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "skill": {
                        "skillSlug": "redis-maintenance-triage",
                        "displayName": "Redis Maintenance Triage",
                        "description": "Check maintenance mode first.",
                        "version": "v1",
                        "entrypoint": {"path": "SKILL.md", "content": "# Triage\n"},
                        "resources": [
                            {"path": "references/checklist.md", "kind": "reference"},
                            {"path": "scripts/collect.sh", "kind": "script"},
                        ],
                    }
                }
            }
        ),
        _FakeResponse(
            {
                "data": {
                    "resource": {
                        "path": "references/checklist.md",
                        "version": "v1",
                        "content": "Checklist guidance\n",
                    }
                }
            }
        ),
    ]
    client = _FakeAsyncClient(responses=responses)
    backend = AFSWorkspaceSkillBackend(
        base_url="https://skills.internal",
        tenant_id="tenant_a",
        project_id="proj_1",
        agent_id="agent_1",
        client_factory=lambda **kwargs: client,  # type: ignore[arg-type]
    )

    listed = await backend.list_skills(query=None, limit=10, offset=0, version="latest")
    assert listed["results_count"] == 1
    assert listed["skills"][0]["name"] == "redis-maintenance-triage"

    loaded = await backend.get_skill(skill_name="redis-maintenance-triage", version="v1")
    assert loaded["content"] == "# Triage\n"
    assert loaded["references"][0]["path"] == "references/checklist.md"

    resource = await backend.get_skill_resource(
        skill_name="redis-maintenance-triage",
        resource_path="references/checklist.md",
        version="v1",
    )
    assert resource["content"] == "Checklist guidance\n"


@pytest.mark.asyncio
async def test_afs_workspace_skill_backend_query_and_error_paths() -> None:
    responses = [
        _FakeResponse(
            {
                "data": {
                    "skills": [
                        {
                            "skillSlug": "redis-maintenance-triage",
                            "displayName": "Redis Maintenance Triage",
                            "description": "Check maintenance mode first.",
                            "version": "v1",
                            "resources": [],
                        }
                    ],
                    "matches": [
                        {
                            "skillSlug": "redis-maintenance-triage",
                            "version": "v1",
                            "path": "/skills/redis-maintenance-triage/versions/v1/references/checklist.md",
                        }
                    ],
                }
            }
        ),
        _FakeResponse({"error": "missing"}, status_code=404),
        _FakeResponse({"error": "missing"}, status_code=404),
    ]
    client = _FakeAsyncClient(responses=responses)
    backend = AFSWorkspaceSkillBackend(
        base_url="https://skills.internal",
        tenant_id="tenant_a",
        project_id="proj_1",
        agent_id="agent_1",
        skill_reference_char_budget=5,
        client_factory=lambda **kwargs: client,  # type: ignore[arg-type]
    )

    queried = await backend.list_skills(query="checklist", limit=10, offset=0, version="v1")
    assert queried["skills"][0]["matched_resource_kind"] == "reference"

    missing_skill = await backend.get_skill(skill_name="missing", version="v1")
    assert missing_skill["error"] == "Skill not found"

    missing_resource = await backend.get_skill_resource(
        skill_name="missing",
        resource_path="references/checklist.md",
        version="v1",
    )
    assert missing_resource["error"] == "Skill resource not found"


def test_afs_workspace_skill_backend_from_settings_uses_env_fallbacks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAR_SKILLS_API_BASE_URL", "https://skills.internal")
    monkeypatch.setenv("RAR_SKILLS_API_TENANT_ID", "tenant_a")
    monkeypatch.setenv("RAR_SKILLS_API_PROJECT_ID", "proj_1")
    monkeypatch.setenv("RAR_SKILLS_API_AGENT_ID", "agent_1")
    monkeypatch.setenv("RAR_SKILLS_API_TOKEN", "secret")
    monkeypatch.setenv("RAR_SKILLS_API_TIMEOUT_SECONDS", "9.5")

    backend = AFSWorkspaceSkillBackend.from_settings(
        SimpleNamespace(skill_reference_char_budget=42)
    )

    assert backend.base_url == "https://skills.internal"
    assert backend.timeout_seconds == 9.5
    assert backend.bearer_token == "secret"


def test_afs_workspace_skill_backend_from_settings_uses_runtime_env_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAK_API_BASE_URL", "https://agent-runtime.redisvl.com")
    monkeypatch.setenv("RAK_TENANT_ID", "tenant_local")
    monkeypatch.setenv("RAK_PROJECT_ID", "proj_runtime")
    monkeypatch.setenv("RAK_SELF_AGENT_ID", "agent_runtime")
    monkeypatch.setenv("RAK_API_TOKEN", "runtime-token")

    backend = AFSWorkspaceSkillBackend.from_settings(
        SimpleNamespace(skill_reference_char_budget=42)
    )

    assert backend.base_url == "https://agent-runtime.redisvl.com"
    assert backend.tenant_id == "tenant_local"
    assert backend.project_id == "proj_runtime"
    assert backend.agent_id == "agent_runtime"
    assert backend.bearer_token == "runtime-token"


def test_afs_workspace_skill_backend_gateway_endpoint_appends_mcp_once() -> None:
    backend = AFSWorkspaceSkillBackend(
        base_url="https://skills.internal",
        tenant_id="tenant_a",
        project_id="proj_1",
        agent_id="agent_1",
        gateway_url="https://gateway.internal/mcp",
        gateway_token="secret",
        workspace_id="skills-proj-1-agent-1",
    )

    assert backend._gateway_endpoint() == "https://gateway.internal/mcp"


def test_afs_workspace_skill_backend_gateway_endpoint_adds_missing_suffix() -> None:
    backend = AFSWorkspaceSkillBackend(
        base_url="https://skills.internal",
        tenant_id="tenant_a",
        project_id="proj_1",
        agent_id="agent_1",
        gateway_url="https://gateway.internal",
        gateway_token="secret",
        workspace_id="skills-proj-1-agent-1",
    )

    assert backend._gateway_endpoint() == "https://gateway.internal/mcp"


def test_parse_event_stream_payload_extracts_jsonrpc_object() -> None:
    payload = _parse_event_stream_payload(
        'event: message\n'
        'data: {"jsonrpc":"2.0","id":"1","result":{"ok":true}}\n'
        "\n"
    )

    assert payload["result"]["ok"] is True
