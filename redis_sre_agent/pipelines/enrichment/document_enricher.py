"""
Document enrichment pipeline for improving search quality.

This module enhances scraped documents with semantic metadata, topical classifications,
and operational context to improve search relevance and discovery.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List

import openai

logger = logging.getLogger(__name__)


class DocumentEnricher:
    """Enriches documents with semantic metadata for improved search quality."""

    def __init__(self, openai_api_key: str):
        self.client = openai.AsyncOpenAI(api_key=openai_api_key)

        # Redis command patterns for classification
        self.command_patterns = {
            "memory": ["MEMORY", "INFO memory"],
            "replication": ["REPLICAOF", "ROLE", "PSYNC"],
            "cluster": ["CLUSTER"],
            "security": ["AUTH", "ACL"],
            "persistence": ["SAVE", "BGSAVE", "LASTSAVE"],
            "monitoring": ["INFO", "MONITOR", "SLOWLOG", "LATENCY"],
            "search": ["FT.", "FT_"],
            "json": ["JSON"],
            "streams": ["XADD", "XREAD", "XGROUP"],
            "hash": ["HSET", "HGET", "HMSET", "HMGET"],
            "list": ["LPUSH", "RPUSH", "LPOP", "RPOP", "LLEN"],
            "set": ["SADD", "SREM", "SMEMBERS", "SISMEMBER"],
            "sorted_set": ["ZADD", "ZRANGE", "ZREM", "ZSCORE"],
            "string": ["SET", "GET", "APPEND", "STRLEN"],
            "key_management": ["DEL", "EXISTS", "EXPIRE", "TTL", "TYPE", "KEYS", "SCAN"],
        }

        # Operational scenarios mapping
        self.operational_scenarios = {
            "troubleshooting": [
                "debug",
                "diagnose",
                "issue",
                "problem",
                "error",
                "slow",
                "latency",
            ],
            "monitoring": ["info", "stats", "status", "health", "metrics", "performance"],
            "configuration": ["config", "setup", "configure", "settings", "parameter"],
            "optimization": ["optimize", "performance", "tuning", "efficient", "speed"],
            "administration": ["admin", "manage", "maintenance", "backup", "restore"],
            "development": ["client", "application", "integrate", "library", "sdk"],
        }

    def is_redis_command(self, title: str) -> bool:
        """Check if document is about a Redis command."""
        title_upper = title.upper()

        # Check for uppercase Redis commands
        if re.match(r"^[A-Z][A-Z0-9_.]*(\s+|\(|$)", title_upper):
            return True

        # Check against known command patterns
        for category, patterns in self.command_patterns.items():
            for pattern in patterns:
                if pattern in title_upper:
                    return True

        return False

    def classify_by_patterns(self, title: str, content: str) -> Dict[str, Any]:
        """Classify document using pattern matching."""
        title_upper = title.upper()
        content_lower = content.lower()

        # Determine primary category
        primary_category = "general"
        for category, patterns in self.command_patterns.items():
            for pattern in patterns:
                if pattern in title_upper or pattern.lower() in content_lower:
                    primary_category = category
                    break
            if primary_category != "general":
                break

        # Determine operational scenarios
        scenarios = []
        for scenario, keywords in self.operational_scenarios.items():
            for keyword in keywords:
                if keyword in content_lower:
                    scenarios.append(scenario)
                    break

        return {
            "primary_category": primary_category,
            "operational_scenarios": list(set(scenarios)),
            "is_command": self.is_redis_command(title),
        }

    async def generate_semantic_description(self, title: str, content: str) -> Dict[str, str]:
        """Generate semantic description using LLM."""
        try:
            # Truncate content for API limits
            content_snippet = content[:1000] if content else "No content available"

            prompt = f"""
            Analyze this Redis documentation and provide:
            1. A concise one-line description (max 80 chars)
            2. Primary use case in 2-3 words
            3. When you would use this (one phrase)

            Title: {title}
            Content: {content_snippet}

            Respond in JSON format:
            {{
                "description": "Brief description of what this does",
                "use_case": "primary use case",
                "when_to_use": "when you would use this"
            }}
            """

            response = await self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
                temperature=0.1,
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            logger.warning(f"Failed to generate semantic description for '{title}': {e}")
            return {
                "description": "Redis documentation",
                "use_case": "general",
                "when_to_use": "as needed",
            }

    async def extract_related_commands(self, content: str) -> List[str]:
        """Extract mentioned Redis commands from content."""
        if not content:
            return []

        # Pattern to match Redis commands (uppercase words that look like commands)
        command_pattern = r"\b([A-Z][A-Z0-9_.]{2,})\b"

        matches = re.findall(command_pattern, content)

        # Filter to likely Redis commands
        redis_commands = []
        for match in set(matches):
            # Skip common non-command words
            if match in ["HTTP", "URL", "API", "JSON", "HTML", "TCP", "SSL", "TLS", "CPU", "RAM"]:
                continue

            # Check if it matches known Redis command patterns
            for category, patterns in self.command_patterns.items():
                for pattern in patterns:
                    if pattern in match or match.startswith(pattern):
                        redis_commands.append(match)
                        break

        return list(set(redis_commands))[:10]  # Limit to top 10

    async def enrich_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        """Enrich a single document with semantic metadata."""
        title = document.get("title", "")
        content = document.get("content", "")

        logger.debug(f"Enriching document: {title}")

        # Pattern-based classification (fast)
        classification = self.classify_by_patterns(title, content)

        # Semantic enhancement (slower, using LLM)
        semantic_info = await self.generate_semantic_description(title, content)

        # Extract related commands
        related_commands = await self.extract_related_commands(content)

        # Build enriched metadata
        enrichment = {
            "enriched_title": f"{title} - {semantic_info.get('description', '')}",
            "semantic_description": semantic_info.get("description", ""),
            "primary_use_case": semantic_info.get("use_case", ""),
            "when_to_use": semantic_info.get("when_to_use", ""),
            "primary_category": classification["primary_category"],
            "operational_scenarios": classification["operational_scenarios"],
            "is_redis_command": classification["is_command"],
            "related_commands": related_commands,
            "enrichment_version": "1.0",
        }

        # Merge with original document
        enriched_doc = {**document, **enrichment}

        logger.debug(f"Enriched {title} with category: {classification['primary_category']}")
        return enriched_doc

    async def enrich_batch(
        self, documents: List[Dict[str, Any]], batch_size: int = 5, delay: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Enrich a batch of documents with rate limiting."""
        enriched_docs = []

        for i in range(0, len(documents), batch_size):
            batch = documents[i : i + batch_size]

            logger.info(
                f"Enriching batch {i // batch_size + 1}/{(len(documents) + batch_size - 1) // batch_size}"
            )

            # Process batch concurrently
            tasks = [self.enrich_document(doc) for doc in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Handle results and exceptions
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    logger.error(f"Failed to enrich document {i + j}: {result}")
                    enriched_docs.append(batch[j])  # Keep original if enrichment fails
                else:
                    enriched_docs.append(result)

            # Rate limiting delay
            if i + batch_size < len(documents):
                await asyncio.sleep(delay)

        return enriched_docs


async def enrich_documents_from_batch(
    batch_date: str, openai_api_key: str, output_suffix: str = "_enriched"
) -> Dict[str, Any]:
    """
    Enrich all documents from a scraped batch.

    Args:
        batch_date: Date of the batch to enrich (e.g., "2025-08-21")
        openai_api_key: OpenAI API key for semantic enhancement
        output_suffix: Suffix to add to output files

    Returns:
        Enrichment statistics
    """
    enricher = DocumentEnricher(openai_api_key)

    # Set up paths
    artifacts_path = Path("artifacts") / batch_date
    if not artifacts_path.exists():
        raise ValueError(f"Batch directory not found: {artifacts_path}")

    stats = {
        "batch_date": batch_date,
        "documents_processed": 0,
        "documents_enriched": 0,
        "errors": [],
    }

    # Process each category
    for category in ["oss", "enterprise", "shared"]:
        category_path = artifacts_path / category
        if not category_path.exists():
            continue

        # Find all JSON documents
        json_files = list(category_path.glob("*.json"))
        logger.info(f"Found {len(json_files)} documents in {category}")

        # Load documents
        documents = []
        for json_file in json_files:
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                    documents.append((json_file, doc))
            except Exception as e:
                stats["errors"].append(f"Failed to load {json_file}: {e}")

        if not documents:
            continue

        # Enrich documents
        logger.info(f"Enriching {len(documents)} documents in {category}")

        doc_data = [doc for _, doc in documents]
        enriched_docs = await enricher.enrich_batch(doc_data)

        # Save enriched documents
        for (original_file, _), enriched_doc in zip(documents, enriched_docs):
            try:
                # Create new filename with suffix
                stem = original_file.stem
                new_filename = f"{stem}{output_suffix}.json"
                output_file = original_file.parent / new_filename

                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(enriched_doc, f, indent=2, ensure_ascii=False)

                stats["documents_enriched"] += 1

            except Exception as e:
                stats["errors"].append(f"Failed to save enriched {original_file}: {e}")

        stats["documents_processed"] += len(documents)

    logger.info(
        f"Enrichment completed: {stats['documents_enriched']}/{stats['documents_processed']} documents"
    )
    return stats
