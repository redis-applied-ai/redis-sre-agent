"""Tests for support-package helper configuration."""

from __future__ import annotations

from unittest.mock import patch

from redis_sre_agent.core.support_package_helpers import get_support_package_manager


def test_get_support_package_manager_uses_local_storage(tmp_path, monkeypatch):
    """Local storage is selected by default."""
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_storage_type",
        "local",
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_artifacts_dir",
        tmp_path,
        raising=False,
    )

    with (
        patch("redis_sre_agent.core.support_package_helpers.LocalStorage") as mock_local,
        patch("redis_sre_agent.core.support_package_helpers.SupportPackageManager") as mock_manager,
    ):
        get_support_package_manager()

        mock_local.assert_called_once_with(base_path=tmp_path / "storage")
        mock_manager.assert_called_once_with(
            storage=mock_local.return_value,
            extract_dir=tmp_path / "extracted",
        )


def test_get_support_package_manager_uses_s3_storage(tmp_path, monkeypatch):
    """S3 storage is selected when configured."""
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_storage_type",
        "s3",
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_artifacts_dir",
        tmp_path,
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_s3_bucket",
        "bucket",
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_s3_prefix",
        "prefix/",
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_s3_region",
        "us-west-2",
        raising=False,
    )
    monkeypatch.setattr(
        "redis_sre_agent.core.support_package_helpers.settings.support_package_s3_endpoint",
        "https://s3.example.com",
        raising=False,
    )

    with (
        patch("redis_sre_agent.core.support_package_helpers.S3Storage") as mock_s3,
        patch("redis_sre_agent.core.support_package_helpers.SupportPackageManager") as mock_manager,
    ):
        get_support_package_manager()

        mock_s3.assert_called_once_with(
            bucket="bucket",
            prefix="prefix/",
            region="us-west-2",
            endpoint_url="https://s3.example.com",
        )
        mock_manager.assert_called_once_with(
            storage=mock_s3.return_value,
            extract_dir=tmp_path / "extracted",
        )
