# PII Remediation Hook Spec

Status: Proposed

Related:
- `redis_sre_agent/core/llm_helpers.py`
- `redis_sre_agent/agent/langgraph_agent.py`
- `redis_sre_agent/agent/chat_agent.py`
- `redis_sre_agent/agent/knowledge_agent.py`
- `redis_sre_agent/agent/router.py`
- `redis_sre_agent/core/threads.py`
- `redis_sre_agent/pipelines/enrichment/document_enricher.py`
- `redis_sre_agent/pipelines/scraper/runbook_generator.py`

## Summary

Add a pluggable pre-request PII remediation function that runs on outbound text input before
`redis-sre-agent` sends a request to an LLM vendor API.

Today the repo has no centralized outbound input policy for LLM calls. We already redact some
tool arguments for audit previews, but that does not protect user prompts, thread history, or
pipeline-generated text that is sent to `ChatOpenAI.ainvoke(...)` or `AsyncOpenAI.chat.completions.create(...)`.

This spec introduces:

- a `PIIRemediator` interface that can detect, redact, or block outbound text
- a shared request-guard layer used by both LangChain chat models and direct OpenAI SDK calls
- structured findings and stable placeholders so one request remains coherent after redaction
- metrics and audit events that record categories and counts without persisting raw PII
- a shipped default implementation that runs OpenAI Privacy Filter locally

The default detector choice is intentionally explicit and time-bound:

- on April 22, 2026, OpenAI introduced Privacy Filter as a PII detection and redaction model
- Privacy Filter is designed specifically for this task, supports a single-pass token
  classification flow, and can run locally
- the released model supports up to 128,000 tokens and predicts spans across eight privacy
  categories, including `secret`

This is a better fit for the requirement than using a general LLM to decide what PII should be
masked before a larger reasoning model sees the text.

## Problem

`redis-sre-agent` can send sensitive user text to external model providers without a single
pluggable inspection point.

Current gaps in this repo:

- agent calls are spread across multiple modules and directly invoke LLMs
- `llm_factory` and `async_openai_client_factory` customize client construction, not per-request
  payload handling
- audit redaction in `ToolManager` only covers tool argument previews, not outbound prompts
- there is no consistent way to:
  - detect likely PII
  - replace it with placeholders
  - block a request when policy requires it
  - emit non-sensitive telemetry about what happened

That leaves the repo with no reusable answer for teams that want:

- prompt redaction before vendor submission
- different policies in different deployments
- a stricter local or enterprise DLP implementation later

## Goals

- Add one pluggable pre-request seam for outbound LLM input remediation.
- Run remediation on the exact text payload that will be sent to the vendor.
- Support policy modes: `off`, `detect`, `redact`, and `block`.
- Keep placeholder replacement stable within a single outbound request.
- Cover both LangChain `ainvoke(...)` paths and direct OpenAI SDK `chat.completions.create(...)`
  paths.
- Record counts, categories, model choice, and decision outcome without logging raw PII.
- Ship a default implementation so deployments do not need to write a plugin to use the feature.

## Non-goals

- Retroactively scrubbing existing Redis thread data, cached tool outputs, or logs.
- Replacing existing secret redaction for tool arguments or approval previews.
- Building a full enterprise DLP rules engine in v1.
- Inspecting image pixels or binary files for PII in v1.
- Guaranteeing zero false positives or zero false negatives.
- Building a full document anonymization or compliance certification workflow.

## Current-State Observations

### 1. There is no single outbound LLM invocation seam today

The repo makes outbound LLM calls from multiple places, including:

- `redis_sre_agent/agent/langgraph_agent.py`
- `redis_sre_agent/agent/chat_agent.py`
- `redis_sre_agent/agent/knowledge_agent.py`
- `redis_sre_agent/agent/router.py`
- `redis_sre_agent/core/threads.py`
- `redis_sre_agent/pipelines/enrichment/document_enricher.py`
- `redis_sre_agent/pipelines/scraper/runbook_generator.py`
- `redis_sre_agent/evaluation/judge.py`

Without a shared wrapper, any PII policy would be fragile and easy to bypass accidentally.

### 2. Client factories are the wrong abstraction level for payload remediation

`redis_sre_agent/core/llm_helpers.py` already supports:

- `llm_factory`
- `async_openai_client_factory`

Those seams are useful for provider swapping, but they do not see the normalized request payload
at invocation time. PII remediation belongs at the point where we have the final message list or
chat-completions payload.

### 3. Existing redaction only protects tool previews

`ToolManager` already replaces obviously sensitive argument keys with `[redacted]` for audit
previews. That is good, but it protects operator-facing summaries, not the actual prompt content
sent to an LLM vendor.

## Proposed Design

### 1. Add a pluggable remediation contract

Add a new module:

```text
redis_sre_agent/core/pii_remediation.py
```

