import pytest
from click.testing import CliRunner


class FakeRedis:
    def __init__(self, entries: dict[str, dict[str, str]] | None = None):
        self.entries = entries or {}
        self.deleted: list[str] = []
        self.zrems: list[tuple[str, str]] = []

    async def scan(self, cursor: int = 0, match: str | None = None, count: int = 10):
        prefix = match[:-1] if match and match.endswith("*") else match
        keys = [k for k in self.entries if (prefix is None or k.startswith(prefix))]
        # Return all at once with cursor=0 to finish
        return 0, keys

    async def hmget(self, key: str, *fields: str):
        data = self.entries.get(key, {})
        return [data.get(f) for f in fields]

    async def hget(self, key: str, field: str):
        data = self.entries.get(key, {})
        return data.get(field)

    async def hgetall(self, key: str):
        return self.entries.get(key, {})

    async def delete(self, key: str):
        self.deleted.append(key)
        # simulate deletion from entries map if present
        self.entries.pop(key, None)
        return 1

    async def zrem(self, key: str, member: str):
        self.zrems.append((key, member))
        return 1

    async def zrevrange(self, key: str, start: int, end: int):
        # Not used in tests (we pass --no-include-tasks)
        return []


class FakeThreadManager:
    instances: list["FakeThreadManager"] = []

    def __init__(self, redis_client=None):
        self._redis = redis_client
        self.deleted_ids: list[str] = []
        FakeThreadManager.instances.append(self)

    async def _get_client(self):
        return self._redis

    async def delete_thread(self, thread_id: str) -> bool:
        self.deleted_ids.append(thread_id)
        return True


def test_task_purge_all_yes_uses_delete_task(monkeypatch):
    from redis_sre_agent.cli import tasks as tasks_mod

    fake = FakeRedis(
        {
            "sre_tasks:t1": {"status": "done", "updated_at": "100", "created_at": "50"},
            "sre_tasks:t2": {"status": "failed", "updated_at": "200", "created_at": "100"},
        }
    )

    calls: list[str] = []

    async def fake_delete_task(*, task_id: str, redis_client=None):
        calls.append(task_id)

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr("redis_sre_agent.core.tasks.delete_task", fake_delete_task)

    runner = CliRunner()
    result = runner.invoke(tasks_mod.task, ["purge", "--all", "-y"])

    assert result.exit_code == 0
    assert set(calls) == {"t1", "t2"}


def test_task_purge_guard_messages(monkeypatch):
    from redis_sre_agent.cli import tasks as tasks_mod

    runner = CliRunner()

    # No scope
    result = runner.invoke(tasks_mod.task, ["purge"])
    assert result.exit_code == 0
    assert "Refusing to purge" in result.output

    # Scope provided but no confirmation
    result2 = runner.invoke(tasks_mod.task, ["purge", "--status", "done"])
    assert result2.exit_code == 0
    assert "You are about to delete" in result2.output


def test_thread_purge_all_yes_no_include_tasks(monkeypatch):
    from redis_sre_agent.cli import threads as threads_mod

    fake_redis = FakeRedis(
        {
            "sre_threads:th1": {"created_at": "100"},
            "sre_threads:th2": {"created_at": "200"},
        }
    )

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("redis_sre_agent.core.threads.ThreadManager", FakeThreadManager)

    runner = CliRunner()
    result = runner.invoke(threads_mod.thread, ["purge", "--all", "-y", "--no-include-tasks"])

    assert result.exit_code == 0
    # One FakeThreadManager instance used
    assert FakeThreadManager.instances, "ThreadManager was not instantiated"
    tm = FakeThreadManager.instances[-1]
    assert set(tm.deleted_ids) == {"th1", "th2"}
    # FT docs removed
    assert set(fake_redis.deleted) == {"sre_threads:th1", "sre_threads:th2"}


def test_thread_purge_guard_messages():
    from redis_sre_agent.cli import threads as threads_mod

    runner = CliRunner()

    # No scope
    result = runner.invoke(threads_mod.thread, ["purge"])
    assert result.exit_code == 0
    assert "Refusing to purge" in result.output

    # Scope provided but no confirmation
    result2 = runner.invoke(threads_mod.thread, ["purge", "--older-than", "7d"])
    assert result2.exit_code == 0
    assert "You are about to delete" in result2.output


@pytest.mark.asyncio
async def test_core_delete_task_deletes_kv_and_zrem(monkeypatch):
    from redis_sre_agent.core.keys import RedisKeys
    from redis_sre_agent.core.tasks import delete_task

    t_id = "t123"
    th_id = "th123"
    fake = FakeRedis({RedisKeys.task_metadata(t_id): {"thread_id": th_id}})

    await delete_task(task_id=t_id, redis_client=fake)

    # KV keys deleted
    expected_deleted = {
        RedisKeys.task_status(t_id),
        RedisKeys.task_updates(t_id),
        RedisKeys.task_result(t_id),
        RedisKeys.task_error(t_id),
        RedisKeys.task_metadata(t_id),
        # FT doc also deleted (prefix fixed in core)
        f"sre_tasks:{t_id}",
    }
    assert set(fake.deleted) == expected_deleted
    # zrem from thread task index
    assert (RedisKeys.thread_tasks_index(th_id), t_id) in fake.zrems


