from redis_sre_agent.agent.subgraphs.reduce import reduce_plans


def test_reduce_plans_dedupe_same_args_different_order():
    # Two problems propose the same action with args; dedupe should keep one
    per_problem_results = [
        {
            "problem": {"id": "P1", "title": "A", "severity": "medium"},
            "summary": "s1",
            "actions": [
                {"target": "db", "verb": "configure", "args": {"b": 2, "a": 1}},
            ],
        },
        {
            "problem": {"id": "P2", "title": "B", "severity": "low"},
            "summary": "s2",
            "actions": [
                {"target": "db", "verb": "configure", "args": {"a": 1, "b": 2}},
            ],
        },
    ]

    merged_actions, *_ = reduce_plans(per_problem_results, leftover_problems=[])
    assert len([a for a in merged_actions if a.get("verb") == "configure"]) == 1
