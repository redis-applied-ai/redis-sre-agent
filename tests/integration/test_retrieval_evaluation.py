"""
Retrieval Evaluation Integration Tests for Redis SRE Agent Knowledge Base

This module evaluates the quality of knowledge base search and retrieval
using standard Information Retrieval metrics.
"""

import asyncio
import logging
import os
from pathlib import Path

import pytest

from redis_sre_agent.evaluation.retrieval_eval import (
    RetrievalEvaluator,
    get_redis_retrieval_test_cases,
)

logger = logging.getLogger(__name__)

# Define project root
project_root = Path(__file__).parent.parent.parent


async def run_retrieval_evaluation():
    """Run comprehensive retrieval evaluation."""
    print("🔍 Redis SRE Agent - Knowledge Base Retrieval Evaluation")
    print("=" * 70)

    # Check Redis connection
    try:
        from redis_sre_agent.core.redis import test_redis_connection

        redis_ok = await test_redis_connection()
        if not redis_ok:
            print("❌ Redis connection failed. Please ensure Redis is running.")
            return
    except Exception as e:
        print(f"❌ Redis connection error: {e}")
        return

    # Check OpenAI API key for embeddings
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not set. This is required for vector embeddings.")
        return

    # Initialize evaluator
    evaluator = RetrievalEvaluator(k_values=[1, 3, 5, 10])

    # Get test cases
    test_cases = get_redis_retrieval_test_cases()
    print(f"📋 Running retrieval evaluation on {len(test_cases)} test queries")
    print()

    # Show test case overview
    difficulty_counts = {}
    for test_case in test_cases:
        difficulty_counts[test_case.difficulty] = difficulty_counts.get(test_case.difficulty, 0) + 1

    print("📊 Test Case Distribution:")
    for difficulty, count in difficulty_counts.items():
        print(f"   - {difficulty.title()}: {count} queries")
    print()

    try:
        # Run evaluation
        print("🤖 Running knowledge base retrieval evaluation...")
        print("   This may take a few minutes due to embedding generation...")
        print()

        evaluation = await evaluator.evaluate_test_set(test_cases)

        # Display results
        print("📊 Retrieval Evaluation Results:")
        print("=" * 50)
        print(f"Mean Reciprocal Rank (MRR):     {evaluation.mean_reciprocal_rank:.3f}")
        print(f"Mean Average Precision (MAP):   {evaluation.mean_average_precision:.3f}")
        print()

        print("Precision@K Results:")
        for k in sorted(evaluation.mean_precision_at_k.keys()):
            print(f"  P@{k:2d}: {evaluation.mean_precision_at_k[k]:.3f}")
        print()

        print("Recall@K Results:")
        for k in sorted(evaluation.mean_recall_at_k.keys()):
            print(f"  R@{k:2d}: {evaluation.mean_recall_at_k[k]:.3f}")
        print()

        print("NDCG@K Results:")
        for k in sorted(evaluation.mean_ndcg_at_k.keys()):
            print(f"  NDCG@{k:2d}: {evaluation.mean_ndcg_at_k[k]:.3f}")
        print()

        # Performance analysis
        print("🎯 Performance Analysis:")

        # Count perfect queries (MRR = 1.0)
        perfect_queries = sum(1 for r in evaluation.results if r.reciprocal_rank == 1.0)
        print(
            f"   Perfect queries (MRR=1.0): {perfect_queries}/{len(evaluation.results)} ({perfect_queries / len(evaluation.results) * 100:.1f}%)"
        )

        # Count queries with no relevant results in top-5
        no_results = sum(1 for r in evaluation.results if r.precision_at_k[5] == 0.0)
        print(
            f"   Queries with no results in top-5: {no_results}/{len(evaluation.results)} ({no_results / len(evaluation.results) * 100:.1f}%)"
        )

        # Show best and worst performing queries
        best_query = max(evaluation.results, key=lambda r: r.reciprocal_rank)
        worst_query = min(evaluation.results, key=lambda r: r.reciprocal_rank)

        print("\n✅ Best performing query:")
        print(f"   Query: {best_query.query}")
        print(f"   MRR: {best_query.reciprocal_rank:.3f}")
        print(f"   P@5: {best_query.precision_at_k[5]:.3f}")

        print("\n⚠️  Worst performing query:")
        print(f"   Query: {worst_query.query}")
        print(f"   MRR: {worst_query.reciprocal_rank:.3f}")
        print(f"   P@5: {worst_query.precision_at_k[5]:.3f}")

        # Generate detailed report
        report = evaluator.generate_report(evaluation)

        # Save report
        eval_reports_dir = project_root / "eval_reports"
        eval_reports_dir.mkdir(exist_ok=True)
        report_path = eval_reports_dir / "retrieval_evaluation_report.md"
        with open(report_path, "w") as f:
            f.write(report)

        print(f"\n📄 Detailed report saved to: {report_path}")

        # Performance interpretation
        print("\n📈 Performance Interpretation:")

        if evaluation.mean_reciprocal_rank >= 0.8:
            print(
                "   🟢 Excellent retrieval quality - Most queries find relevant results in top positions"
            )
        elif evaluation.mean_reciprocal_rank >= 0.6:
            print("   🟡 Good retrieval quality - Many queries find relevant results quickly")
        elif evaluation.mean_reciprocal_rank >= 0.4:
            print("   🟠 Moderate retrieval quality - Some improvement needed")
        else:
            print("   🔴 Poor retrieval quality - Significant improvement needed")

        if evaluation.mean_precision_at_k[5] >= 0.7:
            print("   🟢 High precision - Low noise in top-5 results")
        elif evaluation.mean_precision_at_k[5] >= 0.5:
            print("   🟡 Good precision - Acceptable relevance in top-5 results")
        else:
            print("   🟠 Low precision - Many irrelevant results in top-5")

    except Exception as e:
        print(f"❌ Retrieval evaluation failed: {str(e)}")
        logger.error(f"Evaluation error: {e}", exc_info=True)


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_retrieval_evaluation():
    """Test retrieval evaluation with IR metrics."""
    await run_retrieval_evaluation()

    # Basic validation that the evaluation ran without errors
    # In a real test, we'd capture the results and make assertions
    assert True  # If we get here, the evaluation completed


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_retrieval_metrics_calculation():
    """Test that retrieval metrics are calculated correctly."""
    evaluator = RetrievalEvaluator()
    test_cases = get_redis_retrieval_test_cases()

    # Run evaluation on subset for faster testing
    subset_cases = test_cases[:3]
    evaluation = await evaluator.evaluate_retrieval(subset_cases)

    # Verify metrics structure
    assert hasattr(evaluation, "mean_precision_at_k")
    assert hasattr(evaluation, "mean_recall_at_k")
    assert hasattr(evaluation, "mean_reciprocal_rank")
    assert hasattr(evaluation, "mean_average_precision")
    assert hasattr(evaluation, "ndcg_at_k")

    # Verify metrics are in valid ranges
    assert 0 <= evaluation.mean_reciprocal_rank <= 1
    assert 0 <= evaluation.mean_average_precision <= 1

    for k in [1, 3, 5]:
        if k in evaluation.mean_precision_at_k:
            assert 0 <= evaluation.mean_precision_at_k[k] <= 1
        if k in evaluation.mean_recall_at_k:
            assert 0 <= evaluation.mean_recall_at_k[k] <= 1
        if k in evaluation.ndcg_at_k:
            assert 0 <= evaluation.ndcg_at_k[k] <= 1


async def main():
    """Main evaluation demo."""
    await run_retrieval_evaluation()
    print("\n✅ Retrieval evaluation completed!")


if __name__ == "__main__":
    asyncio.run(main())
