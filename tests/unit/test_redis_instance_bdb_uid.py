from unittest.mock import patch

import pytest

from redis_sre_agent.core.instances import RedisInstance


class DummyResponse:
    def __init__(self, data, status_code=200):
        self._data = data
        self.status_code = status_code
        self.text = ""

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._data


class DummyClient:
    def __init__(self, captured_kwargs: dict):
        self.captured_kwargs = captured_kwargs
        self._data = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, path, params=None):
        return DummyResponse(self._data)


@pytest.mark.asyncio
async def test_get_bdb_uid_by_port_match():
    """Matches non-TLS port to bdb.port."""
    inst = RedisInstance(
        id="re-1",
        name="Enterprise",
        connection_url="redis://host:12000/0",
        environment="test",
        usage="cache",
        description="",
        instance_type="redis_enterprise",
        admin_url="https://cluster:9443",
        admin_username="admin",
        admin_password="pass",
    )

    bdbs = [
        {"uid": 1, "name": "db1", "port": 12000},
        {"uid": 2, "name": "db2", "port": 12001, "ssl_port": 12001},
    ]

    captured = {}

    def make_client(**kwargs):
        captured.update(kwargs)
        c = DummyClient(captured)
        c._data = bdbs
        return c

    with patch("httpx.AsyncClient", side_effect=lambda **kw: make_client(**kw)):
        uid = await inst.get_bdb_uid()

    assert uid == 1


@pytest.mark.asyncio
async def test_get_bdb_uid_by_ssl_port_match():
    """Matches TLS port to bdb.ssl_port when scheme is rediss."""
    inst = RedisInstance(
        id="re-2",
        name="Enterprise",
        connection_url="rediss://host:12001/0",
        environment="test",
        usage="cache",
        description="",
        instance_type="redis_enterprise",
        admin_url="https://cluster:9443",
        admin_username="admin",
        admin_password="pass",
    )

    bdbs = [
        {"uid": 1, "name": "db1", "port": 12000},
        {"uid": 2, "name": "db2", "port": 12002, "ssl_port": 12001},
    ]

    client = DummyClient({})
    client._data = bdbs

    with patch("httpx.AsyncClient", side_effect=lambda **kw: client):
        uid = await inst.get_bdb_uid()

    assert uid == 2


@pytest.mark.asyncio
async def test_get_bdb_uid_by_name_fallback():
    """When name is provided, prefer exact name match."""
    inst = RedisInstance(
        id="re-3",
        name="Enterprise",
        connection_url="redis://host:12000/0",
        environment="test",
        usage="cache",
        description="",
        instance_type="redis_enterprise",
        admin_url="https://cluster:9443",
        admin_username="admin",
        admin_password="pass",
    )

    bdbs = [
        {"uid": 10, "name": "alpha", "port": 12001},
        {"uid": 77, "name": "target", "port": 12002, "ssl_port": 0},
    ]

    client = DummyClient({})
    client._data = bdbs

    with patch("httpx.AsyncClient", side_effect=lambda **kw: client):
        uid = await inst.get_bdb_uid(bdb_name="target")

    assert uid == 77


@pytest.mark.asyncio
async def test_get_bdb_uid_missing_admin_returns_none():
    inst = RedisInstance(
        id="re-4",
        name="Enterprise",
        connection_url="redis://host:12000/0",
        environment="test",
        usage="cache",
        description="",
        instance_type="redis_enterprise",
    )

    uid = await inst.get_bdb_uid()
    assert uid is None
