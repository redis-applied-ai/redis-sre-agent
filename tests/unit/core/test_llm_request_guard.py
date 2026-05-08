from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import HumanMessage

import redis_sre_agent.core.llm_request_guard as guard_module
from redis_sre_agent.core.llm_request_guard import (
    PIIRemediationBlockedError,
    PIIRemediationError,
    guard_langchain_input,
    guard_openai_chat_messages,
    guarded_ainvoke,
)
from redis_sre_agent.core.pii_remediation import (
    PIIFinding,
    PIIRemediationDecision,
    PIIRemediationResult,
    PIITextBlock,
)


@pytest.fixture
def guard_settings(monkeypatch):
    settings = SimpleNamespace(
        pii_remediation_mode="redact",
        pii_remediation_categories=["private_email", "secret"],
        pii_remediation_max_chars=32000,
        pii_remediation_fail_open_for_redact=False,
    )
    monkeypatch.setattr(guard_module, "settings", settings)
    return settings


@pytest.mark.asyncio
async def test_guard_langchain_input_redacts_string(monkeypatch, guard_settings):
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="lc:0",
                    path="messages[0].content",
                    role="human",
                    text="Contact [PII:EMAIL:1] now",
                )
            ],
            findings=[
                PIIFinding(
                    category="private_email",
                    block_id="lc:0",
                    placeholder="[PII:EMAIL:1]",
                    text="alice@example.com",
                )
            ],
            detector_name="test",
            detector_model="local",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    result = await guard_langchain_input(
        "Contact alice@example.com now",
        request_kind="unit",
    )

    assert result == "Contact [PII:EMAIL:1] now"


@pytest.mark.asyncio
async def test_guard_openai_chat_messages_redacts_parts(monkeypatch, guard_settings):
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="oa:0:0",
                    path="messages[0].content[0].text",
                    role="user",
                    text="token [PII:SECRET:1]",
                )
            ],
            findings=[
                PIIFinding(
                    category="secret",
                    block_id="oa:0:0",
                    placeholder="[PII:SECRET:1]",
                    text="abcd1234",
                )
            ],
            detector_name="test",
            detector_model="local",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    result = await guard_openai_chat_messages(
        [{"role": "user", "content": [{"type": "text", "text": "token abcd1234"}]}],
        request_kind="unit",
    )

    assert result[0]["content"][0]["text"] == "token [PII:SECRET:1]"


@pytest.mark.asyncio
async def test_guard_detect_mode_fails_open(monkeypatch, guard_settings):
    guard_settings.pii_remediation_mode = "detect"
    monkeypatch.setattr(
        guard_module,
        "get_pii_remediator",
        lambda: SimpleNamespace(remediate=AsyncMock(side_effect=RuntimeError("boom"))),
    )

    result = await guard_langchain_input("hello", request_kind="unit")

    assert result == "hello"


@pytest.mark.asyncio
async def test_guard_redact_mode_fails_closed(monkeypatch, guard_settings):
    monkeypatch.setattr(
        guard_module,
        "get_pii_remediator",
        lambda: SimpleNamespace(remediate=AsyncMock(side_effect=RuntimeError("boom"))),
    )

    with pytest.raises(PIIRemediationError):
        await guard_langchain_input("hello", request_kind="unit")


@pytest.mark.asyncio
async def test_guard_raises_when_result_blocks(monkeypatch, guard_settings):
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.BLOCKED,
            blocks=[
                PIITextBlock(
                    block_id="lc:0", path="messages[0].content", role="human", text="hello"
                )
            ],
            findings=[PIIFinding(category="secret", block_id="lc:0")],
            detector_name="test",
            detector_model="local",
            reason="blocked",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    with pytest.raises(PIIRemediationBlockedError):
        await guard_langchain_input("hello", request_kind="unit")


