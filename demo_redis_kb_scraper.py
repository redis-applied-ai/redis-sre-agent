#!/usr/bin/env python3
"""
Demo script for Redis KB scraper functionality.

This script demonstrates the complete Redis Knowledge Base scraping and indexing workflow.
"""

import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a command and display results."""
    print(f"\n{'='*60}")
    print(f"🔧 {description}")
    print(f"{'='*60}")
    print(f"Command: {cmd}")
    print()

    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("✅ Success!")
            if result.stdout:
                print("Output:")
                print(result.stdout)
        else:
            print("❌ Failed!")
            if result.stderr:
                print("Error:")
                print(result.stderr)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print("⏰ Command timed out")
        return False
    except Exception as e:
        print(f"❌ Exception: {e}")
        return False

def main():
    """Run the complete Redis KB scraper demo."""
    print("🚀 Redis Knowledge Base Scraper Demo")
    print("This demo shows the complete workflow for scraping and indexing Redis KB articles.")

    # Step 1: Scrape Redis KB articles
    success = run_command(
        "redis-sre-agent knowledge scrape --scrapers redis_kb",
        "Step 1: Scraping Redis KB Articles"
    )

    if not success:
        print("❌ Scraping failed. Exiting demo.")
        return

    # Step 2: Ingest scraped articles into knowledge base
    success = run_command(
        "redis-sre-agent knowledge ingest",
        "Step 2: Ingesting Articles into Knowledge Base"
    )

    if not success:
        print("❌ Ingestion failed. Exiting demo.")
        return

    # Step 3: Search without product label filtering
    run_command(
        'redis-sre-agent search "vector database" --limit 3',
        "Step 3: Search for 'vector database' (no filtering)"
    )

    # Step 4: Show scraped artifacts
    print(f"\n{'='*60}")
    print("📁 Step 4: Scraped Artifacts")
    print(f"{'='*60}")

    artifacts_path = Path("artifacts")
    if artifacts_path.exists():
        for batch_dir in artifacts_path.iterdir():
            if batch_dir.is_dir():
                print(f"Batch: {batch_dir.name}")
                for category_dir in batch_dir.iterdir():
                    if category_dir.is_dir() and category_dir.name in ["oss", "enterprise", "shared"]:
                        files = list(category_dir.glob("*.json"))
                        print(f"  {category_dir.name}: {len(files)} documents")
                        for file in files[:2]:  # Show first 2 files
                            print(f"    - {file.name}")

    # Step 5: Show product labels in scraped documents
    print(f"\n{'='*60}")
    print("🏷️  Step 5: Product Labels in Scraped Documents")
    print(f"{'='*60}")

    import json
    shared_dir = Path("artifacts/2025-09-19/shared")
    if shared_dir.exists():
        for json_file in shared_dir.glob("*.json"):
            with open(json_file) as f:
                doc = json.load(f)
            print(f"Document: {doc['title']}")
            print(f"  Product Labels: {doc['metadata'].get('product_labels', [])}")
            print(f"  Product Label Tags: {doc['metadata'].get('product_label_tags', [])}")
            print()
            break  # Show just one example

    # Step 6: API Examples (if server is running)
    print(f"\n{'='*60}")
    print("🌐 Step 6: API Usage Examples")
    print(f"{'='*60}")

    print("To test the API endpoints, start the server with:")
    print("  python -m redis_sre_agent.api.app")
    print()
    print("Then you can use these API calls:")
    print()
    print("1. Search with product label filtering:")
    print("   GET /api/v1/knowledge/search?query=vector%20database&product_labels=Redis%20Enterprise%20Software")
    print()
    print("2. Start scraping job:")
    print("   POST /api/v1/knowledge/ingest/pipeline")
    print("   Body: {\"scrapers\": [\"redis_kb\"], \"operation\": \"scrape\"}")
    print()
    print("3. Start full pipeline (scrape + ingest):")
    print("   POST /api/v1/knowledge/ingest/pipeline")
    print("   Body: {\"scrapers\": [\"redis_kb\"], \"operation\": \"full\"}")

    # Step 7: CLI Usage Summary
    print(f"\n{'='*60}")
    print("💻 Step 7: CLI Usage Summary")
    print(f"{'='*60}")

    print("Available CLI commands:")
    print()
    print("1. Scrape Redis KB articles:")
    print("   redis-sre-agent knowledge scrape --scrapers redis_kb")
    print()
    print("2. Ingest scraped articles:")
    print("   redis-sre-agent knowledge ingest")
    print()
    print("3. Full pipeline (scrape + ingest):")
    print("   redis-sre-agent knowledge update --scrapers redis_kb")
    print()
    print("4. Search knowledge base:")
    print("   redis-sre-agent search 'your query here'")
    print()
    print("5. Search with category filter:")
    print("   redis-sre-agent search 'your query' --category shared")

    print(f"\n{'='*60}")
    print("🎉 Demo Complete!")
    print(f"{'='*60}")
    print("The Redis KB scraper is now fully functional and integrated!")
    print()
    print("Key Features Implemented:")
    print("✅ Scrapes Redis Knowledge Base articles from https://redis.io/kb")
    print("✅ Extracts and preserves product labels (Redis Enterprise, Redis Cloud, etc.)")
    print("✅ Indexes documents with searchable product label tags")
    print("✅ Supports product label filtering in search")
    print("✅ Available through both CLI and API")
    print("✅ Integrates with existing knowledge base infrastructure")
    print()
    print("Product Labels Supported:")
    print("- Redis Enterprise Software")
    print("- Redis CE and Stack")
    print("- Redis Cloud")
    print("- Redis Enterprise")
    print("- Redis Insight")
    print("- Redis Enterprise for K8s")
    print("- Redis Data Integration")
    print("- Client Libraries")

if __name__ == "__main__":
    main()
