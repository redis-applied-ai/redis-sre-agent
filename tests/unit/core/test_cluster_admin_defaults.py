"""Unit tests for Redis Enterprise admin defaults resolution."""

import os
from unittest.mock import patch

from pydantic import SecretStr

from redis_sre_agent.core.cluster_admin_defaults import (
    build_enterprise_admin_missing_fields_error,
    missing_enterprise_admin_fields,
    resolve_enterprise_admin_fields,
)


def test_resolve_enterprise_admin_fields_uses_explicit_values():
    with patch.dict(
        os.environ,
        {
            "REDIS_ENTERPRISE_ADMIN_URL": "https://env.example.com:9443",
            "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
            "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
        },
        clear=False,
    ):
        resolved = resolve_enterprise_admin_fields(
            cluster_type="redis_enterprise",
            admin_url="https://explicit.example.com:9443",
            admin_username="explicit-admin@example.com",
            admin_password=SecretStr("explicit-secret"),
        )

    assert resolved.admin_url == "https://explicit.example.com:9443"
    assert resolved.admin_username == "explicit-admin@example.com"
    assert resolved.admin_password is not None
    assert resolved.admin_password.get_secret_value() == "explicit-secret"
    assert resolved.field_sources == {
        "admin_url": "explicit",
        "admin_username": "explicit",
        "admin_password": "explicit",
    }


def test_resolve_enterprise_admin_fields_falls_back_to_env():
    with patch.dict(
        os.environ,
        {
            "REDIS_ENTERPRISE_ADMIN_URL": "https://env.example.com:9443",
            "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
            "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
        },
        clear=False,
    ):
        resolved = resolve_enterprise_admin_fields(
            cluster_type="redis_enterprise",
            admin_url=None,
            admin_username=None,
            admin_password=None,
        )

    assert resolved.admin_url == "https://env.example.com:9443"
    assert resolved.admin_username == "env-admin@example.com"
    assert resolved.admin_password is not None
    assert resolved.admin_password.get_secret_value() == "env-secret"
    assert resolved.field_sources == {
        "admin_url": "env",
        "admin_username": "env",
        "admin_password": "env",
    }


def test_resolve_enterprise_admin_fields_accepts_tools_alias_env_vars():
    with patch.dict(
        os.environ,
        {
            "TOOLS_REDIS_ENTERPRISE_ADMIN_URL": "https://tools-env.example.com:9443",
            "TOOLS_REDIS_ENTERPRISE_ADMIN_USERNAME": "tools-admin@example.com",
            "TOOLS_REDIS_ENTERPRISE_ADMIN_PASSWORD": "tools-secret",
        },
        clear=False,
    ):
        resolved = resolve_enterprise_admin_fields(
            cluster_type="redis_enterprise",
            admin_url=None,
            admin_username=None,
            admin_password=None,
        )

    assert resolved.admin_url == "https://tools-env.example.com:9443"
    assert resolved.admin_username == "tools-admin@example.com"
    assert resolved.admin_password is not None
    assert resolved.admin_password.get_secret_value() == "tools-secret"


def test_resolve_enterprise_admin_fields_non_enterprise_ignores_env_defaults():
    with patch.dict(
        os.environ,
        {
            "REDIS_ENTERPRISE_ADMIN_URL": "https://env.example.com:9443",
            "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
            "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
        },
        clear=False,
    ):
        resolved = resolve_enterprise_admin_fields(
            cluster_type="oss_cluster",
            admin_url=None,
            admin_username=None,
            admin_password=None,
        )

    assert resolved.admin_url is None
    assert resolved.admin_username is None
    assert resolved.admin_password is None
    assert resolved.field_sources == {
        "admin_url": "none",
        "admin_username": "none",
        "admin_password": "none",
    }


def test_resolve_enterprise_admin_fields_normalizes_whitespace_and_uses_env_fallback():
    with patch.dict(
        os.environ,
        {
            "REDIS_ENTERPRISE_ADMIN_URL": "https://env.example.com:9443",
            "REDIS_ENTERPRISE_ADMIN_USERNAME": "env-admin@example.com",
            "REDIS_ENTERPRISE_ADMIN_PASSWORD": "env-secret",
        },
        clear=False,
    ):
        resolved = resolve_enterprise_admin_fields(
            cluster_type="redis_enterprise",
            admin_url="   ",
            admin_username="  explicit-admin@example.com  ",
            admin_password="   ",
        )

    assert resolved.admin_url == "https://env.example.com:9443"
    assert resolved.admin_username == "explicit-admin@example.com"
    assert resolved.admin_password is not None
    assert resolved.admin_password.get_secret_value() == "env-secret"
    assert resolved.field_sources == {
        "admin_url": "env",
        "admin_username": "explicit",
        "admin_password": "env",
    }


def test_missing_enterprise_admin_fields_reports_missing_values():
    missing = missing_enterprise_admin_fields(
        admin_url=None,
        admin_username="admin@example.com",
        admin_password="",
    )

    assert missing == ["admin_url", "admin_password"]


def test_build_enterprise_admin_missing_fields_error_includes_env_hints():
    error = build_enterprise_admin_missing_fields_error(["admin_url", "admin_password"])

    assert "Missing: admin_url, admin_password." in error
    assert "REDIS_ENTERPRISE_ADMIN_URL" in error
    assert "REDIS_ENTERPRISE_ADMIN_USERNAME" in error
    assert "REDIS_ENTERPRISE_ADMIN_PASSWORD" in error
