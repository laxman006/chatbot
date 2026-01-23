# -*- coding: utf-8 -*-
"""
Test script for Intelligent Query Routing System

Tests the LLM-based routing with different query types to verify:
1. Routing decisions make sense
2. Correct sources are prioritized
3. Budget allocation is reasonable
4. System handles edge cases
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, '.')

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Set environment to not initialize vectorstores (read-only test)
os.environ['INITIALIZE_VECTORSTORE'] = 'false'
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
os.environ['ENABLE_INTELLIGENT_ROUTING'] = 'true'

from intelligent_router import IntelligentQueryRouter, get_routing_confidence
from app.llm_factory import get_llm
from config import ROUTING_TOTAL_BUDGET
from datetime import datetime


# Test queries representing different scenarios
TEST_QUERIES = [
    {
        "query": "Migration shows pending status for 10 minutes, worker_status is null in database",
        "expected_type": "troubleshooting",
        "expected_primary": "jira",
        "description": "Copy-pasted error (no explicit keywords)"
    },
    {
        "query": "How to fix delta migration stuck error?",
        "expected_type": "troubleshooting",
        "expected_primary": "jira",
        "description": "Explicit troubleshooting query"
    },
    {
        "query": "What is CloudFuze?",
        "expected_type": "general_info",
        "expected_primary": "blog",
        "description": "General informational query"
    },
    {
        "query": "Do you have SOC 2 Type II certification?",
        "expected_type": "compliance",
        "expected_primary": "sharepoint",
        "description": "Compliance/security question"
    },
    {
        "query": "How much does the enterprise plan cost?",
        "expected_type": "pricing",
        "expected_primary": "excel",
        "description": "Pricing question"
    },
    {
        "query": "What features differentiate CloudFuze from competitors?",
        "expected_type": "sales",
        "expected_primary": "transcripts",
        "description": "Sales/competitive question"
    },
    {
        "query": "API documentation for delta migration endpoint",
        "expected_type": "technical",
        "expected_primary": "pdfs",
        "description": "Technical documentation request"
    },
    {
        "query": "java.lang.NullPointerException at com.cloudfuze.worker.MigrationWorker.process(MigrationWorker.java:245)",
        "expected_type": "troubleshooting",
        "expected_primary": "jira",
        "description": "Copy-pasted stack trace (no keywords)"
    }
]


def test_routing_decision(router: IntelligentQueryRouter, test_case: dict, test_num: int):
    """Test a single routing decision."""
    print("\n" + "="*80)
    print(f"TEST {test_num}: {test_case['description']}")
    print("="*80)
    print(f"Query: {test_case['query']}")
    print(f"Expected Type: {test_case['expected_type']}")
    print(f"Expected Primary Source: {test_case['expected_primary']}")
    print("-"*80)
    
    try:
        # Get routing decision
        routing_plan = router.route_query(test_case['query'])
        
        # Extract results
        actual_type = routing_plan.get('query_type', 'unknown')
        sources = routing_plan.get('sources', {})
        confidence = routing_plan.get('confidence', 0.0)
        
        # Find primary source (highest k value)
        primary_source = max(sources.items(), key=lambda x: x[1].get('k', 0))
        primary_name = primary_source[0]
        primary_k = primary_source[1].get('k', 0)
        
        # Calculate total allocation
        total_k = sum(src.get('k', 0) for src in sources.values())
        active_sources = [name for name, src in sources.items() if src.get('k', 0) > 0]
        
        # Validation
        type_match = actual_type == test_case['expected_type']
        primary_match = primary_name == test_case['expected_primary']
        budget_ok = total_k <= ROUTING_TOTAL_BUDGET
        
        # Results
        print("\n📊 ROUTING RESULTS:")
        print(f"  Query Type: {actual_type} {'✓' if type_match else '✗ Expected: ' + test_case['expected_type']}")
        print(f"  Primary Source: {primary_name} (k={primary_k}) {'✓' if primary_match else '✗ Expected: ' + test_case['expected_primary']}")
        print(f"  Total Budget: {total_k}/{ROUTING_TOTAL_BUDGET} {'✓' if budget_ok else '✗ OVER BUDGET'}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Active Sources: {len(active_sources)} - {', '.join(active_sources)}")
        
        # Overall result
        all_pass = type_match and primary_match and budget_ok
        
        if all_pass:
            print("\n✅ TEST PASSED")
        else:
            print("\n⚠️ TEST PARTIAL - Check reasoning above")
        
        return {
            "passed": all_pass,
            "type_match": type_match,
            "primary_match": primary_match,
            "budget_ok": budget_ok,
            "confidence": confidence,
            "total_k": total_k
        }
        
    except Exception as e:
        print(f"\n❌ TEST FAILED - Error: {e}")
        import traceback
        traceback.print_exc()
        return {
            "passed": False,
            "error": str(e)
        }


def main():
    """Run all routing tests."""
    print("="*80)
    print("INTELLIGENT QUERY ROUTING - TEST SUITE")
    print("="*80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Total Budget: {ROUTING_TOTAL_BUDGET} documents")
    print(f"Test Queries: {len(TEST_QUERIES)}")
    print("="*80)
    
    # Initialize router
    print("\n[*] Initializing LLM and Router...")
    try:
        llm = get_llm()
        router = IntelligentQueryRouter(llm, total_budget=ROUTING_TOTAL_BUDGET)
        print("[OK] Router initialized successfully")
    except Exception as e:
        print(f"[ERROR] Failed to initialize router: {e}")
        return
    
    # Run tests
    results = []
    for i, test_case in enumerate(TEST_QUERIES, 1):
        result = test_routing_decision(router, test_case, i)
        results.append(result)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for r in results if r.get('passed', False))
    total = len(results)
    
    print(f"\nTotal Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {passed/total*100:.1f}%")
    
    # Detailed breakdown
    print("\nDetailed Breakdown:")
    type_matches = sum(1 for r in results if r.get('type_match', False))
    primary_matches = sum(1 for r in results if r.get('primary_match', False))
    budget_oks = sum(1 for r in results if r.get('budget_ok', False))
    
    print(f"  Type Classification: {type_matches}/{total} ({type_matches/total*100:.1f}%)")
    print(f"  Primary Source: {primary_matches}/{total} ({primary_matches/total*100:.1f}%)")
    print(f"  Budget Compliance: {budget_oks}/{total} ({budget_oks/total*100:.1f}%)")
    
    # Average confidence
    confidences = [r.get('confidence', 0) for r in results if 'confidence' in r]
    if confidences:
        avg_confidence = sum(confidences) / len(confidences)
        print(f"  Average Confidence: {avg_confidence:.2f}")
    
    # Conclusion
    print("\n" + "="*80)
    if passed == total:
        print("🎉 ALL TESTS PASSED!")
        print("Intelligent routing is working correctly.")
    elif passed >= total * 0.7:
        print("✅ MOST TESTS PASSED")
        print(f"System is functional but may need refinement ({passed}/{total} passed)")
    else:
        print("⚠️ MULTIPLE TESTS FAILED")
        print("Review routing logic and LLM prompts")
    print("="*80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test suite failed: {e}")
        import traceback
        traceback.print_exc()
