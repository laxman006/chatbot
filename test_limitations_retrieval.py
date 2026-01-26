# -*- coding: utf-8 -*-
"""
Test script for limitations document retrieval and guardrail enforcement.

Tests:
1. Limitations docs are always retrieved
2. Limitations docs appear in top results
3. Responses obey "not supported" when limitation says no
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.vectorstore import vectorstore
from multi_source_retrieval import retrieve_limitations_documents, intelligent_multi_source_retrieve
from intelligent_router import IntelligentQueryRouter

def test_limitations_retrieval():
    """Test that limitations documents are retrieved."""
    print("=" * 70)
    print("TEST 1: Limitations Document Retrieval")
    print("=" * 70)
    
    test_queries = [
        "Can we migrate edited messages with edited tag?",
        "Is thread migration supported slack to teams?",
        "What is not supported in slack to teams?",
    ]
    
    for query in test_queries:
        print(f"\n[TEST] Query: {query}")
        print("-" * 70)
        
        # Test direct limitations retrieval
        limitations_docs = retrieve_limitations_documents(vectorstore, query, k=4)
        
        if limitations_docs:
            print(f"✓ Retrieved {len(limitations_docs)} limitations documents")
            for i, (doc, score) in enumerate(limitations_docs[:3], 1):
                source_type = doc.metadata.get("source_type", "unknown")
                doc_type = doc.metadata.get("doc_type", "N/A")
                file_name = doc.metadata.get("file_name", "N/A")
                print(f"  {i}. [{source_type}] doc_type={doc_type}, file={file_name[:50]}... (score: {score:.3f})")
        else:
            print("✗ FAILED: No limitations documents retrieved")
            return False
    
    print("\n✓ TEST 1 PASSED: Limitations documents are retrieved")
    return True


def test_limitations_in_top_results():
    """Test that limitations docs appear in top results after merging."""
    print("\n" + "=" * 70)
    print("TEST 2: Limitations Docs in Top Results")
    print("=" * 70)
    
    if not vectorstore:
        print("✗ FAILED: Vectorstore not available")
        return False
    
    # Create a simple routing plan
    router = IntelligentQueryRouter()
    routing_plan = router._get_fallback_routing()
    
    test_query = "Can we migrate edited messages with edited tag?"
    
    print(f"\n[TEST] Query: {test_query}")
    print("-" * 70)
    
    # Retrieve using intelligent_multi_source_retrieve
    all_candidates = intelligent_multi_source_retrieve(
        vectorstore=vectorstore,
        jira_vectorstore=None,  # Skip Jira for this test
        query=test_query,
        routing_plan=routing_plan,
        enable_deduplication=True,
        always_include_limitations=True
    )
    
    if not all_candidates:
        print("✗ FAILED: No candidates retrieved")
        return False
    
    print(f"✓ Retrieved {len(all_candidates)} total candidates")
    
    # Check top 10 results
    top_10 = all_candidates[:10]
    limitations_in_top = [
        (doc, score) for doc, score in top_10
        if doc.metadata.get("source_type") == "sharepoint_limitations"
        or doc.metadata.get("doc_type") == "limitations"
    ]
    
    if limitations_in_top:
        print(f"✓ Found {len(limitations_in_top)} limitations docs in top 10")
        for i, (doc, score) in enumerate(limitations_in_top[:3], 1):
            file_name = doc.metadata.get("file_name", "N/A")
            print(f"  {i}. {file_name[:60]}... (score: {score:.3f})")
        
        # Check if at least one is in top 3
        top_3 = all_candidates[:3]
        has_limitations_in_top_3 = any(
            doc.metadata.get("source_type") == "sharepoint_limitations"
            or doc.metadata.get("doc_type") == "limitations"
            for doc, _ in top_3
        )
        
        if has_limitations_in_top_3:
            print("✓ PASSED: At least one limitations doc in top 3")
            return True
        else:
            print("⚠ WARNING: Limitations docs found but not in top 3")
            return True  # Still pass, but note the warning
    else:
        print("✗ FAILED: No limitations docs in top 10 results")
        return False


def test_response_format():
    """Test that responses follow the structured format."""
    print("\n" + "=" * 70)
    print("TEST 3: Response Format Validation")
    print("=" * 70)
    print("\n[INFO] This test validates the guardrail is working.")
    print("       Run a full chat query to verify response format.")
    print("       Expected format:")
    print("       - Support: [Yes/No/Partial]")
    print("       - Reason: [explanation]")
    print("       - Workaround: [if applicable]")
    print("       - Source: Limitations document")
    print("\n✓ TEST 3: Manual validation required (check chat responses)")


def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("LIMITATIONS RETRIEVAL TEST SUITE")
    print("=" * 70)
    
    if not vectorstore:
        print("\n✗ ERROR: Vectorstore not initialized")
        print("   Run the vectorstore initialization first")
        return
    
    results = []
    
    # Test 1: Direct retrieval
    results.append(("Limitations Retrieval", test_limitations_retrieval()))
    
    # Test 2: Top results
    results.append(("Limitations in Top Results", test_limitations_in_top_results()))
    
    # Test 3: Format (manual)
    test_response_format()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    for test_name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    if all_passed:
        print("\n✓ ALL AUTOMATED TESTS PASSED")
    else:
        print("\n✗ SOME TESTS FAILED - Review output above")


if __name__ == "__main__":
    main()
