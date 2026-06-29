from types import SimpleNamespace
from unittest.mock import MagicMock

from redis_sre_agent.observability import llm_metrics


def _mock_metric():
    metric = MagicMock()
    child = MagicMock()
    metric.labels.return_value = child
    return metric, child


def test_record_llm_call_metrics_records_prometheus_and_span_attributes(monkeypatch):
    requests, requests_child = _mock_metric()
    latency, latency_child = _mock_metric()
    prompt_tokens, prompt_child = _mock_metric()
    completion_tokens, completion_child = _mock_metric()
    total_tokens, total_child = _mock_metric()
    span = MagicMock()
    span.is_recording.return_value = True
    trace = MagicMock()
    trace.get_current_span.return_value = span

    monkeypatch.setattr(llm_metrics, "LLM_REQUESTS", requests)
    monkeypatch.setattr(llm_metrics, "LLM_LATENCY", latency)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_PROMPT", prompt_tokens)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_COMPLETION", completion_tokens)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_TOTAL", total_tokens)
    monkeypatch.setattr(llm_metrics, "trace", trace)

    llm_metrics.record_llm_call_metrics(
        component="knowledge",
        llm=SimpleNamespace(model_name="gpt-5-mini"),
        response=SimpleNamespace(
            usage_metadata={
                "input_tokens": 4,
                "output_tokens": 6,
                "total_tokens": 10,
            }
        ),
        start_time=0.0,
        status="ok",
        extra_attrs={"request_kind": "knowledge_agent.agent_node"},
    )

    requests.labels.assert_called_once_with(model="gpt-5-mini", component="knowledge", status="ok")
    requests_child.inc.assert_called_once()
    latency.labels.assert_called_once_with(model="gpt-5-mini", component="knowledge")
    latency_child.observe.assert_called_once()
    prompt_tokens.labels.assert_called_once_with(model="gpt-5-mini", component="knowledge")
    prompt_child.inc.assert_called_once_with(4)
    completion_tokens.labels.assert_called_once_with(model="gpt-5-mini", component="knowledge")
    completion_child.inc.assert_called_once_with(6)
    total_tokens.labels.assert_called_once_with(model="gpt-5-mini", component="knowledge")
    total_child.inc.assert_called_once_with(10)
    span.set_attribute.assert_any_call("llm.model", "gpt-5-mini")
    span.set_attribute.assert_any_call("llm.tokens.prompt", 4)
    span.set_attribute.assert_any_call("llm.tokens.completion", 6)
    span.set_attribute.assert_any_call("llm.tokens.total", 10)
    span.set_attribute.assert_any_call("llm.status", "ok")
    span.set_attribute.assert_any_call("llm.request_kind", "knowledge_agent.agent_node")


def test_record_llm_call_metrics_handles_missing_usage_payload(monkeypatch):
    requests, requests_child = _mock_metric()
    latency, latency_child = _mock_metric()
    prompt_tokens, _ = _mock_metric()
    completion_tokens, _ = _mock_metric()
    total_tokens, _ = _mock_metric()
    span = MagicMock()
    span.is_recording.return_value = True
    trace = MagicMock()
    trace.get_current_span.return_value = span

    monkeypatch.setattr(llm_metrics, "LLM_REQUESTS", requests)
    monkeypatch.setattr(llm_metrics, "LLM_LATENCY", latency)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_PROMPT", prompt_tokens)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_COMPLETION", completion_tokens)
    monkeypatch.setattr(llm_metrics, "LLM_TOKENS_TOTAL", total_tokens)
    monkeypatch.setattr(llm_metrics, "trace", trace)

    llm_metrics.record_llm_call_metrics(
        component="router",
        llm=SimpleNamespace(),
        response=SimpleNamespace(content="ok"),
        start_time=0.0,
        status="error",
    )

    requests.labels.assert_called_once_with(model="unknown", component="router", status="error")
    requests_child.inc.assert_called_once()
    latency.labels.assert_called_once_with(model="unknown", component="router")
    latency_child.observe.assert_called_once()
    prompt_tokens.labels.assert_not_called()
    completion_tokens.labels.assert_not_called()
    total_tokens.labels.assert_not_called()
    span.set_attribute.assert_any_call("llm.model", "unknown")
    span.set_attribute.assert_any_call("llm.tokens.prompt", 0)
    span.set_attribute.assert_any_call("llm.tokens.completion", 0)
    span.set_attribute.assert_any_call("llm.tokens.total", 0)
    span.set_attribute.assert_any_call("llm.status", "error")