@pytest.mark.asyncio
async def test_guard_logs_do_not_include_raw_pii(monkeypatch, guard_settings, caplog):
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="lc:0",
                    path="messages[0].content",
                    role="human",
                    text="safe [PII:EMAIL:1]",
                )
            ],
            findings=[
                PIIFinding(
                    category="private_email",
                    block_id="lc:0",
                    placeholder="[PII:EMAIL:1]",
                    text="alice@example.com",
                )
            ],
            detector_name="privacy_filter",
            detector_model="openai/privacy-filter",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    with caplog.at_level("INFO"):
        await guard_langchain_input("safe alice@example.com", request_kind="unit")

    assert "alice@example.com" not in caplog.text
    assert "private_email" in caplog.text


@pytest.mark.asyncio
async def test_guarded_ainvoke_passes_redacted_payload(monkeypatch, guard_settings):
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value="ok"))
    monkeypatch.setattr(
        guard_module,
        "guard_langchain_input",
        AsyncMock(return_value=[HumanMessage(content="redacted")]),
    )

    result = await guarded_ainvoke(llm, [HumanMessage(content="raw")], request_kind="unit")

    assert result == "ok"
    llm.ainvoke.assert_awaited_once()
    sent_payload = llm.ainvoke.await_args.args[0]
    assert sent_payload[0].content == "redacted"


@pytest.mark.asyncio
async def test_guarded_ainvoke_supports_openai_style_dict_messages(monkeypatch, guard_settings):
    llm = SimpleNamespace(ainvoke=AsyncMock(return_value="ok"))
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="oa:0",
                    path="messages[0].content",
                    role="user",
                    text="reach [PII:EMAIL:1]",
                )
            ],
            findings=[
                PIIFinding(
                    category="private_email",
                    block_id="oa:0",
                    placeholder="[PII:EMAIL:1]",
                    text="alice@example.com",
                )
            ],
            detector_name="test",
            detector_model="local",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    payload = [{"role": "user", "content": "reach alice@example.com"}]

    result = await guarded_ainvoke(llm, payload, request_kind="unit")

    assert result == "ok"
    sent_payload = llm.ainvoke.await_args.args[0]
    assert sent_payload[0]["content"] == "reach [PII:EMAIL:1]"


@pytest.mark.asyncio
async def test_guard_langchain_input_preserves_tail_beyond_max_chars(monkeypatch, guard_settings):
    guard_settings.pii_remediation_max_chars = 10
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="lc:0",
                    path="messages[0].content",
                    role="human",
                    text="[PII:EMAIL:1]",
                )
            ],
            findings=[
                PIIFinding(
                    category="private_email",
                    block_id="lc:0",
                    placeholder="[PII:EMAIL:1]",
                    text="alice@exam",
                )
            ],
            detector_name="test",
            detector_model="local",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    result = await guard_langchain_input("alice@example.com trailing", request_kind="unit")

    assert result == "[PII:EMAIL:1]ple.com trailing"


@pytest.mark.asyncio
async def test_guard_langchain_input_supports_mixed_message_and_dict_sequences(
    monkeypatch, guard_settings
):
    remediator = AsyncMock(
        return_value=PIIRemediationResult(
            decision=PIIRemediationDecision.REDACTED,
            blocks=[
                PIITextBlock(
                    block_id="lc:1",
                    path="messages[1].content",
                    role="user",
                    text="reach [PII:EMAIL:1]",
                )
            ],
            findings=[
                PIIFinding(
                    category="private_email",
                    block_id="lc:1",
                    placeholder="[PII:EMAIL:1]",
                    text="alice@example.com",
                )
            ],
            detector_name="test",
            detector_model="local",
        )
    )
    monkeypatch.setattr(
        guard_module, "get_pii_remediator", lambda: SimpleNamespace(remediate=remediator)
    )

    payload = [
        HumanMessage(content="safe"),
        {"role": "user", "content": "reach alice@example.com"},
    ]

    result = await guard_langchain_input(payload, request_kind="unit")

    assert result[0].content == "safe"
    assert result[1]["content"] == "reach [PII:EMAIL:1]"