Core models:

- `PIIRemediationMode = "off" | "detect" | "redact" | "block"`
- `PIIRemediationDecision = "allow" | "redacted" | "blocked"`
- `PIITextBlock`
- `PIIFinding`
- `PIIRemediationRequest`
- `PIIRemediationResult`
- `PIIRemediator` protocol

Suggested shape:

```python
class PIIRemediator(Protocol):
    async def remediate(
        self,
        request: PIIRemediationRequest,
    ) -> PIIRemediationResult: ...
```

`PIITextBlock` should represent one text-bearing fragment of an outbound request:

- `block_id`
- `path`
- `role`
- `text`

Examples:

- `messages[0].content`
- `messages[4].content`
- `prompt`
- `system`

`PIIFinding` should include:

- `category`
- `block_id`
- `placeholder`
- `confidence`
- optional `span_start` / `span_end`

`PIIRemediationResult` should include:

- `decision`
- `blocks` with redacted text when applicable
- `findings`
- `detector_name`
- `detector_model`
- `latency_ms`
- optional `reason`

### 2. Add a shared outbound request-guard layer

Add a second module:

```text
redis_sre_agent/core/llm_request_guard.py
```

This module is the only place that should:

- normalize outbound text-bearing inputs into `PIITextBlock`s
- call the configured `PIIRemediator`
- rebuild the outbound payload with redacted text when needed
- emit telemetry and audit summaries
- enforce `block` decisions before vendor submission

Helpers should include two transport-focused entrypoints:

- `guard_langchain_messages(messages, request_context) -> list[BaseMessage]`
- `guard_openai_chat_messages(messages, request_context) -> list[dict[str, Any]]`

And two invocation helpers:

- `guarded_ainvoke(llm, messages, request_context)`
- `guarded_chat_completions_create(client, *, model, messages, **kwargs)`

The important design constraint is that the guarded helper receives the final outbound payload,
not an earlier intermediate prompt fragment.

### 3. Centralize integration through wrappers, not ad hoc call-site logic

Update all direct outbound call sites to use the new wrappers instead of calling the provider
directly.

Initial scope must include:

- `langgraph_agent.py`
- `chat_agent.py`
- `knowledge_agent.py`
- `router.py`
- `threads.py`
- `document_enricher.py`
- `runbook_generator.py`
- `evaluation/judge.py`

This keeps the policy consistent across:

- agent turns
- thread subject generation
- evaluators
- document enrichment
- scraped runbook standardization

### 4. Preserve internal state; only mutate the outbound copy in v1

The remediation hook should transform the payload copy being sent to the vendor, not rewrite
thread history or in-memory state objects before the outbound call.

Why:

- v1 is about vendor-bound request handling, not storage migration
- changing canonical message history would complicate checkpointing and debugging
- placeholder text is useful for one request, but it should not silently overwrite the original
  application state without an explicit data-retention decision

This means the system may retain original user text internally unless another feature chooses to
scrub it separately.

### 5. Use stable placeholders within each request

When mode is `redact`, the remediator should replace matches with deterministic placeholders that
stay consistent within one outbound request:

- `[PII:EMAIL:1]`
- `[PII:PHONE:1]`
- `[PII:GOV_ID:1]`

If the same email appears three times in the same outbound payload, it should map to the same
placeholder each time.

That keeps the model prompt coherent while still removing the original value.

Cross-request placeholder stability is not required in v1.

### 6. Policy modes

Support four modes:

- `off`
  - do nothing
- `detect`
  - inspect and record findings, but send the original payload
- `redact`
  - inspect and replace detected PII with placeholders before sending
- `block`
  - reject the outbound call if PII is detected

Recommended defaults:

- default config mode: `off`
- recommended first rollout mode: `detect`
- recommended steady-state mode for vendor-bound prompts: `redact`

Using `off` as the shipped config default avoids surprise latency and cost regressions for current
deployments.

### 7. Default shipped implementation: local OpenAI Privacy Filter

Ship a built-in implementation:

```text
redis_sre_agent/core/default_pii_remediator.py
```

This implementation should:

- run OpenAI Privacy Filter locally instead of calling an external LLM API
- default to `model="openai/privacy-filter"`
- convert model spans into the repo's placeholder format
- keep a bounded max input size per remediation pass
- preserve the ability to swap in a different implementation through the same plugin contract

Recommended settings:

- `pii_remediation_model = "openai/privacy-filter"`
- `pii_remediation_max_chars = 32000`
- `pii_remediation_runtime = "local"`

The base taxonomy should align to the model's released labels:

- `private_person`
- `private_address`
- `private_email`
- `private_phone`
- `private_url`
- `private_date`
- `account_number`
- `secret`

Rationale:

