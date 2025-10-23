from redis_sre_agent.agent.subgraphs.diagnose import (
    make_diagnose_prompt,
    parse_problems,
)


def test_make_diagnose_prompt_includes_summary_and_schema():
    prompt = make_diagnose_prompt("SIG_SUMMARY")
    assert "SIG_SUMMARY" in prompt
    assert "Provide a strict JSON array" in prompt
    # Spot-check schema hints
    assert "NodeInMaintenanceMode" in prompt
    assert '"critical","high","medium","low"' in prompt


def test_parse_problems_normalizes_and_filters():
    raw = """```json
[
  {"id": "P1", "category": "Performance", "title": "Slow ops", "severity": "high", "scope": "cluster", "evidence_keys": ["latency", 123]},
  {"id": "P2", "category": "UnknownCat", "title": "", "severity": "badsev", "scope": "", "evidence_keys": ["foo"]},
  {"id": "", "category": "Configuration", "title": "No id", "severity": "low", "scope": "node:1"}
]
```"""
    problems = parse_problems(raw)

    # Third item missing id should be filtered out
    assert len(problems) == 2

    p1, p2 = problems

    # P1 preserved and normalized
    assert p1["id"] == "P1"
    assert p1["category"] == "Performance"
    assert p1["severity"] == "high"
    assert p1["scope"] == "cluster"
    # evidence_keys cast to strings, ints allowed
    assert set(p1["evidence_keys"]) == {"latency", "123"}

    # P2 normalization: unknown category -> Other, bad severity -> medium, empty scope -> cluster
    assert p2["id"] == "P2"
    assert p2["category"] == "Other"
    assert p2["severity"] == "medium"
    assert p2["scope"] == "cluster"
    # Title should not be empty after normalization
    assert p2["title"]
