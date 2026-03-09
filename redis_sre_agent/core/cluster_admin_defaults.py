"""Resolve Redis Enterprise admin fields from explicit input and env defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from pydantic import SecretStr

# Canonical environment variables for Redis Enterprise admin defaults.
_ADMIN_ENV_CANDIDATES: Dict[str, Sequence[str]] = {
    "admin_url": (
        "REDIS_ENTERPRISE_ADMIN_URL",
        "TOOLS_REDIS_ENTERPRISE_ADMIN_URL",  # Backward-compatible alias
    ),
    "admin_username": (
        "REDIS_ENTERPRISE_ADMIN_USERNAME",
        "TOOLS_REDIS_ENTERPRISE_ADMIN_USERNAME",  # Backward-compatible alias
    ),
    "admin_password": (
        "REDIS_ENTERPRISE_ADMIN_PASSWORD",
        "TOOLS_REDIS_ENTERPRISE_ADMIN_PASSWORD",  # Backward-compatible alias
    ),
}

_CANONICAL_ADMIN_ENV_VARS = (
    "REDIS_ENTERPRISE_ADMIN_URL",
    "REDIS_ENTERPRISE_ADMIN_USERNAME",
    "REDIS_ENTERPRISE_ADMIN_PASSWORD",
)


@dataclass(frozen=True)
class EnterpriseAdminResolution:
    """Resolved admin fields and the source used for each field."""

    admin_url: Optional[str]
    admin_username: Optional[str]
    admin_password: Optional[SecretStr]
    field_sources: Dict[str, str]


def _normalize_optional_text(value: object) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_secret(value: SecretStr | str | None) -> Optional[SecretStr]:
    if value is None:
        return None
    if isinstance(value, SecretStr):
        raw = value.get_secret_value()
    else:
        raw = value
    normalized = _normalize_optional_text(raw)
    if not normalized:
        return None
    return SecretStr(normalized)


def _read_env_default(field: str) -> Optional[str]:
    for env_name in _ADMIN_ENV_CANDIDATES[field]:
        value = _normalize_optional_text(os.getenv(env_name))
        if value:
            return value
    return None


def resolve_enterprise_admin_fields(
    *,
    cluster_type: str,
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: SecretStr | str | None,
) -> EnterpriseAdminResolution:
    """Resolve admin fields with precedence: explicit input > env > missing.

    Env fallback applies only to ``cluster_type=redis_enterprise``.
    """
    normalized_cluster_type = (cluster_type or "").strip().lower()
    resolved_url = _normalize_optional_text(admin_url)
    resolved_username = _normalize_optional_text(admin_username)
    resolved_password = _normalize_secret(admin_password)
    field_sources = {
        "admin_url": "explicit" if resolved_url else "none",
        "admin_username": "explicit" if resolved_username else "none",
        "admin_password": "explicit" if resolved_password else "none",
    }

    if normalized_cluster_type == "redis_enterprise":
        if resolved_url is None:
            env_url = _read_env_default("admin_url")
            if env_url:
                resolved_url = env_url
                field_sources["admin_url"] = "env"

        if resolved_username is None:
            env_username = _read_env_default("admin_username")
            if env_username:
                resolved_username = env_username
                field_sources["admin_username"] = "env"

        if resolved_password is None:
            env_password = _read_env_default("admin_password")
            if env_password:
                resolved_password = SecretStr(env_password)
                field_sources["admin_password"] = "env"

    return EnterpriseAdminResolution(
        admin_url=resolved_url,
        admin_username=resolved_username,
        admin_password=resolved_password,
        field_sources=field_sources,
    )


def missing_enterprise_admin_fields(
    *,
    admin_url: Optional[str],
    admin_username: Optional[str],
    admin_password: SecretStr | str | None,
) -> List[str]:
    """Return the missing Redis Enterprise admin fields."""
    missing: List[str] = []
    if _normalize_optional_text(admin_url) is None:
        missing.append("admin_url")
    if _normalize_optional_text(admin_username) is None:
        missing.append("admin_username")
    if _normalize_secret(admin_password) is None:
        missing.append("admin_password")
    return missing


def build_enterprise_admin_missing_fields_error(missing_fields: Sequence[str]) -> str:
    """Build an actionable validation message for missing admin fields."""
    missing_csv = ", ".join(missing_fields)
    env_csv = "/".join(_CANONICAL_ADMIN_ENV_VARS)
    return (
        "cluster_type=redis_enterprise requires admin_url, admin_username, and admin_password. "
        f"Missing: {missing_csv}. "
        f"Set explicitly or via {env_csv}."
    )
