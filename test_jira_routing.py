"""
Test script to verify improved Jira routing with pattern recognition
"""
import sys
from langchain_openai import ChatOpenAI
from intelligent_router import IntelligentQueryRouter
from config import OPENAI_API_KEY, OPENAI_MODEL

# Test queries that should route to Jira
JIRA_QUERIES = [
    "how many tickets are related to epiqglobal2",
    "What is the retry file version for epiqglobal2?",
    "Show me PRI-9812 details",
    "What tickets mention lgads2?",
    "retry all file versions for roccofortehotel2",
    "version conflicts in pilottravelcenters migration",
    "Show me all tickets for Box to OneDrive",
    "What was the root cause of the epiqglobal2 issue?",
    "How many tickets are there for file version retry?",
    "List all tickets related to version conflicts"
]

def test_jira_routing():
    """Test that Jira-specific queries are routed correctly"""
    
    print("="*80)
    print("JIRA ROUTING TEST - Pattern Recognition")
    print("="*80)
    print("\nInitializing router...")
    
    # Initialize LLM and router
    llm = ChatOpenAI(
        model=OPENAI_MODEL,
        api_key=OPENAI_API_KEY,
        temperature=0
    )
    
    router = IntelligentQueryRouter(llm, total_budget=50)
    
    results = []
    
    for i, query in enumerate(JIRA_QUERIES, 1):
        print(f"\n{'='*80}")
        print(f"TEST {i}/{len(JIRA_QUERIES)}")
        print(f"{'='*80}")
        print(f"Query: \"{query}\"")
        
        try:
            # Get routing plan
            plan = router.route_query(query)
            
            # Extract Jira allocation
            jira_plan = plan.get("sources", {}).get("jira", {})
            jira_k = jira_plan.get("k", 0)
            jira_relevance = jira_plan.get("relevance", 0.0)
            
            # Check if it passed
            passed = jira_k >= 20 and jira_relevance >= 0.7
            status = "✅ PASS" if passed else "❌ FAIL"
            
            print(f"\n{status}")
            print(f"  Jira allocation: k={jira_k}, relevance={jira_relevance:.2f}")
            print(f"  Query type: {plan.get('query_type', 'N/A')}")
            print(f"  Reasoning: {jira_plan.get('reasoning', 'N/A')[:100]}...")
            
            # Show all allocations
            print(f"\n  All allocations:")
            for source, info in plan.get("sources", {}).items():
                k = info.get("k", 0)
                rel = info.get("relevance", 0.0)
                if k > 0:
                    print(f"    • {source}: k={k}, relevance={rel:.2f}")
            
            results.append({
                "query": query,
                "passed": passed,
                "jira_k": jira_k,
                "jira_relevance": jira_relevance
            })
            
        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            results.append({
                "query": query,
                "passed": False,
                "jira_k": 0,
                "jira_relevance": 0.0,
                "error": str(e)
            })
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}")
    
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = (passed_count / total_count * 100) if total_count > 0 else 0
    
    print(f"\nTotal tests: {total_count}")
    print(f"Passed: {passed_count}")
    print(f"Failed: {total_count - passed_count}")
    print(f"Pass rate: {pass_rate:.1f}%")
    
    print(f"\n{'='*80}")
    print("DETAILED RESULTS")
    print(f"{'='*80}")
    
    for i, result in enumerate(results, 1):
        status = "✅" if result["passed"] else "❌"
        print(f"\n{i}. {status} {result['query'][:60]}...")
        print(f"   Jira k={result['jira_k']}, relevance={result['jira_relevance']:.2f}")
    
    if pass_rate >= 80:
        print(f"\n🎉 SUCCESS! {pass_rate:.1f}% pass rate - Jira routing is working well!")
    elif pass_rate >= 60:
        print(f"\n⚠️  MODERATE: {pass_rate:.1f}% pass rate - Some improvements needed")
    else:
        print(f"\n❌ FAILURE: {pass_rate:.1f}% pass rate - Jira routing needs work")
    
    return results


if __name__ == "__main__":
    print("\n" + "="*80)
    print("Testing Enhanced Jira Routing with Pattern Recognition")
    print("="*80)
    print("\nThis test verifies that queries containing:")
    print("  • Ticket numbers (PRI-XXXX)")
    print("  • Server names (epiqglobal2, lgads2, etc.)")
    print("  • 'How many tickets' questions")
    print("  • Retry/version conflict keywords")
    print("\nAre correctly routed to Jira with high relevance (≥0.7) and k (≥20)")
    
    try:
        results = test_jira_routing()
        sys.exit(0)
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
