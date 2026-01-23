"""
Simple test to verify deduplication logic without loading vectorstores.

Tests the core fix: Jira deduplication using ticket_key.
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from langchain_core.documents import Document
from multi_source_retrieval import deduplicate_by_content


def test_jira_deduplication():
    """Test that Jira deduplication uses ticket_key instead of content."""
    print("\n" + "="*80)
    print("TEST 1: Jira Deduplication (using ticket_key)")
    print("="*80)
    
    # Create mock Jira documents with VERY similar content but different ticket_keys
    jira_docs = [
        (Document(
            page_content="## Root Cause\nDatabase connection timeout due to configuration issues in production environment.",
            metadata={"ticket_key": "CF-123", "section": "root_cause"}
        ), 0.5),
        (Document(
            page_content="## Root Cause\nDatabase connection timeout due to network latency in production environment.",
            metadata={"ticket_key": "CF-124", "section": "root_cause"}
        ), 0.6),
        (Document(
            page_content="## Root Cause\nDatabase connection timeout due to configuration issues in production environment.",
            metadata={"ticket_key": "CF-125", "section": "root_cause"}
        ), 0.55),
        (Document(
            page_content="## Description\nThis ticket describes database issues.",
            metadata={"ticket_key": "CF-123", "section": "description"}
        ), 0.4),  # Same ticket as first one, should be removed
        (Document(
            page_content="## Root Cause\nDatabase connection refused by server.",
            metadata={"ticket_key": "CF-126", "section": "root_cause"}
        ), 0.7),
    ]
    
    print(f"\nInput: {len(jira_docs)} documents (chunks)")
    print("  • CF-123 (root_cause): 'Database connection timeout due to configuration...'")
    print("  • CF-124 (root_cause): 'Database connection timeout due to network...'")
    print("  • CF-125 (root_cause): 'Database connection timeout due to configuration...' [SAME CONTENT AS CF-123]")
    print("  • CF-123 (description): 'This ticket describes database issues.' [SAME TICKET AS #1]")
    print("  • CF-126 (root_cause): 'Database connection refused by server.'")
    
    print("\nWithout ticket_key deduplication:")
    print("  Old behavior would remove CF-125 (same content as CF-123)")
    print("  New behavior should keep CF-125 (different ticket_key)")
    
    # Deduplicate
    print("\nRunning deduplication...")
    deduplicated = deduplicate_by_content(jira_docs)
    
    print(f"\nOutput: {len(deduplicated)} unique documents")
    
    # Verify results
    unique_keys = {}
    for doc, score in deduplicated:
        key = doc.metadata.get("ticket_key")
        section = doc.metadata.get("section")
        if key not in unique_keys:
            unique_keys[key] = []
        unique_keys[key].append((section, score))
    
    print("\nUnique tickets after deduplication:")
    for ticket_key in sorted(unique_keys.keys()):
        sections = unique_keys[ticket_key]
        print(f"  • {ticket_key}: {len(sections)} chunk(s) - {', '.join(s[0] for s in sections)}")
    
    # Assertions
    assert len(deduplicated) == 4, f"[FAIL] Expected 4 unique documents, got {len(deduplicated)}"
    assert len(unique_keys) == 4, f"[FAIL] Expected 4 unique tickets, got {len(unique_keys)}"
    assert "CF-123" in unique_keys, "[FAIL] CF-123 should be present"
    assert "CF-124" in unique_keys, "[FAIL] CF-124 should be present"
    assert "CF-125" in unique_keys, "[FAIL] CF-125 should be present (different ticket despite similar content)"
    assert "CF-126" in unique_keys, "[FAIL] CF-126 should be present"
    assert len(unique_keys["CF-123"]) == 1, f"[FAIL] CF-123 should have only 1 chunk (duplicate removed), got {len(unique_keys['CF-123'])}"
    
    print("\n[PASS] TEST PASSED!")
    print("  * Each unique ticket is preserved (CF-123, CF-124, CF-125, CF-126)")
    print("  * CF-125 is kept despite having similar content to CF-123")
    print("  * Duplicate chunk from CF-123 was correctly removed")
    

def test_content_deduplication():
    """Test that non-Jira documents still use content-based deduplication."""
    print("\n" + "="*80)
    print("TEST 2: Content-Based Deduplication (for non-Jira documents)")
    print("="*80)
    
    # Create mock documents with similar content (no ticket_key)
    content_docs = [
        (Document(
            page_content="CloudFuze is a cloud migration platform that helps enterprises migrate data between cloud storage systems seamlessly.",
            metadata={"source_type": "web", "tag": "blog", "post_title": "What is CloudFuze"}
        ), 0.3),
        (Document(
            page_content="CloudFuze is a cloud migration platform that helps enterprises migrate data between cloud storage systems seamlessly.",
            metadata={"source_type": "web", "tag": "blog", "post_title": "CloudFuze Overview"}
        ), 0.4),  # DUPLICATE content - should be removed
        (Document(
            page_content="SharePoint to Google Drive migration is easy with CloudFuze. Simply connect your accounts and start migrating.",
            metadata={"source_type": "sharepoint", "tag": "sharepoint/docs"}
        ), 0.5),
        (Document(
            page_content="Office 365 to AWS S3 migration guide. Follow these steps for a successful migration using CloudFuze platform.",
            metadata={"source_type": "web", "tag": "blog", "post_title": "Migration Guide"}
        ), 0.35),
    ]
    
    print(f"\nInput: {len(content_docs)} documents")
    print("  • Blog: 'CloudFuze is a cloud migration platform...' (score=0.3)")
    print("  • Blog: 'CloudFuze is a cloud migration platform...' (score=0.4) [DUPLICATE CONTENT]")
    print("  • SharePoint: 'SharePoint to Google Drive migration...' (score=0.5)")
    print("  • Blog: 'Office 365 to AWS S3 migration guide...' (score=0.35)")
    
    # Deduplicate
    print("\nRunning deduplication...")
    deduplicated = deduplicate_by_content(content_docs)
    
    print(f"\nOutput: {len(deduplicated)} unique documents")
    print("Expected: 3 documents (duplicate blog post removed, better score 0.3 kept)")
    
    sources = {}
    for doc, score in deduplicated:
        source = doc.metadata.get("tag", "unknown")
        if source not in sources:
            sources[source] = []
        sources[source].append(score)
    
    print("\nDocuments by source:")
    for source, scores in sorted(sources.items()):
        print(f"  • {source}: {len(scores)} document(s), scores={scores}")
    
    # Assertions
    assert len(deduplicated) == 3, f"[FAIL] Expected 3 unique documents, got {len(deduplicated)}"
    
    # Check that the better score (0.3) was kept for the duplicate
    blog_docs = [doc for doc, score in deduplicated if doc.metadata.get("tag") == "blog"]
    assert len(blog_docs) == 2, f"[FAIL] Expected 2 unique blog documents, got {len(blog_docs)}"
    
    blog_scores = [score for doc, score in deduplicated if doc.metadata.get("tag") == "blog"]
    assert 0.3 in blog_scores, "[FAIL] Should keep the better score (0.3)"
    assert 0.4 not in blog_scores, "[FAIL] Should remove the worse score (0.4)"
    
    print("\n[PASS] TEST PASSED!")
    print("  * Content-based deduplication works for non-Jira documents")
    print("  * Better score (0.3) was kept, worse score (0.4) was removed")
    print("  * Different content is preserved")


def test_mixed_documents():
    """Test deduplication with a mix of Jira and non-Jira documents."""
    print("\n" + "="*80)
    print("TEST 3: Mixed Jira and Non-Jira Documents")
    print("="*80)
    
    mixed_docs = [
        # Jira tickets
        (Document(
            page_content="## Root Cause\nIssue description here",
            metadata={"ticket_key": "CF-100", "section": "root_cause"}
        ), 0.2),
        (Document(
            page_content="## Root Cause\nIssue description here",
            metadata={"ticket_key": "CF-101", "section": "root_cause"}
        ), 0.25),  # Same content, different ticket - should be KEPT
        
        # Blog posts
        (Document(
            page_content="Migration best practices include planning ahead and testing thoroughly before production deployment.",
            metadata={"source_type": "web", "tag": "blog"}
        ), 0.3),
        (Document(
            page_content="Migration best practices include planning ahead and testing thoroughly before production deployment.",
            metadata={"source_type": "web", "tag": "blog"}
        ), 0.35),  # Duplicate content - should be REMOVED
        
        # SharePoint
        (Document(
            page_content="Internal documentation for migration procedures.",
            metadata={"source_type": "sharepoint", "tag": "sharepoint"}
        ), 0.4),
    ]
    
    print(f"\nInput: {len(mixed_docs)} documents")
    print("  • CF-100 (Jira): '## Root Cause\\nIssue description here'")
    print("  • CF-101 (Jira): '## Root Cause\\nIssue description here' [SAME CONTENT, DIFFERENT TICKET]")
    print("  • Blog: 'Migration best practices...'")
    print("  • Blog: 'Migration best practices...' [DUPLICATE CONTENT]")
    print("  • SharePoint: 'Internal documentation...'")
    
    # Deduplicate
    print("\nRunning deduplication...")
    deduplicated = deduplicate_by_content(mixed_docs)
    
    print(f"\nOutput: {len(deduplicated)} unique documents")
    print("Expected: 4 documents (1 blog duplicate removed, both Jira tickets kept)")
    
    # Count by type
    jira_count = sum(1 for doc, _ in deduplicated if doc.metadata.get("ticket_key"))
    blog_count = sum(1 for doc, _ in deduplicated if doc.metadata.get("tag") == "blog")
    sp_count = sum(1 for doc, _ in deduplicated if doc.metadata.get("tag") == "sharepoint")
    
    print(f"\nBreakdown:")
    print(f"  • Jira tickets: {jira_count}")
    print(f"  • Blog posts: {blog_count}")
    print(f"  • SharePoint: {sp_count}")
    
    # Assertions
    assert len(deduplicated) == 4, f"[FAIL] Expected 4 documents, got {len(deduplicated)}"
    assert jira_count == 2, f"[FAIL] Expected 2 Jira tickets, got {jira_count}"
    assert blog_count == 1, f"[FAIL] Expected 1 blog post, got {blog_count}"
    assert sp_count == 1, f"[FAIL] Expected 1 SharePoint doc, got {sp_count}"
    
    print("\n[PASS] TEST PASSED!")
    print("  * Both Jira tickets kept (different ticket_keys)")
    print("  * Blog duplicate removed (same content)")
    print("  * SharePoint doc preserved")


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DEDUPLICATION LOGIC TESTS")
    print("="*80)
    print("\nTesting the core fix: Jira deduplication using ticket_key")
    print("This test does NOT require loading vectorstores.")
    
    try:
        test_jira_deduplication()
        test_content_deduplication()
        test_mixed_documents()
        
        print("\n" + "="*80)
        print("ALL TESTS PASSED!")
        print("="*80)
        print("\nSummary:")
        print("  [OK] Jira deduplication correctly uses ticket_key")
        print("  [OK] Content deduplication works for non-Jira documents")
        print("  [OK] Mixed document types are handled correctly")
        print("\nThe fix is working as expected!")
        
    except AssertionError as e:
        print(f"\n[FAIL] TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
