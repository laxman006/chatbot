"""
Test the improved intelligent routing system.
Tests with queries that previously returned 0 results.
"""
from intelligent_router import IntelligentQueryRouter
from langchain_openai import ChatOpenAI
import json

# Test queries - especially those that returned 0 results before
TEST_QUERIES = [
    {
        "query": "if during an ongoing migration the csv needs to be changed should we change from UI or from backend",
        "expected_type": "migration_procedure",
        "expected_sources": ["blog", "jira"],
        "note": "Previously returned 0 results - classified as general_info"
    },
    {
        "query": "Why are messages posted in channels not migrating during the migration process?",
        "expected_type": "troubleshooting",
        "expected_sources": ["jira", "blog"],
        "note": "Previously returned 0 results"
    },
    {
        "query": "how to configure Teams migration settings",
        "expected_type": "configuration",
        "expected_sources": ["blog", "pdfs"],
        "note": "New configuration type test"
    },
    {
        "query": "best practices for large file migrations",
        "expected_type": "best_practices",
        "expected_sources": ["blog", "transcripts"],
        "note": "New best_practices type test"
    },
    {
        "query": "what is CloudFuze Migrate",
        "expected_type": "general_info",
        "expected_sources": ["blog", "pdfs"],
        "note": "General info should still work"
    },
    {
        "query": "SOC 2 Type 2 certification",
        "expected_type": "compliance",
        "expected_sources": ["sharepoint"],
        "note": "Compliance should prioritize SharePoint"
    },
    {
        "query": "migration failed with error 500",
        "expected_type": "troubleshooting",
        "expected_sources": ["jira", "blog"],
        "note": "Error troubleshooting"
    },
    {
        "query": "how to modify user mappings during active migration",
        "expected_type": "migration_procedure",
        "expected_sources": ["blog", "jira"],
        "note": "Another migration procedure test"
    }
]


def test_routing():
    """Test the improved routing system."""
    print("=" * 80)
    print(" TESTING IMPROVED INTELLIGENT ROUTING")
    print("=" * 80)
    
    # Initialize router
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    router = IntelligentQueryRouter(llm)
    
    results = []
    
    for idx, test_case in enumerate(TEST_QUERIES, 1):
        query = test_case["query"]
        expected_type = test_case["expected_type"]
        expected_sources = set(test_case["expected_sources"])
        note = test_case.get("note", "")
        
        print(f"\n{'=' * 80}")
        print(f"TEST {idx}/{len(TEST_QUERIES)}: {query}")
        print(f"Expected type: {expected_type}")
        print(f"Expected sources: {', '.join(expected_sources)}")
        if note:
            print(f"Note: {note}")
        print("-" * 80)
        
        try:
            # Get routing decision
            routing_plan = router.route_query(query)
            
            # Analyze results
            actual_type = routing_plan.get("query_type", "unknown")
            confidence = routing_plan.get("confidence", 0)
            sources = routing_plan.get("sources", {})
            
            # Get sources with k > 0
            active_sources = {name: info for name, info in sources.items() if info.get("k", 0) > 0}
            total_k = sum(info.get("k", 0) for info in active_sources.values())
            
            # Check results
            type_match = actual_type == expected_type
            sources_match = set(active_sources.keys()) & expected_sources
            has_results = total_k > 0
            
            # Print results
            print(f"\n[RESULT]")
            if type_match:
                print(f"  Actual type: {actual_type} [OK]")
            else:
                print(f"  Actual type: {actual_type} [MISMATCH] (expected: {expected_type})")
            print(f"  Confidence: {confidence:.2f}")
            print(f"  Total documents: {total_k}")
            print(f"  Active sources: {', '.join(active_sources.keys())}")
            
            if sources_match:
                print(f"  Matched expected sources: {', '.join(sources_match)} [OK]")
            
            missing = expected_sources - set(active_sources.keys())
            if missing:
                print(f"  Missing expected sources: {', '.join(missing)} [WARN]")
            
            # Detailed source breakdown
            print(f"\n  Source allocation:")
            for name, info in sorted(active_sources.items(), key=lambda x: x[1].get("k", 0), reverse=True):
                k = info.get("k", 0)
                relevance = info.get("relevance", 0)
                reasoning = info.get("reasoning", "")
                print(f"    - {name:12} k={k:2d}  relevance={relevance:.2f}")
                print(f"      Reasoning: {reasoning}")
            
            # Overall assessment
            if not has_results:
                print(f"\n  [FAIL] NO DOCUMENTS ALLOCATED - This query would return 0 results!")
            elif type_match and sources_match == expected_sources:
                print(f"\n  [PASS] Perfect match - type and all expected sources present")
            elif type_match or sources_match:
                print(f"\n  [PARTIAL] Partial match - some aspects correct")
            else:
                print(f"\n  [WARN] Different from expected but may still work")
            
            results.append({
                "query": query,
                "expected_type": expected_type,
                "actual_type": actual_type,
                "type_match": type_match,
                "expected_sources": list(expected_sources),
                "actual_sources": list(active_sources.keys()),
                "sources_match": list(sources_match),
                "total_k": total_k,
                "confidence": confidence,
                "has_results": has_results,
                "note": note
            })
            
        except Exception as e:
            print(f"\n[ERROR] {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "query": query,
                "error": str(e),
                "has_results": False
            })
    
    # Summary
    print("\n" + "=" * 80)
    print(" SUMMARY")
    print("=" * 80)
    
    total_tests = len(results)
    with_results = sum(1 for r in results if r.get("has_results", False))
    type_matches = sum(1 for r in results if r.get("type_match", False))
    perfect_matches = sum(1 for r in results if r.get("type_match", False) and 
                         set(r.get("sources_match", [])) == set(r.get("expected_sources", [])))
    
    print(f"\nTotal tests: {total_tests}")
    print(f"Tests with results (k > 0): {with_results}/{total_tests} ({with_results/total_tests*100:.1f}%)")
    print(f"Type matches: {type_matches}/{total_tests} ({type_matches/total_tests*100:.1f}%)")
    print(f"Perfect matches: {perfect_matches}/{total_tests} ({perfect_matches/total_tests*100:.1f}%)")
    
    if with_results < total_tests:
        print(f"\n[WARNING] {total_tests - with_results} queries would still return 0 results:")
        for r in results:
            if not r.get("has_results", False):
                print(f"  - {r['query'][:60]}...")
    
    # Previously failing queries
    print(f"\n[IMPROVEMENT CHECK]")
    prev_failing = [r for r in results if "Previously returned 0 results" in r.get("note", "")]
    if prev_failing:
        now_working = sum(1 for r in prev_failing if r.get("has_results", False))
        print(f"Previously failing queries: {len(prev_failing)}")
        print(f"Now working: {now_working}/{len(prev_failing)}")
        
        if now_working == len(prev_failing):
            print("[SUCCESS] All previously failing queries now return results!")
        else:
            print("[PARTIAL] Some queries still failing:")
            for r in prev_failing:
                if not r.get("has_results", False):
                    print(f"  - {r['query'][:60]}...")
    
    # Export results
    with open("routing_test_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Test results exported to: routing_test_results.json")
    
    return results


if __name__ == "__main__":
    test_routing()
