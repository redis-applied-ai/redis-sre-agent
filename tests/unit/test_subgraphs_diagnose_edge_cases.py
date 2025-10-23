from redis_sre_agent.agent.subgraphs.diagnose import make_diagnose_prompt, parse_problems


def test_parse_problems_malformed_and_nonlist():
    assert parse_problems("not json") == []
    assert parse_problems("{}") == []  # non-list root


def test_parse_problems_mixed_case_normalization():
    raw = """```json
[
  {"id": "P1", "category": "performance", "title": "t", "severity": "HIGH", "scope": "node:3", "evidence_keys": [true, null, "x"]}
]
```"""
    problems = parse_problems(raw)
    assert len(problems) == 1
    p = problems[0]
    # category not matched due to case -> Other; severity lowercased and allowed
    assert p["category"] == "Other"
    assert p["severity"] == "high"
    assert p["scope"] == "node:3"
    # evidence_keys keeps only str/int and casts to str (bool counts as int)
    assert set(p["evidence_keys"]) == {"True", "x"}


def test_make_diagnose_prompt_smoke():
    prompt = make_diagnose_prompt("abc")
    assert "abc" in prompt
    assert "strict JSON array" in prompt
