#!/usr/bin/env python3
"""
Comprehensive test suite for document fragment retrieval functionality.

This test suite validates the new fragment retrieval features:
- get_all_document_fragments()
- get_related_document_fragments()
- Enhanced search results with document_hash and chunk_index
"""

import asyncio

import pytest

from redis_sre_agent.tools.sre_functions import (
    get_all_document_fragments,
    get_related_document_fragments,
    search_knowledge_base,
)


class TestFragmentRetrieval:
    """Test suite for document fragment retrieval functionality."""

    @pytest.fixture
    async def sample_search_results(self):
        """Get sample search results for testing."""
        return await search_knowledge_base("vector database", limit=3)

    @pytest.fixture
    async def sample_document_hash(self, sample_search_results):
        """Extract a document hash from search results."""
        if sample_search_results and "results" in sample_search_results:
            results = sample_search_results["results"]
            if results and results[0].get("document_hash"):
                return results[0]["document_hash"]
        pytest.skip("No document hash available in search results")

    async def test_search_includes_fragment_metadata(self):
        """Test that search results include document_hash and chunk_index."""
        results = await search_knowledge_base("Redis Enterprise", limit=2)

        assert results is not None
        assert "results" in results
        assert len(results["results"]) > 0

        for result in results["results"]:
            # Check that fragment metadata is included
            assert "document_hash" in result, "Search results should include document_hash"
            assert "chunk_index" in result, "Search results should include chunk_index"

            # Validate data types
            assert isinstance(result["document_hash"], str), "document_hash should be string"
            assert isinstance(result["chunk_index"], (int, str)), (
                "chunk_index should be int or string"
            )

    async def test_get_all_document_fragments_success(self, sample_document_hash):
        """Test successful retrieval of all document fragments."""
        result = await get_all_document_fragments(sample_document_hash)

        # Check basic structure
        assert "error" not in result, f"Should not have error: {result.get('error')}"
        assert "fragments_count" in result
        assert "fragments" in result
        assert "full_content" in result
        assert "title" in result
        assert "source" in result

        # Validate fragments
        fragments = result["fragments"]
        assert len(fragments) > 0, "Should have at least one fragment"
        assert len(fragments) == result["fragments_count"], "Fragment count should match"

        # Check fragment structure
        for i, fragment in enumerate(fragments):
            assert "title" in fragment, f"Fragment {i} should have title"
            assert "content" in fragment, f"Fragment {i} should have content"
            assert "chunk_index" in fragment, f"Fragment {i} should have chunk_index"
            assert "document_hash" in fragment, f"Fragment {i} should have document_hash"
            assert fragment["document_hash"] == sample_document_hash

        # Validate full content reconstruction
        assert len(result["full_content"]) > 0, "Full content should not be empty"

        # Check that fragments are ordered by chunk_index
        chunk_indices = [int(f.get("chunk_index", 0)) for f in fragments]
        assert chunk_indices == sorted(chunk_indices), "Fragments should be ordered by chunk_index"

    async def test_get_all_document_fragments_invalid_hash(self):
        """Test behavior with invalid document hash."""
        result = await get_all_document_fragments("invalid_hash_12345")

        assert "error" in result or result["fragments_count"] == 0
        assert result["fragments"] == []

    async def test_get_related_document_fragments_success(self, sample_document_hash):
        """Test successful retrieval of related document fragments."""
        # First get all fragments to know the structure
        all_fragments = await get_all_document_fragments(sample_document_hash)

        if all_fragments["fragments_count"] < 2:
            pytest.skip("Need at least 2 fragments for context testing")

        # Test with middle chunk
        target_chunk = 1 if all_fragments["fragments_count"] > 2 else 0
        context_window = 1

        result = await get_related_document_fragments(
            sample_document_hash, current_chunk_index=target_chunk, context_window=context_window
        )

        # Check basic structure
        assert "error" not in result, f"Should not have error: {result.get('error')}"
        assert "related_fragments_count" in result
        assert "related_fragments" in result
        assert "target_chunk_index" in result
        assert "context_window" in result

        # Validate related fragments
        related_fragments = result["related_fragments"]
        assert len(related_fragments) > 0, "Should have at least one related fragment"
        assert len(related_fragments) == result["related_fragments_count"]

        # Check that target chunk is marked
        target_found = False
        for fragment in related_fragments:
            assert "is_target_chunk" in fragment
            if fragment["is_target_chunk"]:
                target_found = True
                assert int(fragment["chunk_index"]) == target_chunk

        assert target_found, "Target chunk should be marked in results"

    async def test_get_related_fragments_edge_cases(self, sample_document_hash):
        """Test edge cases for related fragment retrieval."""
        # Test with chunk_index 0 (beginning)
        result = await get_related_document_fragments(
            sample_document_hash, current_chunk_index=0, context_window=2
        )
        assert "error" not in result

        # Test with large context window
        result = await get_related_document_fragments(
            sample_document_hash, current_chunk_index=0, context_window=100
        )
        assert "error" not in result

        # Test with string chunk_index (type conversion)
        result = await get_related_document_fragments(
            sample_document_hash, current_chunk_index="0", context_window=1
        )
        assert "error" not in result

    async def test_fragment_content_consistency(self, sample_document_hash):
        """Test that fragment content is consistent between different retrieval methods."""
        # Get all fragments
        all_fragments_result = await get_all_document_fragments(sample_document_hash)

        if all_fragments_result["fragments_count"] == 0:
            pytest.skip("No fragments available for consistency testing")

        # Get related fragments for each chunk
        for fragment in all_fragments_result["fragments"]:
            chunk_index = int(fragment["chunk_index"])

            related_result = await get_related_document_fragments(
                sample_document_hash,
                current_chunk_index=chunk_index,
                context_window=0,  # Just the target chunk
            )

            # Find the target chunk in related results
            target_fragment = None
            for rel_frag in related_result["related_fragments"]:
                if rel_frag.get("is_target_chunk"):
                    target_fragment = rel_frag
                    break

            assert target_fragment is not None, f"Target chunk {chunk_index} not found"

            # Compare content
            assert fragment["content"] == target_fragment["content"], (
                f"Content mismatch for chunk {chunk_index}"
            )
            assert fragment["title"] == target_fragment["title"], (
                f"Title mismatch for chunk {chunk_index}"
            )


