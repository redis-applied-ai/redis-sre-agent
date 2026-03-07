"""Unit tests for target context validation helpers."""

from unittest.mock import AsyncMock

import pytest

from redis_sre_agent.core.target_context import (
    TurnTarget,
    extract_turn_target,
    require_at_most_one_target,
    require_continuation_target_compatibility,
    require_exactly_one_target_for_new_turn,
)


def test_extract_turn_target_normalizes_ids():
    target = extract_turn_target({"instance_id": " inst-1 ", "cluster_id": " "})
    assert target.instance_id == "inst-1"
    assert target.cluster_id is None


def test_require_at_most_one_target_rejects_both():
    with pytest.raises(ValueError, match="Provide only one target"):
        require_at_most_one_target(TurnTarget(instance_id="inst-1", cluster_id="cluster-1"))


def test_require_exactly_one_target_for_new_turn_requires_target():
    with pytest.raises(ValueError, match="New turns require exactly one target"):
        require_exactly_one_target_for_new_turn(TurnTarget(instance_id=None, cluster_id=None))


@pytest.mark.asyncio
async def test_continuation_accepts_no_provided_target():
    await require_continuation_target_compatibility(
        provided_target=TurnTarget(instance_id=None, cluster_id=None),
        thread_target=TurnTarget(instance_id="inst-1", cluster_id=None),
        get_instance_by_id=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_continuation_rejects_target_injection_for_untargeted_thread():
    with pytest.raises(ValueError, match="Thread has no saved target context"):
        await require_continuation_target_compatibility(
            provided_target=TurnTarget(instance_id="inst-1", cluster_id=None),
            thread_target=TurnTarget(instance_id=None, cluster_id=None),
            get_instance_by_id=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_continuation_accepts_matching_instance():
    await require_continuation_target_compatibility(
        provided_target=TurnTarget(instance_id="inst-1", cluster_id=None),
        thread_target=TurnTarget(instance_id="inst-1", cluster_id=None),
        get_instance_by_id=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_continuation_rejects_mismatched_instance():
    with pytest.raises(ValueError, match="instance_id=inst-1"):
        await require_continuation_target_compatibility(
            provided_target=TurnTarget(instance_id="inst-2", cluster_id=None),
            thread_target=TurnTarget(instance_id="inst-1", cluster_id=None),
            get_instance_by_id=AsyncMock(),
        )


@pytest.mark.asyncio
async def test_continuation_accepts_instance_for_thread_cluster():
    inst = type("Inst", (), {"cluster_id": "cluster-1"})()
    await require_continuation_target_compatibility(
        provided_target=TurnTarget(instance_id="inst-9", cluster_id=None),
        thread_target=TurnTarget(instance_id=None, cluster_id="cluster-1"),
        get_instance_by_id=AsyncMock(return_value=inst),
    )


@pytest.mark.asyncio
async def test_continuation_rejects_instance_for_mismatched_thread_cluster():
    inst = type("Inst", (), {"cluster_id": "cluster-2"})()
    with pytest.raises(ValueError, match="not linked to thread cluster_id=cluster-1"):
        await require_continuation_target_compatibility(
            provided_target=TurnTarget(instance_id="inst-9", cluster_id=None),
            thread_target=TurnTarget(instance_id=None, cluster_id="cluster-1"),
            get_instance_by_id=AsyncMock(return_value=inst),
        )


@pytest.mark.asyncio
async def test_continuation_accepts_cluster_for_thread_instance():
    inst = type("Inst", (), {"cluster_id": "cluster-1"})()
    await require_continuation_target_compatibility(
        provided_target=TurnTarget(instance_id=None, cluster_id="cluster-1"),
        thread_target=TurnTarget(instance_id="inst-1", cluster_id=None),
        get_instance_by_id=AsyncMock(return_value=inst),
    )


@pytest.mark.asyncio
async def test_continuation_rejects_cluster_for_mismatched_thread_instance():
    inst = type("Inst", (), {"cluster_id": "cluster-2"})()
    with pytest.raises(ValueError, match="does not match thread instance_id=inst-1"):
        await require_continuation_target_compatibility(
            provided_target=TurnTarget(instance_id=None, cluster_id="cluster-1"),
            thread_target=TurnTarget(instance_id="inst-1", cluster_id=None),
            get_instance_by_id=AsyncMock(return_value=inst),
        )
