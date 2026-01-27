"""
Integration tests for retrieval around:
- Redis Enterprise Admin API endpoints (e.g., GET /v1/bdbs)
- rladmin command documentation (e.g., rladmin failover, rladmin bind)

These tests ingest a few specific docs and verify that semantic search retrieves
expected titles/content using traditional IR-style checks.
"""

import os
from pathlib import Path

import pytest

from redis_sre_agent.core.docket_tasks import (
    ingest_sre_document,
    search_knowledge_base,
)
from redis_sre_agent.core.redis import create_indices

PROJECT_ROOT = Path(__file__).parent.parent.parent


async def _ensure_ready(test_settings) -> bool:
    """Return True if environment appears ready for real embedding-backed search."""
    # Must have OpenAI API key for embeddings
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set; skipping ingestion + retrieval assertions.")
        return False
    # Create indices if needed using dependency injection
    await create_indices(config=test_settings)
    return True


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_admin_api_bdbs_retrieval(test_settings):
    """Ingest the Admin API bdbs page and verify retrieval for a targeted query."""
    if not await _ensure_ready(test_settings):
        return

    # Read Admin API bdbs page content
    bdbs_path = (
        PROJECT_ROOT / "redis-docs/content/operate/rs/references/rest-api/requests/bdbs/_index.md"
    )
    content = bdbs_path.read_text(encoding="utf-8")

    # Ingest with a stable title matching docs front matter
    await ingest_sre_document(
        title="Database requests",
        content=content,
        source=str(bdbs_path),
        category="rest_api",
        severity="info",
    )

    # Query for the databases GET endpoint
    query = "redis enterprise admin api get databases"
    result = await search_knowledge_base(query=query, limit=8)

    assert result["query"] == query
    assert isinstance(result.get("results"), list)

    titles = [r.get("title", "") for r in result["results"]]
    sources = [r.get("source", "") for r in result["results"]]
    contents = [r.get("content", "") for r in result["results"]]

    # Expect the bdbs page title or close variants
    assert any("database requests" in t.lower() for t in titles), (
        f"Expected 'Database requests' among titles; saw: {titles}"
    )

    # Ensure we actually retrieved the specific source file we ingested
    assert any("/references/rest-api/requests/bdbs/_index.md" in s for s in sources), (
        f"Expected source to include bdbs/_index.md; saw: {sources}"
    )

    # Require the example HTTP request with full arguments in the retrieved snippet
    assert any(("GET /v1/bdbs" in b) and ("/v1/bdbs?fields=uid,name" in b) for b in contents), (
        "Retrieval must return an example HTTP request including full arguments, e.g. 'GET /v1/bdbs?fields=uid,name'"
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_rladmin_retrieval(test_settings):
    """Ingest a couple rladmin command pages and verify retrieval for two queries."""
    if not await _ensure_ready(test_settings):
        return

    # Read rladmin docs
    failover_path = (
        PROJECT_ROOT / "redis-docs/content/operate/rs/references/cli-utilities/rladmin/failover.md"
    )
    bind_path = (
        PROJECT_ROOT / "redis-docs/content/operate/rs/references/cli-utilities/rladmin/bind.md"
    )

    failover_content = failover_path.read_text(encoding="utf-8")
    bind_content = bind_path.read_text(encoding="utf-8")

    # Ingest with titles matching the docs
    await ingest_sre_document(
        title="rladmin failover",
        content=failover_content,
        source=str(failover_path),
        category="rladmin",
        severity="info",
    )
    await ingest_sre_document(
        title="rladmin bind",
        content=bind_content,
        source=str(bind_path),
        category="rladmin",
        severity="info",
    )

    # Query: failover
    q1 = "rladmin failover database shards"
    res1 = await search_knowledge_base(query=q1, limit=8)
    t1 = [r.get("title", "").lower() for r in res1.get("results", [])]
    c1 = [r.get("content", "").lower() for r in res1.get("results", [])]

    assert any("rladmin failover" in t for t in t1), (
        f"Expected 'rladmin failover' among titles; saw: {t1}"
    )
    # Require the usage block to include command and key arguments
    assert any(
        ("rladmin failover" in b) and ("db:<id>" in b) and ("shard" in b) and ("immediate" in b)
        for b in c1
    ), (
        "Retrieval must include the full rladmin failover usage with arguments (db:<id>, shard ..., [immediate])"
    )

    # Query: bind endpoint policy
    q2 = "rladmin bind endpoint policy"
    res2 = await search_knowledge_base(query=q2, limit=8)
    t2 = [r.get("title", "").lower() for r in res2.get("results", [])]

    assert any("rladmin bind" in t for t in t2), f"Expected 'rladmin bind' among titles; saw: {t2}"

    # Find the specific bind.md result and assert its snippet includes the full policy usage
    bind_result = None
    for r in res2.get("results", []):
        if "rladmin bind" in r.get("title", "").lower() and "/rladmin/bind.md" in r.get(
            "source", ""
        ):
            bind_result = r
            break

    assert bind_result is not None, (
        "Expected a result for rladmin/bind.md but did not find one in search results"
    )

    bind_blob = bind_result.get("content", "").lower()
    assert "endpoint <id>" in bind_blob, "Bind snippet must show 'endpoint <id>' argument"
    assert "policy" in bind_blob, "Bind snippet must include the 'policy' subcommand"
    assert "all-master-shards" in bind_blob, "Bind snippet must include 'all-master-shards' option"
    assert "all-nodes" in bind_blob, "Bind snippet must include 'all-nodes' option"
    assert " single" in bind_blob, "Bind snippet must include 'single' option"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_retrieval_metrics_for_targeted_cases(test_settings):
    """Run IR metrics evaluation on a small set of targeted queries (structure checks)."""
    if not await _ensure_ready(test_settings):
        return

    from redis_sre_agent.evaluation.retrieval_eval import (
        RetrievalEvaluator,
        get_admin_api_retrieval_test_cases,
        get_rladmin_retrieval_test_cases,
    )

    evaluator = RetrievalEvaluator(k_values=[1, 3, 5])
    test_cases = get_admin_api_retrieval_test_cases() + get_rladmin_retrieval_test_cases()

    evaluation = await evaluator.evaluate_test_set(test_cases)

    # Structural assertions only; we don't fix exact metric values here
    assert hasattr(evaluation, "mean_precision_at_k")
    assert hasattr(evaluation, "mean_recall_at_k")
    assert hasattr(evaluation, "mean_reciprocal_rank")
    assert hasattr(evaluation, "mean_average_precision")
    assert hasattr(evaluation, "ndcg_at_k")

    assert 0 <= evaluation.mean_reciprocal_rank <= 1
    assert 0 <= evaluation.mean_average_precision <= 1

    for k in [1, 3, 5]:
        if k in evaluation.mean_precision_at_k:
            assert 0 <= evaluation.mean_precision_at_k[k] <= 1
        if k in evaluation.mean_recall_at_k:
            assert 0 <= evaluation.mean_recall_at_k[k] <= 1
        if k in evaluation.ndcg_at_k:
            assert 0 <= evaluation.ndcg_at_k[k] <= 1
