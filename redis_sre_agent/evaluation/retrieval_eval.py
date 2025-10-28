"""
Retrieval Evaluation for Redis SRE Agent Knowledge Base

This module provides evaluation capabilities for assessing the quality of
knowledge base search and retrieval using standard IR metrics.

Metrics evaluated:
- Precision@K
- Recall@K
- Mean Reciprocal Rank (MRR)
- Normalized Discounted Cumulative Gain (NDCG@K)
- Mean Average Precision (MAP)
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional

from redis_sre_agent.core.docket_tasks import search_knowledge_base

logger = logging.getLogger(__name__)


@dataclass
class RetrievalTestCase:
    """A single test case for retrieval evaluation."""

    query: str
    relevant_docs: List[str]  # List of document IDs or titles that should be retrieved
    description: str
    category: Optional[str] = None
    difficulty: str = "medium"  # easy, medium, hard


@dataclass
class RetrievalResult:
    """Results from a single retrieval test."""

    query: str
    retrieved_docs: List[str]
    relevant_docs: List[str]
    precision_at_k: Dict[int, float]
    recall_at_k: Dict[int, float]
    reciprocal_rank: float
    ndcg_at_k: Dict[int, float]
    average_precision: float


@dataclass
class RetrievalEvaluation:
    """Overall retrieval evaluation results."""

    test_cases: int
    mean_precision_at_k: Dict[int, float]
    mean_recall_at_k: Dict[int, float]
    mean_reciprocal_rank: float
    mean_ndcg_at_k: Dict[int, float]
    mean_average_precision: float
    results: List[RetrievalResult]
    # Backward-compat alias expected by some tests
    ndcg_at_k: Optional[Dict[int, float]] = None


class RetrievalEvaluator:
    """Evaluator for knowledge base retrieval performance."""

    def __init__(self, k_values: List[int] = None):
        self.k_values = k_values or [1, 3, 5, 10]

    def calculate_precision_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """Calculate Precision@K."""
        if k <= 0 or not retrieved:
            return 0.0

        retrieved_at_k = retrieved[:k]
        relevant_retrieved = len([doc for doc in retrieved_at_k if doc in relevant])
        return relevant_retrieved / len(retrieved_at_k)

    def calculate_recall_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """Calculate Recall@K."""
        if not relevant or k <= 0:
            return 0.0

        retrieved_at_k = retrieved[:k]
        relevant_retrieved = len([doc for doc in retrieved_at_k if doc in relevant])
        return relevant_retrieved / len(relevant)

    def calculate_reciprocal_rank(self, retrieved: List[str], relevant: List[str]) -> float:
        """Calculate Mean Reciprocal Rank (MRR)."""
        for i, doc in enumerate(retrieved):
            if doc in relevant:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_ndcg_at_k(self, retrieved: List[str], relevant: List[str], k: int) -> float:
        """Calculate Normalized Discounted Cumulative Gain@K."""
        if k <= 0 or not relevant:
            return 0.0

        # Calculate DCG@K
        dcg = 0.0
        for i, doc in enumerate(retrieved[:k]):
            relevance = 1.0 if doc in relevant else 0.0
            dcg += relevance / (1.0 + i)  # Using log base 2: log2(1+i)

        # Calculate ideal DCG@K
        ideal_dcg = sum(1.0 / (1.0 + i) for i in range(min(k, len(relevant))))

        return dcg / ideal_dcg if ideal_dcg > 0 else 0.0

    def calculate_average_precision(self, retrieved: List[str], relevant: List[str]) -> float:
        """Calculate Average Precision (AP)."""
        if not relevant:
            return 0.0

        precision_sum = 0.0
        relevant_found = 0

        for i, doc in enumerate(retrieved):
            if doc in relevant:
                relevant_found += 1
                precision_at_i = relevant_found / (i + 1)
                precision_sum += precision_at_i

        return precision_sum / len(relevant) if len(relevant) > 0 else 0.0

    def calculate_precision_at_k_fuzzy(
        self, retrieved: List[str], fuzzy_relevant: List[str], k: int
    ) -> float:
        """Calculate Precision@K with fuzzy matching."""
        if k <= 0 or not retrieved:
            return 0.0

        retrieved_at_k = retrieved[:k]
        relevant_retrieved = sum(
            1
            for i, doc in enumerate(retrieved_at_k)
            if i < len(fuzzy_relevant) and fuzzy_relevant[i] is not None
        )
        return relevant_retrieved / len(retrieved_at_k)

    def calculate_recall_at_k_fuzzy(
        self, fuzzy_relevant_docs: List[str], original_relevant: List[str], k: int
    ) -> float:
        """Calculate Recall@K with fuzzy matching."""
        if not original_relevant or k <= 0:
            return 0.0

        # Count unique relevant docs found (up to k)
        unique_relevant_found = len(set(fuzzy_relevant_docs[:k]))
        return min(unique_relevant_found / len(original_relevant), 1.0)

    def calculate_ndcg_at_k_fuzzy(
        self, retrieved: List[str], fuzzy_relevant: List[str], k: int
    ) -> float:
        """Calculate NDCG@K with fuzzy matching."""
        if k <= 0 or not fuzzy_relevant:
            return 0.0

        # Calculate DCG@K
        dcg = 0.0
        for i, doc in enumerate(retrieved[:k]):
            relevance = 1.0 if i < len(fuzzy_relevant) and fuzzy_relevant[i] is not None else 0.0
            dcg += relevance / (1.0 + i)  # Using log base 2: log2(1+i)

        # Calculate ideal DCG@K
        num_relevant = sum(1 for doc in fuzzy_relevant[:k] if doc is not None)
        ideal_dcg = sum(1.0 / (1.0 + i) for i in range(min(k, num_relevant)))

        return dcg / ideal_dcg if ideal_dcg > 0 else 0.0

    def calculate_reciprocal_rank_fuzzy(
        self, retrieved: List[str], fuzzy_relevant: List[str]
    ) -> float:
        """Calculate MRR with fuzzy matching."""
        for i, doc in enumerate(retrieved):
            if i < len(fuzzy_relevant) and fuzzy_relevant[i] is not None:
                return 1.0 / (i + 1)
        return 0.0

    def calculate_average_precision_fuzzy(
        self, retrieved: List[str], fuzzy_relevant: List[str]
    ) -> float:
        """Calculate Average Precision with fuzzy matching."""
        relevant_count = sum(1 for doc in fuzzy_relevant if doc is not None)
        if relevant_count == 0:
            return 0.0

        precision_sum = 0.0
        relevant_found = 0

        for i, doc in enumerate(retrieved):
            if i < len(fuzzy_relevant) and fuzzy_relevant[i] is not None:
                relevant_found += 1
                precision_at_i = relevant_found / (i + 1)
                precision_sum += precision_at_i

        return precision_sum / relevant_count if relevant_count > 0 else 0.0

    async def evaluate_single_query(
        self, test_case: RetrievalTestCase, limit: int = 10
    ) -> RetrievalResult:
        """Evaluate retrieval performance for a single query."""
        logger.info(f"Evaluating query: {test_case.query}")

        # Perform search
        try:
            search_results = await search_knowledge_base(
                query=test_case.query, category=test_case.category, limit=limit
            )

            # Extract document titles/IDs from search results
            retrieved_docs = []
            if search_results and isinstance(search_results, dict):
                # Handle formatted search result structure
                results_list = search_results.get("results", [])
                for result in results_list:
                    # Use title as document identifier
                    title = result.get("title", "") if isinstance(result, dict) else ""
                    if title:
                        retrieved_docs.append(title)
            elif isinstance(search_results, list):
                # Handle direct list of results
                for result in search_results:
                    title = result.get("title", "") if isinstance(result, dict) else ""
                    if title:
                        retrieved_docs.append(title)

            logger.info(f"Retrieved {len(retrieved_docs)} documents for query")

        except Exception as e:
            logger.error(f"Search failed for query '{test_case.query}': {e}")
            retrieved_docs = []

        # Calculate metrics using fuzzy matching for document titles
        # This accounts for chunked documents with "(Part N)" suffixes
        def fuzzy_match(retrieved_title: str, relevant_title: str) -> bool:
            # Remove common suffixes and normalize
            retrieved_clean = retrieved_title.lower().replace("(part", "").strip()
            relevant_clean = relevant_title.lower().strip()

            # Check if relevant title is contained in retrieved title or vice versa
            return (
                relevant_clean in retrieved_clean
                or retrieved_clean in relevant_clean
                or
                # Check for exact match without part numbers
                retrieved_title.lower().split("(")[0].strip() == relevant_clean
            )

        # Create fuzzy-matched relevant list for each retrieved doc
        fuzzy_relevant = []
        for retrieved_doc in retrieved_docs:
            is_relevant = any(
                fuzzy_match(retrieved_doc, rel_doc) for rel_doc in test_case.relevant_docs
            )
            fuzzy_relevant.append(retrieved_doc if is_relevant else None)

        # Filter to just the relevant retrieved docs for calculations
        fuzzy_relevant_docs = [doc for doc in fuzzy_relevant if doc is not None]

        precision_at_k = {}
        recall_at_k = {}
        ndcg_at_k = {}

        for k in self.k_values:
            precision_at_k[k] = self.calculate_precision_at_k_fuzzy(
                retrieved_docs, fuzzy_relevant, k
            )
            recall_at_k[k] = self.calculate_recall_at_k_fuzzy(
                fuzzy_relevant_docs, test_case.relevant_docs, k
            )
            ndcg_at_k[k] = self.calculate_ndcg_at_k_fuzzy(retrieved_docs, fuzzy_relevant, k)

        reciprocal_rank = self.calculate_reciprocal_rank_fuzzy(retrieved_docs, fuzzy_relevant)
        average_precision = self.calculate_average_precision_fuzzy(retrieved_docs, fuzzy_relevant)

        return RetrievalResult(
            query=test_case.query,
            retrieved_docs=retrieved_docs,
            relevant_docs=test_case.relevant_docs,
            precision_at_k=precision_at_k,
            recall_at_k=recall_at_k,
            reciprocal_rank=reciprocal_rank,
            ndcg_at_k=ndcg_at_k,
            average_precision=average_precision,
        )

    async def evaluate_test_set(self, test_cases: List[RetrievalTestCase]) -> RetrievalEvaluation:
        """Evaluate retrieval performance across a test set."""
        logger.info(f"Starting retrieval evaluation on {len(test_cases)} test cases")

        results = []
        for test_case in test_cases:
            result = await self.evaluate_single_query(test_case)
            results.append(result)

        # Aggregate metrics
        mean_precision_at_k = {}
        mean_recall_at_k = {}
        mean_ndcg_at_k = {}

        for k in self.k_values:
            precisions = [r.precision_at_k[k] for r in results]
            recalls = [r.recall_at_k[k] for r in results]
            ndcgs = [r.ndcg_at_k[k] for r in results]

            mean_precision_at_k[k] = statistics.mean(precisions) if precisions else 0.0
            mean_recall_at_k[k] = statistics.mean(recalls) if recalls else 0.0
            mean_ndcg_at_k[k] = statistics.mean(ndcgs) if ndcgs else 0.0

        reciprocal_ranks = [r.reciprocal_rank for r in results]
        mean_reciprocal_rank = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0.0

        average_precisions = [r.average_precision for r in results]
        mean_average_precision = statistics.mean(average_precisions) if average_precisions else 0.0

        eval_result = RetrievalEvaluation(
            test_cases=len(test_cases),
            mean_precision_at_k=mean_precision_at_k,
            mean_recall_at_k=mean_recall_at_k,
            mean_reciprocal_rank=mean_reciprocal_rank,
            mean_ndcg_at_k=mean_ndcg_at_k,
            mean_average_precision=mean_average_precision,
            results=results,
        )

        # Provide alias used in tests
        eval_result.ndcg_at_k = mean_ndcg_at_k
        return eval_result

    # Backward-compat wrapper expected by tests
    async def evaluate_retrieval(self, test_cases: List[RetrievalTestCase]):
        return await self.evaluate_test_set(test_cases)

    def generate_report(self, evaluation: RetrievalEvaluation) -> str:
        """Generate a detailed evaluation report."""
        report = []
        report.append("# Knowledge Base Retrieval Evaluation Report")
        report.append("")
        report.append(f"**Test Cases Evaluated**: {evaluation.test_cases}")
        report.append("")

        # Summary metrics
        report.append("## Summary Metrics")
        report.append("")
        report.append(f"**Mean Reciprocal Rank (MRR)**: {evaluation.mean_reciprocal_rank:.3f}")
        report.append(f"**Mean Average Precision (MAP)**: {evaluation.mean_average_precision:.3f}")
        report.append("")

        # Precision@K table
        report.append("### Precision@K")
        report.append("| K | Precision@K |")
        report.append("|---|-------------|")
        for k in sorted(evaluation.mean_precision_at_k.keys()):
            report.append(f"| {k} | {evaluation.mean_precision_at_k[k]:.3f} |")
        report.append("")

        # Recall@K table
        report.append("### Recall@K")
        report.append("| K | Recall@K |")
        report.append("|---|----------|")
        for k in sorted(evaluation.mean_recall_at_k.keys()):
            report.append(f"| {k} | {evaluation.mean_recall_at_k[k]:.3f} |")
        report.append("")

        # NDCG@K table
        report.append("### NDCG@K")
        report.append("| K | NDCG@K |")
        report.append("|---|--------|")
        for k in sorted(evaluation.mean_ndcg_at_k.keys()):
            report.append(f"| {k} | {evaluation.mean_ndcg_at_k[k]:.3f} |")
        report.append("")

        # Individual results
        report.append("## Individual Query Results")
        report.append("")

        for i, result in enumerate(evaluation.results, 1):
            report.append(f"### Query {i}: {result.query}")
            report.append(f"**Relevant Documents**: {len(result.relevant_docs)}")
            report.append(f"**Retrieved Documents**: {len(result.retrieved_docs)}")
            report.append(f"**Reciprocal Rank**: {result.reciprocal_rank:.3f}")
            report.append(f"**Average Precision**: {result.average_precision:.3f}")

            # Show top retrieved documents
            if result.retrieved_docs:
                report.append("**Top Retrieved:**")
                for j, doc in enumerate(result.retrieved_docs[:5], 1):
                    relevance = "✓" if doc in result.relevant_docs else "✗"
                    report.append(f"  {j}. {relevance} {doc}")

            report.append("")

        return "\n".join(report)


def get_redis_retrieval_test_cases() -> List[RetrievalTestCase]:
    """Get predefined test cases for Redis knowledge base retrieval evaluation."""

    test_cases = [
        RetrievalTestCase(
            query="Redis memory usage commands",
            relevant_docs=[
                "MEMORY USAGE",
                "MEMORY STATS",
                "MEMORY DOCTOR",
                "INFO",
                "Memory optimization",
            ],
            description="Query about Redis memory-related commands",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="How to check Redis latency and slow queries",
            relevant_docs=[
                "SLOWLOG",
                "LATENCY HISTORY",
                "LATENCY LATEST",
                "MONITOR",
                "Diagnosing latency issues",
            ],
            description="Query about Redis performance monitoring",
            difficulty="medium",
        ),
        RetrievalTestCase(
            query="Redis replication setup and configuration",
            relevant_docs=["REPLICAOF", "ROLE", "Redis replication", "Redis configuration"],
            description="Query about Redis replication",
            difficulty="medium",
        ),
        RetrievalTestCase(
            query="Redis JSON operations and search",
            relevant_docs=["JSONGET", "JSONSET", "JSONDEL", "JSONTYPE", "JSON", "Search and query"],
            description="Query about Redis JSON functionality",
            difficulty="medium",
        ),
        RetrievalTestCase(
            query="Redis security authentication and access control",
            relevant_docs=[
                "AUTH",
                "ACL SETUSER",
                "ACL GETUSER",
                "ACL LIST",
                "ACL USERS",
                "Redis security",
            ],
            description="Query about Redis security features",
            difficulty="medium",
        ),
        RetrievalTestCase(
            query="Redis persistence RDB and AOF configuration",
            relevant_docs=["Redis persistence", "CONFIG GET", "CONFIG SET", "Redis configuration"],
            description="Query about Redis persistence mechanisms",
            difficulty="hard",
        ),
        RetrievalTestCase(
            query="Redis cluster information and node management",
            relevant_docs=["CLUSTER INFO", "CLUSTER NODES", "Redis administration"],
            description="Query about Redis clustering",
            difficulty="hard",
        ),
        RetrievalTestCase(
            query="Redis hash operations HSET HGET",
            relevant_docs=["HSET", "HGET", "HGETALL", "HMGET", "HMSET          (deprecated)"],
            description="Query about Redis hash data type operations",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="Redis list operations push and pop",
            relevant_docs=["LPUSH", "RPUSH", "LPOP", "RPOP", "LLEN"],
            description="Query about Redis list data type operations",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="Redis key expiration and TTL management",
            relevant_docs=["EXPIRE", "TTL", "EXISTS", "DEL"],
            description="Query about Redis key lifecycle management",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="Redis full-text search index creation and querying",
            relevant_docs=["FTCREATE", "FTSEARCH", "FTINFO", "Search and query"],
            description="Query about Redis Search module functionality",
            difficulty="hard",
        ),
        RetrievalTestCase(
            query="Redis set operations add and check membership",
            relevant_docs=["SADD", "SISMEMBER", "SMEMBERS", "SCARD"],
            description="Query about Redis set data type operations",
            difficulty="easy",
        ),
    ]

    return test_cases


def get_rladmin_retrieval_test_cases() -> List[RetrievalTestCase]:
    """Small set of retrieval test cases focused on rladmin commands."""
    return [
        RetrievalTestCase(
            query="rladmin failover database shards",
            relevant_docs=["rladmin failover"],
            description="Finds the rladmin command to fail over primary shards to replicas",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="rladmin bind endpoint policy",
            relevant_docs=["rladmin bind"],
            description="Finds docs about managing endpoint proxy policy using rladmin bind",
            difficulty="medium",
        ),
    ]


def get_admin_api_retrieval_test_cases() -> List[RetrievalTestCase]:
    """Small set of retrieval test cases focused on Redis Enterprise Admin API."""
    return [
        RetrievalTestCase(
            query="redis enterprise admin api get databases",
            relevant_docs=["Database requests"],
            description="Should retrieve the bdbs index page documenting GET /v1/bdbs",
            difficulty="easy",
        ),
        RetrievalTestCase(
            query="redis enterprise admin api get nodes",
            relevant_docs=["Node requests", "Nodes"],
            description="Should retrieve the nodes index page documenting GET /v1/nodes",
            difficulty="easy",
        ),
    ]
