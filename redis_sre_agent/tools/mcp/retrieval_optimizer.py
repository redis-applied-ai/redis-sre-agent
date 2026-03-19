"""Retrieval Optimizer MCP Server integration.

This module provides helper functions for configuring the Redis Retrieval Optimizer
MCP server, which provides tools for optimizing Redis-based information retrieval.

The retrieval-optimizer package provides:
- Grid studies: Compare embedding models and search methods
- Bayesian optimization: Fine-tune index configurations
- Search studies: Test search methods on existing indexes
- Threshold optimization: Tune semantic cache and router thresholds

Installation:
    pip install redis-retrieval-optimizer
    # or
    uv add redis-retrieval-optimizer

Usage:
    1. Add the configuration to your config.yaml:

        mcp_servers:
          retrieval-optimizer:
            command: uv
            args:
              - run
              - redis-retrieval-optimizer-mcp
            env:
              REDIS_URL: ${REDIS_URL}

    2. Or use the helper function to create the config programmatically:

        from redis_sre_agent.tools.mcp.retrieval_optimizer import (
            get_retrieval_optimizer_config,
        )

        config = get_retrieval_optimizer_config()
"""

from typing import Any, Dict, Optional


def get_retrieval_optimizer_config(
    redis_url: str = "${REDIS_URL}",
    retrieval_optimizer_dir: Optional[str] = None,
    include_all_tools: bool = False,
) -> Dict[str, Any]:
    """Create MCP server configuration for the Redis Retrieval Optimizer.

    Args:
        redis_url: Redis URL to use for optimization studies. Supports
            environment variable expansion (e.g., "${REDIS_URL}").
        retrieval_optimizer_dir: Optional path to the retrieval-optimizer directory.
            If provided, uses --directory flag for uv run. If None, assumes the
            package is installed in the environment.
        include_all_tools: If True, includes all tools from the server.
            If False (default), only includes the most commonly used tools
            with SRE-focused descriptions.

    Returns:
        MCPServerConfig-compatible dictionary for use in mcp_servers config.

    Example:
        >>> config = get_retrieval_optimizer_config()
        >>> settings.mcp_servers["retrieval-optimizer"] = config
    """
    # Build command arguments
    args = ["run"]
    if retrieval_optimizer_dir:
        args.extend(["--directory", retrieval_optimizer_dir])
    args.append("redis-retrieval-optimizer-mcp")

    config: Dict[str, Any] = {
        "command": "uv",
        "args": args,
        "env": {"REDIS_URL": redis_url},
    }

    if not include_all_tools:
        # Include commonly used tools with SRE-focused descriptions
        config["tools"] = {
            "run_grid_study_tool": {
                "description": (
                    "Run a grid search study to compare embedding models and search "
                    "methods. Use this to find the best-performing retrieval "
                    "configuration for your Redis-based search system.\n\n{original}"
                ),
            },
            "run_bayes_study_tool": {
                "description": (
                    "Run Bayesian optimization to fine-tune Redis index configurations. "
                    "Use this after grid study to optimize HNSW parameters, vector data "
                    "types, and other index settings for better performance.\n\n{original}"
                ),
            },
            "run_search_study_tool": {
                "description": (
                    "Test different search methods on an existing Redis index without "
                    "recreating it. Ideal for A/B testing search strategies on "
                    "production data.\n\n{original}"
                ),
            },
            "optimize_cache_threshold": {
                "description": (
                    "Optimize the distance threshold for a RedisVL SemanticCache. "
                    "Use this to improve cache hit rates while maintaining relevance "
                    "quality.\n\n{original}"
                ),
            },
            "optimize_router_threshold": {
                "description": (
                    "Optimize distance thresholds for a RedisVL SemanticRouter. "
                    "Use this to improve routing accuracy across different routes.\n\n"
                    "{original}"
                ),
            },
            "get_index_info": {
                "description": (
                    "Get information about an existing Redis search index including "
                    "document count, memory usage, and field configuration. Use this "
                    "to understand the current state of an index.\n\n{original}"
                ),
            },
            "evaluate_search_results": {
                "description": (
                    "Evaluate search results against ground truth relevance labels. "
                    "Computes NDCG, recall, precision, and F1 metrics to measure "
                    "retrieval quality.\n\n{original}"
                ),
            },
            "estimate_memory_usage": {
                "description": (
                    "Estimate memory requirements for an index configuration. "
                    "Use this for capacity planning before creating large indexes.\n\n"
                    "{original}"
                ),
            },
        }

    return config


# Convenience constant with default configuration
DEFAULT_RETRIEVAL_OPTIMIZER_CONFIG = get_retrieval_optimizer_config()

