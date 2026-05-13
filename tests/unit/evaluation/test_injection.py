from contextlib import AsyncExitStack
from unittest.mock import AsyncMock, patch

import pytest

from redis_sre_agent.agent.knowledge_context import build_startup_knowledge_context
from redis_sre_agent.core.config import MCPServerConfig
from redis_sre_agent.core.knowledge_helpers import (
    get_pinned_documents_helper,
    get_related_document_fragments,
    search_knowledge_base_helper,
)
from redis_sre_agent.evaluation.injection import (
    eval_injection_scope,
    get_active_knowledge_backend,
    get_active_mcp_servers,
)
from redis_sre_agent.tools.manager import ToolManager
from redis_sre_agent.tools.models import Tool, ToolCapability, ToolDefinition, ToolMetadata


class _FakeKnowledgeBackend:
    async def search_knowledge_base(self, **kwargs):
        return {
            "query": kwargs["query"],
            "results": [{"id": "fixture-doc"}],
            "results_count": 1,
            "backend": "eval-fixture",
        }

    async def skills_check(self, **kwargs):
        return {
            "skills": [
                {
                    "name": "maintenance-mode-skill",
                    "summary": "Check cluster maintenance mode before failover triage.",
                }
            ],
            "backend": "eval-fixture",
        }

    async def get_skill(self, **kwargs):
        return {"skill_name": kwargs["skill_name"], "full_content": "skill content"}

    async def search_support_tickets(self, **kwargs):
        return {"tickets": [{"ticket_id": "RET-4421"}], "backend": "eval-fixture"}

    async def get_support_ticket(self, **kwargs):
        return {"ticket_id": kwargs["ticket_id"], "full_content": "ticket content"}

    async def get_pinned_documents(self, **kwargs):
        return {
            "results_count": 1,
            "pinned_documents": [
                {
                    "document_hash": "fixture-doc",
                    "name": "maintenance-runbook",
                    "priority": "high",
                    "doc_type": "runbook",
                    "full_content": "Check maintenance mode first.",
                    "summary": "Runbook summary",
                    "source": "redis.io",
                }
            ],
            "backend": "eval-fixture",
        }

    async def get_all_document_fragments(self, **kwargs):
        return {"document_hash": kwargs["document_hash"], "fragments": []}

    async def get_related_document_fragments(self, **kwargs):
        return {"document_hash": kwargs["document_hash"], "fragments": []}


class _FakeMCPProvider:
    def __init__(self, server_name, server_config, redis_instance=None, use_pool=True):
        self.provider_name = f"mcp_{server_name}"
        self.server_name = server_name
        self.server_config = server_config
        self.redis_instance = redis_instance
        self.use_pool = use_pool

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def tools(self):
        tool_name = f"mcp_{self.server_name}_query_metrics"
        return [
            Tool(
                metadata=ToolMetadata(
                    name=tool_name,
                    description="query",
                    capability=ToolCapability.METRICS,
                    provider_name=self.provider_name,
                ),
                definition=ToolDefinition(
                    name=tool_name,
                    description="query",
                    capability=ToolCapability.METRICS,
                    parameters={"type": "object", "properties": {}},
                ),
                invoke=AsyncMock(return_value={"ok": True}),
            )
        ]


def test_eval_injection_scope_restores_previous_state():
    backend = _FakeKnowledgeBackend()
    default_catalog = {"global": MCPServerConfig(url="https://global.example/mcp")}

    assert get_active_knowledge_backend() is None
    assert get_active_mcp_servers(default_catalog) == default_catalog

    with eval_injection_scope(
        knowledge_backend=backend,
        mcp_servers={"eval": MCPServerConfig(url="https://eval.example/mcp")},
    ):
        assert get_active_knowledge_backend() is backend
        assert list(get_active_mcp_servers(default_catalog)) == ["eval"]

    assert get_active_knowledge_backend() is None
    assert get_active_mcp_servers(default_catalog) == default_catalog


