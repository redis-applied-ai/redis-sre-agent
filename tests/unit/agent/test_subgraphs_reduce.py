from redis_sre_agent.agent.subgraphs.reduce import reduce_plans


def test_reduce_plans_dedupe_and_order_and_sections():
    per_problem_results = [
        {
            "problem": {"id": "P1", "title": "Prob1", "severity": "high"},
            "summary": "sum1",
            "actions": [
                {"target": "db", "verb": "restart", "args": {"x": 1}},
                {"target": "db", "verb": "restart", "args": {"x": 1}},  # duplicate
            ],
        },
        {
            "problem": {"id": "P2", "title": "Prob2", "severity": "critical"},
            "summary": "sum2",
            "actions": [
                {"target": "db", "verb": "restart", "args": {"x": 1}},  # duplicate across problems
                {"target": "db", "verb": "scale", "args": {"n": 2}},
            ],
        },
        {
            "problem": {"id": "P3", "title": "Prob3", "severity": "low"},
            "summary": "sum3",
            "actions": [],
        },
    ]

    leftover_problems = [
        {"id": "P4", "title": "Leftover", "severity": "medium"},
    ]

    (
        merged_actions,
        per_problem_results_sorted,
        skipped_lines,
        initial_assessment_lines,
        what_im_seeing_lines,
    ) = reduce_plans(per_problem_results, leftover_problems)

    # Dedupe kept only two actions: restart, scale (order not guaranteed; compare as sets)
    verbs = {a.get("verb") for a in merged_actions}
    assert verbs == {"restart", "scale"}

    # Sorted by severity: critical -> high -> low
    sorted_ids = [r["problem"]["id"] for r in per_problem_results_sorted]
    assert sorted_ids == ["P2", "P1", "P3"]

    # Skipped lines include leftover problem with severity
    assert any("Leftover" in line and "medium" in line for line in skipped_lines)

    # Initial assessment mentions each problem title and includes severity text
    assert any("Prob1" in line and "severity" in line for line in initial_assessment_lines)

    # What I'm seeing includes summary snippets
    assert any("Prob2" in line and "sum2" in line for line in what_im_seeing_lines)