def test_task_purge_status_and_age_dry_run_filters(monkeypatch):
    from redis_sre_agent.cli import tasks as tasks_mod

    # t1 is done and old; t2 is in_progress; only t1 should be selected
    fake = FakeRedis(
        {
            "sre_tasks:t1": {"status": "done", "updated_at": "1", "created_at": "0"},
            "sre_tasks:t2": {
                "status": "in_progress",
                "updated_at": "9999999999",
                "created_at": "9999999999",
            },
        }
    )

    # Ensure delete_task is not called on dry-run
    called = {"count": 0}

    async def fake_delete_task(*, task_id: str, redis_client=None):
        called["count"] += 1

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr("redis_sre_agent.core.tasks.delete_task", fake_delete_task)

    runner = CliRunner()
    result = runner.invoke(
        tasks_mod.task,
        ["purge", "--status", "done", "--older-than", "7d", "--dry-run"],
    )

    assert result.exit_code == 0
    assert called["count"] == 0
    assert "Would delete" in result.output


def test_thread_purge_includes_tasks(monkeypatch):
    from redis_sre_agent.cli import threads as threads_mod

    class FakeRedisWithZ(FakeRedis):
        async def zrevrange(self, key: str, start: int, end: int):
            # Always return two task ids
            return ["t1", "t2"]

    fake_redis = FakeRedisWithZ({"sre_threads:th1": {"created_at": "0"}})

    deletes: list[str] = []

    async def fake_delete_task(*, task_id: str, redis_client=None):
        deletes.append(task_id)

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake_redis)
    monkeypatch.setattr("redis_sre_agent.core.threads.ThreadManager", FakeThreadManager)
    monkeypatch.setattr("redis_sre_agent.core.tasks.delete_task", fake_delete_task)

    runner = CliRunner()
    result = runner.invoke(threads_mod.thread, ["purge", "--all", "-y"])  # include tasks by default

    assert result.exit_code == 0
    assert set(deletes) == {"t1", "t2"}


def test_task_purge_invalid_duration(monkeypatch):
    from redis_sre_agent.cli import tasks as tasks_mod

    # Prevent any real redis usage
    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: FakeRedis({}))

    runner = CliRunner()
    result = runner.invoke(
        tasks_mod.task, ["purge", "--older-than", "bogus", "-y"]
    )  # bypass prompt

    assert result.exit_code != 0
    assert "Invalid duration" in (str(result.exception) or "")


def test_task_purge_all_dry_run_handles_hmget_error(monkeypatch):
    from redis_sre_agent.cli import tasks as tasks_mod

    class FR(FakeRedis):
        async def hmget(self, key: str, *fields: str):  # raise to hit except branch in CLI
            raise RuntimeError("boom")

    fake = FR({"sre_tasks:t1": {}, "sre_tasks:t2": {}})

    called = {"count": 0}

    async def fake_delete_task(*, task_id: str, redis_client=None):
        called["count"] += 1

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr("redis_sre_agent.core.tasks.delete_task", fake_delete_task)

    runner = CliRunner()
    result = runner.invoke(tasks_mod.task, ["purge", "--all", "--dry-run"])  # preview only

    assert result.exit_code == 0
    assert called["count"] == 0
    assert "Would delete task t1" in result.output
    assert "Would delete task t2" in result.output


def test_thread_purge_older_than_dry_run_filters(monkeypatch):
    from redis_sre_agent.cli import threads as threads_mod

    fake = FakeRedis(
        {
            "sre_threads:th_old": {"created_at": "1"},
            "sre_threads:th_new": {"created_at": "9999999999"},
        }
    )

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: fake)
    monkeypatch.setattr("redis_sre_agent.core.threads.ThreadManager", FakeThreadManager)

    runner = CliRunner()
    result = runner.invoke(
        threads_mod.thread, ["purge", "--older-than", "7d", "--dry-run"]
    )  # preview only

    assert result.exit_code == 0
    assert "Would delete thread th_old" in result.output
    assert "Would delete thread th_new" not in result.output


def test_thread_purge_invalid_duration(monkeypatch):
    from redis_sre_agent.cli import threads as threads_mod

    monkeypatch.setattr("redis_sre_agent.core.redis.get_redis_client", lambda: FakeRedis({}))
    monkeypatch.setattr("redis_sre_agent.core.threads.ThreadManager", FakeThreadManager)

    runner = CliRunner()
    result = runner.invoke(
        threads_mod.thread, ["purge", "--older-than", "bogus", "-y"]
    )  # bypass prompt

    assert result.exit_code != 0
    assert "Invalid duration" in (str(result.exception) or "")