async def run_comprehensive_tests():
    """Run comprehensive tests and report results."""
    print("🧪 Running Comprehensive Fragment Retrieval Tests")
    print("=" * 60)

    # Get sample data
    print("📋 Setting up test data...")
    sample_results = await search_knowledge_base("vector database", limit=3)

    if not sample_results or "results" not in sample_results or not sample_results["results"]:
        print("❌ No search results available - cannot run tests")
        return

    sample_hash = sample_results["results"][0].get("document_hash")
    if not sample_hash:
        print("❌ No document hash available - cannot run tests")
        return

    print(f"✅ Using document hash: {sample_hash}")
    print()

    # Define test functions
    async def test_search_metadata():
        """Test that search results include document_hash and chunk_index."""
        results = await search_knowledge_base("Redis Enterprise", limit=2)

        assert results is not None
        assert "results" in results
        assert len(results["results"]) > 0

        for result in results["results"]:
            assert "document_hash" in result, "Search results should include document_hash"
            assert "chunk_index" in result, "Search results should include chunk_index"
            assert isinstance(result["document_hash"], str), "document_hash should be string"
            assert isinstance(result["chunk_index"], (int, str)), (
                "chunk_index should be int or string"
            )

    async def test_all_fragments():
        """Test successful retrieval of all document fragments."""
        result = await get_all_document_fragments(sample_hash)

        assert "error" not in result, f"Should not have error: {result.get('error')}"
        assert "fragments_count" in result
        assert "fragments" in result
        assert "full_content" in result

        fragments = result["fragments"]
        assert len(fragments) > 0, "Should have at least one fragment"
        assert len(fragments) == result["fragments_count"], "Fragment count should match"

        for i, fragment in enumerate(fragments):
            assert "title" in fragment, f"Fragment {i} should have title"
            assert "content" in fragment, f"Fragment {i} should have content"
            assert "chunk_index" in fragment, f"Fragment {i} should have chunk_index"
            assert fragment["document_hash"] == sample_hash

        assert len(result["full_content"]) > 0, "Full content should not be empty"

    async def test_invalid_hash():
        """Test behavior with invalid document hash."""
        result = await get_all_document_fragments("invalid_hash_12345")
        assert "error" in result or result["fragments_count"] == 0
        assert result["fragments"] == []

    async def test_related_fragments():
        """Test successful retrieval of related document fragments."""
        all_fragments = await get_all_document_fragments(sample_hash)

        if all_fragments["fragments_count"] < 1:
            return  # Skip if no fragments

        target_chunk = 0
        result = await get_related_document_fragments(
            sample_hash, current_chunk_index=target_chunk, context_window=1
        )

        assert "error" not in result, f"Should not have error: {result.get('error')}"
        assert "related_fragments_count" in result
        assert "related_fragments" in result

        related_fragments = result["related_fragments"]
        assert len(related_fragments) > 0, "Should have at least one related fragment"

        target_found = False
        for fragment in related_fragments:
            assert "is_target_chunk" in fragment
            if fragment["is_target_chunk"]:
                target_found = True
                assert int(fragment["chunk_index"]) == target_chunk

        assert target_found, "Target chunk should be marked in results"

    # Run tests
    tests = [
        ("Search includes fragment metadata", test_search_metadata),
        ("Get all document fragments", test_all_fragments),
        ("Invalid document hash handling", test_invalid_hash),
        ("Get related fragments", test_related_fragments),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            print(f"🔍 Testing: {test_name}")
            await test_func()
            print(f"✅ PASSED: {test_name}")
            passed += 1
        except Exception as e:
            print(f"❌ FAILED: {test_name}")
            print(f"   Error: {str(e)}")
            failed += 1
        print()

    print("📊 Test Results Summary")
    print("-" * 30)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {passed / (passed + failed) * 100:.1f}%")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_tests())