- OpenAI released Privacy Filter specifically for detecting and masking PII in text
- the model is intended for high-throughput privacy workflows and can run on-premises
- the model includes `secret` as a first-class category, which is useful for prompt safety in this
  repo because outbound text can contain passwords, tokens, or API keys in addition to classic PII
- using a purpose-built local classifier is a materially better trust-boundary fit than asking a
  general LLM to identify sensitive spans before the main request

### 8. Local runtime and dependency notes

The repo does not currently include a local Privacy Filter inference stack.

The implementation should therefore call out new runtime requirements explicitly, for example:

- `transformers`
- one supported local inference backend such as `torch` or `onnxruntime`

For v1, prefer the simplest reliable local runtime over the most optimized one. If implementation
tradeoffs matter, use:

- `transformers` plus `torch` for the shortest path to correctness
- `onnxruntime` as a later optimization path if startup time or memory footprint becomes a concern

The default implementation should materialize the model locally from the released OpenAI Privacy
Filter weights rather than proxying requests through the OpenAI API.

### 9. Configuration

Add settings in `redis_sre_agent/core/config.py`:

- `pii_remediation_mode: Literal["off", "detect", "redact", "block"] = "off"`
- `pii_remediation_factory: Optional[str] = None`
- `pii_remediation_model: str = "openai/privacy-filter"`
- `pii_remediation_runtime: Literal["local"] = "local"`
- `pii_remediation_max_chars: int = 32000`
- `pii_remediation_categories: list[str]`

Suggested default category set:

- `private_person`
- `private_address`
- `private_email`
- `private_phone`
- `private_url`
- `private_date`
- `account_number`
- `secret`

If the repo later wants friendlier policy aliases such as `email` or `phone`, that mapping should
live above the model adapter rather than changing the underlying taxonomy names.

### 10. Failure handling

Fail-open versus fail-closed must be explicit.

Recommended behavior:

- mode `detect`
  - if remediation fails, send the original request and emit an error metric
- mode `redact`
  - if remediation fails, block the request by default and return a clear error
- mode `block`
  - if remediation fails, block the request

Reasoning:

- `detect` is observational, so fail-open is acceptable
- `redact` and `block` are privacy controls, so silent fail-open would violate operator intent

Add one config escape hatch only if needed later:

- `pii_remediation_fail_open_for_redact: bool = False`

That flag should not be part of the initial default path unless a real deployment needs it.

### 11. Observability and audit behavior

Add counters and spans for:

- remediation requests
- findings count by category
- redacted requests
- blocked requests
- remediation failures
- remediation latency

Do not log:

- raw matched values
- raw prompt text
- raw redacted prompt text

Safe audit fields:

- `request_kind`
- `mode`
- `decision`
- `detector_name`
- `detector_model`
- `categories_present`
- `findings_count`
- `changed_text`

### 12. Testing strategy

Add automated tests in the repo’s normal test locations.

Coverage should include:

- `off`, `detect`, `redact`, and `block` mode behavior
- stable placeholder mapping within one request
- no-op handling when no PII is found
- fail-open behavior for `detect`
- fail-closed behavior for `redact` and `block`
- wrapper coverage for both LangChain and direct OpenAI SDK call paths
- assurance that logs and metrics do not contain raw matched values

Tests should use mocking for the local detector runtime. Do not add special testing branches into
production code.

## Implementation Plan

### 1. Add the contract and config

- create `core/pii_remediation.py`
- add config fields to `core/config.py`
- add loader logic similar to `llm_factory` and `async_openai_client_factory`

### 2. Add the request-guard wrapper

- create `core/llm_request_guard.py`
- implement message normalization and rebuild helpers
- add telemetry emission

### 3. Add the shipped default remediator

- create `core/default_pii_remediator.py`
- load `openai/privacy-filter` locally
- map the model's span labels into the placeholder renderer
- keep the local runtime behind a small adapter so a faster backend can be added later

### 4. Migrate outbound call sites

- replace direct `ainvoke(...)` and `chat.completions.create(...)` usage with guarded helpers
- keep migration mechanical and centralized

### 5. Add tests

- unit test the contract, wrapper, and default remediator
- regression test at least one agent path and one pipeline path

## Open Questions

1. Should `redact` mode rewrite internal thread history after the outbound call, or should that
remain a separate storage-policy feature?
2. Do we want one shared remediation pass over the whole outbound payload, or independent per-block
classification for better isolation?
3. Should response-side PII detection exist later for assistant outputs, or is request-side
coverage enough for the intended compliance boundary?

## Recommendation

Implement the pluggable contract now and ship the local Privacy Filter default behind a
disabled-by-default feature flag.

That gets us:

- a real extension seam
- a usable default path
- a clear migration point for stricter local or enterprise implementations later

It also keeps the repo honest about the trust boundary: the default local Privacy Filter path is
meant to reduce what leaves the process before the main model call, while still leaving room for a
stricter in-house DLP implementation later if policy requires it.