def test_eval_injection_scope_leaves_global_mcp_settings_unchanged(monkeypatch):
    from redis_sre_agent.core.config import settings

    original = dict(settings.mcp_servers)
    monkeypatch.setattr(
        settings,
        "mcp_servers",
        {"github": MCPServerConfig(url="https://github.example/mcp")},
    )

    with eval_injection_scope(
        mcp_servers={"eval": MCPServerConfig(url="https://eval.example/mcp")}
    ):
        assert list(settings.mcp_servers) == ["github"]
        assert list(get_active_mcp_servers(settings.mcp_servers)) == ["eval"]

    assert list(settings.mcp_servers) == ["github"]
    monkeypatch.setattr(settings, "mcp_servers", original)


@pytest.mark.asyncio
async def test_knowledge_helpers_dispatch_to_eval_backend():
    with eval_injection_scope(knowledge_backend=_FakeKnowledgeBackend()):
        with patch(
            "redis_sre_agent.core.knowledge_helpers.get_vectorizer",
            side_effect=AssertionError("global vectorizer should not be used"),
        ):
            search_result = await search_knowledge_base_helper(query="memory pressure")
            pinned_result = await get_pinned_documents_helper()

    assert search_result["backend"] == "eval-fixture"
    assert search_result["results"][0]["id"] == "fixture-doc"
    assert pinned_result["backend"] == "eval-fixture"
    assert pinned_result["pinned_documents"][0]["document_hash"] == "fixture-doc"


@pytest.mark.asyncio
async def test_startup_context_uses_eval_knowledge_backend():
    with eval_injection_scope(knowledge_backend=_FakeKnowledgeBackend()):
        context = await build_startup_knowledge_context(
            available_tools=[],
        )

    assert "Pinned documents:" in context
    assert "Check maintenance mode first." in context
    assert "Skills you know:" in context
    assert "maintenance-mode-skill" in context


@pytest.mark.asyncio
async def test_related_fragments_dispatch_uses_helper_parameter_names():
    class StrictKnowledgeBackend(_FakeKnowledgeBackend):
        async def get_related_document_fragments(
            self,
            *,
            document_hash: str,
            current_chunk_index: int | None = None,
            context_window: int = 2,
            version: str | None = "latest",
            index_type: str = "knowledge",
        ):
            return {
                "document_hash": document_hash,
                "current_chunk_index": current_chunk_index,
                "context_window": context_window,
                "version": version,
                "index_type": index_type,
            }

    with eval_injection_scope(knowledge_backend=StrictKnowledgeBackend()):
        result = await get_related_document_fragments(
            document_hash="fixture-doc",
            current_chunk_index=4,
            context_window=3,
            version="7.8",
            index_type="skills",
        )

    assert result == {
        "document_hash": "fixture-doc",
        "current_chunk_index": 4,
        "context_window": 3,
        "version": "7.8",
        "index_type": "skills",
    }


@pytest.mark.asyncio
async def test_tool_manager_uses_eval_mcp_overrides_without_pool():
    mgr = ToolManager()
    mgr._stack = AsyncExitStack()
    await mgr._stack.__aenter__()
    try:
        with (
            patch("redis_sre_agent.core.config.settings") as mock_settings,
            patch(
                "redis_sre_agent.tools.mcp.provider.MCPToolProvider",
                new=_FakeMCPProvider,
            ),
            eval_injection_scope(
                mcp_servers={"metrics_eval": MCPServerConfig(url="http://fixture-mcp.invalid")}
            ),
        ):
            mock_settings.mcp_servers = {}
            await mgr._load_mcp_providers()

        assert "mcp_metrics_eval_query_metrics" in mgr._routing_table
        provider = mgr._routing_table["mcp_metrics_eval_query_metrics"]
        assert provider.server_name == "metrics_eval"
        assert provider.use_pool is False
    finally:
        await mgr._stack.__aexit__(None, None, None)
