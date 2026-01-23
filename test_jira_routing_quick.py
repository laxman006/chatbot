"""
Quick test of improved Jira routing
"""
from langchain_openai import ChatOpenAI
from intelligent_router import IntelligentQueryRouter
from config import OPENAI_API_KEY, OPENAI_MODEL

print("="*80)
print("QUICK JIRA ROUTING TEST")
print("="*80)

# Initialize
print("\nInitializing router...")
llm = ChatOpenAI(model=OPENAI_MODEL, api_key=OPENAI_API_KEY, temperature=0)
router = IntelligentQueryRouter(llm, total_budget=50)

# Test critical queries
test_queries = [
    "how many tickets are related to epiqglobal2",
    "What is the retry file version for epiqglobal2?",
    "Show me PRI-9812 details"
]

for i, query in enumerate(test_queries, 1):
    print(f"\n{'='*60}")
    print(f"TEST {i}: {query}")
    print(f"{'='*60}")
    
    try:
        plan = router.route_query(query)
        jira = plan.get("sources", {}).get("jira", {})
        
        print(f"✓ Jira: k={jira.get('k', 0)}, relevance={jira.get('relevance', 0):.2f}")
        print(f"  Type: {plan.get('query_type')}")
        print(f"  Intent: {plan.get('query_intent', '')[:80]}...")
        
        # Check if passed
        if jira.get('k', 0) >= 20 and jira.get('relevance', 0) >= 0.7:
            print("✅ PASS - Correctly routed to Jira!")
        else:
            print("❌ FAIL - Jira allocation too low")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

print("\n" + "="*80)
print("✅ Test complete! Check results above.")
print("="*80)
