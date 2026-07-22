"""Config env-parsing contract for auth settings.

Regression: auth_scopes is a list field, and pydantic-settings JSON-decodes list env vars
at the source level — so a comma/space-separated AUTH_SCOPES used to crash Settings() at
import (SettingsError). NoDecode + a before-validator make the documented form work.
"""

from redis_sre_agent.core.config import Settings


def test_auth_scopes_comma_separated_env(monkeypatch):
    monkeypatch.setenv("AUTH_SCOPES", "openid,profile,email,api://app-id/access_as_user")
    assert Settings().auth_scopes == [
        "openid",
        "profile",
        "email",
        "api://app-id/access_as_user",
    ]


def test_auth_scopes_space_separated_env(monkeypatch):
    monkeypatch.setenv("AUTH_SCOPES", "openid profile email")
    assert Settings().auth_scopes == ["openid", "profile", "email"]


def test_auth_scopes_single_value_env(monkeypatch):
    monkeypatch.setenv("AUTH_SCOPES", "openid")
    assert Settings().auth_scopes == ["openid"]


def test_auth_scopes_extra_whitespace_env(monkeypatch):
    monkeypatch.setenv("AUTH_SCOPES", " openid , profile ,email ")
    assert Settings().auth_scopes == ["openid", "profile", "email"]
