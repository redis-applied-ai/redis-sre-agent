"""Unit tests for RedisKeys key construction utilities."""

from redis_sre_agent.core.keys import RedisKeys


def test_feedback_task_key_shape():
    """feedback_task returns the expected key string."""
    task_id = "01HXYZK7A3PMQX5N9V8RWHTJDF"
    assert RedisKeys.feedback_task(task_id) == "sre:feedback:task:01HXYZK7A3PMQX5N9V8RWHTJDF"


def test_feedback_task_is_static():
    """feedback_task is callable without instantiation."""
    key = RedisKeys.feedback_task("abc")
    assert key == "sre:feedback:task:abc"
