"""Tests for index MCP helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from redis_sre_agent.core.index_helpers import (
    _decode,
    _normalize_index_name,
    get_index_schema_status_helper,
    list_indices_helper,
    recreate_indices_helper,
    sync_index_schemas_helper,
)


class TestNormalizeIndexName:
    """Test index-name normalization logic."""

    def test_normalize_index_name_accepts_none_all_and_valid_names(self):
        assert _normalize_index_name(None) is None
        assert _normalize_index_name("all") is None
        assert _normalize_index_name("knowledge") == "knowledge"

    def test_normalize_index_name_rejects_invalid_names(self):
        with pytest.raises(ValueError, match="Invalid index_name"):
            _normalize_index_name("bogus")


class TestDecode:
    """Test value decoding helpers."""

    def test_decode_handles_bytes_strings_and_none(self):
        assert _decode(b"docs") == "docs"
        assert _decode("docs") == "docs"
        assert _decode(None) == ""


class TestListIndicesHelper:
    """Test index listing behavior."""

    @pytest.mark.asyncio
    async def test_list_indices_helper_collects_index_status(self):
        existing_idx = AsyncMock()
        existing_idx.exists = AsyncMock(return_value=True)
        existing_idx._redis_client.execute_command = AsyncMock(return_value=[b"num_docs", b"7"])
        existing_get = AsyncMock(return_value=existing_idx)

        missing_idx = AsyncMock()
        missing_idx.exists = AsyncMock(return_value=False)
        missing_get = AsyncMock(return_value=missing_idx)

        broken_get = AsyncMock(side_effect=RuntimeError("boom"))

        with patch(
            "redis_sre_agent.core.index_helpers._iter_index_configs",
            return_value=iter(
                [
                    ("knowledge", "idx:knowledge", existing_get, {}),
                    ("threads", "idx:threads", missing_get, {}),
                    ("tasks", "idx:tasks", broken_get, {}),
                ]
            ),
        ):
            result = await list_indices_helper()

        assert result == {
            "success": False,
            "requested_index": "all",
            "indices": [
                {
                    "name": "knowledge",
                    "index_name": "idx:knowledge",
                    "exists": True,
                    "num_docs": 7,
                },
                {
                    "name": "threads",
                    "index_name": "idx:threads",
                    "exists": False,
                    "num_docs": 0,
                },
                {
                    "name": "tasks",
                    "index_name": "idx:tasks",
                    "exists": False,
                    "error": "boom",
                },
            ],
        }

    @pytest.mark.asyncio
    async def test_list_indices_helper_handles_ft_info_errors(self):
        existing_idx = AsyncMock()
        existing_idx.exists = AsyncMock(return_value=True)
        existing_idx._redis_client.execute_command = AsyncMock(side_effect=RuntimeError("bad info"))
        existing_get = AsyncMock(return_value=existing_idx)
        config = MagicMock()

        with patch(
            "redis_sre_agent.core.index_helpers._iter_index_configs",
            return_value=iter([("knowledge", "idx:knowledge", existing_get, {})]),
        ):
            result = await list_indices_helper(index_name="knowledge", config=config)

        assert result == {
            "success": True,
            "requested_index": "knowledge",
            "indices": [
                {
                    "name": "knowledge",
                    "index_name": "idx:knowledge",
                    "exists": True,
                    "num_docs": "?",
                }
            ],
        }
        existing_get.assert_awaited_once_with(config=config)

    @pytest.mark.asyncio
    async def test_list_indices_helper_filters_to_requested_index(self):
        knowledge_idx = AsyncMock()
        knowledge_idx.exists = AsyncMock(return_value=False)
        knowledge_get = AsyncMock(return_value=knowledge_idx)
        skipped_get = AsyncMock()

        with patch(
            "redis_sre_agent.core.index_helpers._iter_index_configs",
            return_value=iter(
                [
                    ("knowledge", "idx:knowledge", knowledge_get, {}),
                    ("threads", "idx:threads", skipped_get, {}),
                ]
            ),
        ):
            result = await list_indices_helper(index_name="knowledge")

        assert result == {
            "success": True,
            "requested_index": "knowledge",
            "indices": [
                {
                    "name": "knowledge",
                    "index_name": "idx:knowledge",
                    "exists": False,
                    "num_docs": 0,
                }
            ],
        }
        knowledge_get.assert_awaited_once_with(config=None)
        skipped_get.assert_not_called()


class TestIndexOperationsHelpers:
    """Test schema/status/recreate/sync helper behavior."""

    @pytest.mark.asyncio
    async def test_get_index_schema_status_helper_delegates(self):
        with patch(
            "redis_sre_agent.core.index_helpers.get_index_schema_status",
            new_callable=AsyncMock,
        ) as mock_status:
            mock_status.return_value = {"success": True, "indices": {}}

            result = await get_index_schema_status_helper(index_name="all")

        assert result == {"success": True, "indices": {}}
        mock_status.assert_awaited_once_with(index_name=None, config=None)

    @pytest.mark.asyncio
    async def test_recreate_indices_helper_requires_confirmation(self):
        result = await recreate_indices_helper(index_name="knowledge", confirm=False)

        assert result == {
            "success": False,
            "status": "cancelled",
            "error": "Confirmation required",
            "index_name": "knowledge",
        }

    @pytest.mark.asyncio
    async def test_recreate_indices_helper_delegates(self):
        with patch(
            "redis_sre_agent.core.index_helpers.recreate_indices",
            new_callable=AsyncMock,
        ) as mock_recreate:
            mock_recreate.return_value = {"success": True, "indices": {"knowledge": "recreated"}}

            result = await recreate_indices_helper(index_name="knowledge", confirm=True)

        assert result == {"success": True, "indices": {"knowledge": "recreated"}}
        mock_recreate.assert_awaited_once_with(index_name="knowledge", config=None)

    @pytest.mark.asyncio
    async def test_sync_index_schemas_helper_requires_confirmation(self):
        result = await sync_index_schemas_helper(index_name="all", confirm=False)

        assert result == {
            "success": False,
            "status": "cancelled",
            "error": "Confirmation required",
            "index_name": "all",
        }

    @pytest.mark.asyncio
    async def test_sync_index_schemas_helper_delegates(self):
        with patch(
            "redis_sre_agent.core.index_helpers.sync_index_schemas",
            new_callable=AsyncMock,
        ) as mock_sync:
            mock_sync.return_value = {
                "success": True,
                "indices": {"knowledge": {"action": "created"}},
            }

            result = await sync_index_schemas_helper(index_name=None, confirm=True)

        assert result == {"success": True, "indices": {"knowledge": {"action": "created"}}}
        mock_sync.assert_awaited_once_with(index_name=None, config=None)
