from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import redis_sre_agent.core.pii_remediation as pii_module
from redis_sre_agent.core.default_pii_remediator import DefaultPrivacyFilterPIIRemediator
from redis_sre_agent.core.pii_remediation import (
    PIIRemediationDecision,
    PIIRemediationMode,
    PIIRemediationRequest,
    PIITextBlock,
    get_pii_remediator,
    reset_pii_remediator_factory,
    set_pii_remediator_factory,
)


class TestPIIRemediatorLoading:
    def teardown_method(self):
        reset_pii_remediator_factory()

    def test_set_factory_overrides_default(self):
        fake_remediator = MagicMock()
        fake_factory = MagicMock(return_value=fake_remediator)

        set_pii_remediator_factory(fake_factory)

        assert get_pii_remediator() is fake_remediator
        fake_factory.assert_called_once_with()

    def test_factory_loads_from_config(self):
        fake_remediator = MagicMock()
        module = MagicMock()
        module.custom_factory = MagicMock(return_value=fake_remediator)

        with (
            patch.object(
                pii_module,
                "settings",
                SimpleNamespace(pii_remediation_factory="my.factory.custom_factory"),
            ),
            patch(
                "redis_sre_agent.core.pii_remediation.importlib.import_module", return_value=module
            ),
        ):
            remediator = get_pii_remediator()

        assert remediator is fake_remediator
        module.custom_factory.assert_called_once_with()


@pytest.mark.asyncio
async def test_default_privacy_filter_redacts_with_stable_placeholders():
    remediator = DefaultPrivacyFilterPIIRemediator(
        model_name="openai/privacy-filter",
        categories=["private_email"],
    )
    remediator._pipeline = lambda text: [
        {
            "entity_group": "PRIVATE_EMAIL",
            "start": 6,
            "end": 23,
            "score": 0.98,
        },
        {
            "entity_group": "PRIVATE_EMAIL",
            "start": 34,
            "end": 51,
            "score": 0.97,
        },
    ]
    request = PIIRemediationRequest(
        mode=PIIRemediationMode.REDACT,
        request_kind="test",
        blocks=[
            PIITextBlock(
                block_id="b1",
                path="messages[0].content",
                role="user",
                text="Email alice@example.com and again alice@example.com",
            )
        ],
        categories=["private_email"],
    )

    result = await remediator.remediate(request)

    assert result.decision == PIIRemediationDecision.REDACTED
    assert result.blocks[0].text.count("[PII:EMAIL:1]") == 2
    assert all(f.placeholder == "[PII:EMAIL:1]" for f in result.findings)


@pytest.mark.asyncio
async def test_default_privacy_filter_blocks_when_mode_is_block():
    remediator = DefaultPrivacyFilterPIIRemediator(
        model_name="openai/privacy-filter",
        categories=["secret"],
    )
    remediator._pipeline = lambda text: [
        {
            "entity_group": "SECRET",
            "start": 4,
            "end": 14,
            "score": 0.91,
        }
    ]
    request = PIIRemediationRequest(
        mode=PIIRemediationMode.BLOCK,
        request_kind="test",
        blocks=[PIITextBlock(block_id="b1", path="prompt", role="user", text="tok my-secret here")],
        categories=["secret"],
    )

    result = await remediator.remediate(request)

    assert result.decision == PIIRemediationDecision.BLOCKED
    assert result.reason
