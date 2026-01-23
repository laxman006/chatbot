"""
Test intelligent routing with various queries and analyze results.
This helps understand what data is being retrieved from different sources.
"""
import requests
import json
from collections import defaultdict

# Assuming server is running on localhost:8000
API_BASE = "http://localhost:8000"

# Test queries covering different scenarios
TEST_QUERIES = [
    # Migration procedures
    {
        "query": "if during an ongoing migration the csv needs to be changed should we change from UI or from backend",
        "expected_type": "migration_procedure",
        "expected_sources": ["blog", "jira", "pdfs"]
    },
    # Troubleshooting
    {
        "query": "migration failed with error 500",
        "expected_type": "troubleshooting",
        "expected_sources": ["jira", "blog"]
    },
    # General info
    {
        "query": "what is CloudFuze Migrate",
        "expected_type": "general_info",
        "expected_sources": ["blog", "pdfs"]
    },
    # Compliance
    {
        "query": "do you have SOC 2 certification",
        "expected_type": "compliance",
        "expected_sources": ["sharepoint", "blog"]
    },
    # Technical
    {
        "query": "API rate limits for migration",
        "expected_type": "technical",
        "expected_sources": ["pdfs", "blog"]
    },
    # Sales
    {
        "query": "customer objection about pricing",
        "expected_type": "sales",
        "expected_sources": ["transcripts", "blog"]
    },
    # Error resolution
    {
        "query": "how to fix user not found error in Teams migration",
        "expected_type": "troubleshooting",
        "expected_sources": ["jira", "blog"]
    },
    # Migration types
    {
        "query": "Teams to SharePoint migration",
        "expected_type": "general_info",
        "expected_sources": ["blog", "jira"]
    },
]


def analyze_routing_behavior():
    """Test routing behavior with different query types."""
    print("=" * 80)
    print(" INTELLIGENT ROUTING BEHAVIOR ANALYSIS")
    print("=" * 80)
    
    results = []
    
    for idx, test in enumerate(TEST_QUERIES, 1):
        query = test["query"]
        print(f"\n{'=' * 80}")
        print(f"TEST {idx}: {query}")
        print(f"Expected type: {test['expected_type']}")
        print(f"Expected sources: {', '.join(test['expected_sources'])}")
        print("-" * 80)
        
        # Call the chat endpoint (streaming disabled for analysis)
        try:
            response = requests.post(
                f"{API_BASE}/chat",
                json={
                    "message": query,
                    "conversation_id": f"test_routing_{idx}",
                    "stream": False
                },
                headers={"Authorization": "Bearer test_token"},
                timeout=30
            )
            
            if response.status_code != 200:
                print(f"[ERROR] Status {response.status_code}")
                print(f"   Response: {response.text[:200]}")
                continue
                
            data = response.json()
            
            # Extract routing information from response
            answer = data.get("answer", "")
            sources = data.get("sources", [])
            
            # Analyze sources retrieved
            source_breakdown = defaultdict(int)
            for source in sources:
                # Determine source type from metadata
                if isinstance(source, dict):
                    tag = source.get("tag", "unknown")
                    source_type = source.get("source_type", "unknown")
                    
                    # Categorize
                    if "blog" in tag.lower() or source_type == "web":
                        source_breakdown["blog"] += 1
                    elif "jira" in tag.lower() or source_type == "jira":
                        source_breakdown["jira"] += 1
                    elif "sharepoint" in tag.lower() or "sharepoint" in source_type.lower():
                        source_breakdown["sharepoint"] += 1
                    elif "pdf" in source_type.lower():
                        source_breakdown["pdfs"] += 1
                    elif "transcript" in tag.lower():
                        source_breakdown["transcripts"] += 1
                    elif "excel" in source_type.lower():
                        source_breakdown["excel"] += 1
                    else:
                        source_breakdown["other"] += 1
            
            # Print results
            total_sources = sum(source_breakdown.values())
            print(f"\n[RETRIEVED] {total_sources} sources:")
            for source_type, count in sorted(source_breakdown.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / total_sources * 100) if total_sources > 0 else 0
                print(f"   {source_type:12} {count:3d} ({percentage:5.1f}%)")
            
            # Check if expected sources were used
            expected_sources = set(test['expected_sources'])
            actual_sources = set(source_breakdown.keys())
            
            matched = expected_sources & actual_sources
            missing = expected_sources - actual_sources
            extra = actual_sources - expected_sources
            
            if total_sources == 0:
                print(f"\n[FAIL] NO SOURCES RETRIEVED - This is a problem!")
            elif matched == expected_sources:
                print(f"\n[OK] GOOD: Retrieved from all expected sources: {', '.join(matched)}")
            else:
                if matched:
                    print(f"\n[PARTIAL] Retrieved from: {', '.join(matched)}")
                if missing:
                    print(f"   Missing expected sources: {', '.join(missing)}")
                if extra:
                    print(f"   Extra sources (not expected): {', '.join(extra)}")
            
            # Store result
            results.append({
                "query": query,
                "expected_type": test["expected_type"],
                "expected_sources": list(expected_sources),
                "actual_sources": dict(source_breakdown),
                "total_retrieved": total_sources,
                "matched": list(matched),
                "missing": list(missing),
                "extra": list(extra)
            })
            
        except Exception as e:
            print(f"[ERROR] Exception: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print("\n" + "=" * 80)
    print(" SUMMARY & RECOMMENDATIONS")
    print("=" * 80)
    
    total_tests = len(results)
    tests_with_results = sum(1 for r in results if r["total_retrieved"] > 0)
    perfect_matches = sum(1 for r in results if not r["missing"] and r["total_retrieved"] > 0)
    
    print(f"\nTests run: {total_tests}")
    print(f"Tests with retrieved documents: {tests_with_results}/{total_tests}")
    print(f"Perfect matches (all expected sources): {perfect_matches}/{total_tests}")
    print(f"Success rate: {(tests_with_results/total_tests*100):.1f}%")
    print(f"Perfect rate: {(perfect_matches/total_tests*100):.1f}%")
    
    # Identify problematic query types
    print("\n[QUERY TYPE ANALYSIS]")
    by_type = defaultdict(list)
    for result in results:
        by_type[result["expected_type"]].append(result)
    
    for query_type, type_results in by_type.items():
        total = len(type_results)
        with_results = sum(1 for r in type_results if r["total_retrieved"] > 0)
        print(f"\n  {query_type}:")
        print(f"    Success: {with_results}/{total}")
        
        if with_results < total:
            failed = [r for r in type_results if r["total_retrieved"] == 0]
            print(f"    Failed queries:")
            for r in failed:
                print(f"      - \"{r['query'][:60]}...\"")
    
    # Source usage analysis
    print("\n[SOURCE USAGE ANALYSIS]")
    all_sources_used = defaultdict(int)
    for result in results:
        for source, count in result["actual_sources"].items():
            all_sources_used[source] += count
    
    total_docs = sum(all_sources_used.values())
    print(f"\n  Total documents retrieved: {total_docs}")
    for source, count in sorted(all_sources_used.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total_docs * 100) if total_docs > 0 else 0
        print(f"    {source:12} {count:4d} ({percentage:5.1f}%)")
    
    # Export results
    with open("routing_analysis_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[OK] Detailed results exported to: routing_analysis_results.json")
    
    return results


if __name__ == "__main__":
    print("\n[NOTE] This script requires the backend server to be running on localhost:8000")
    print("If the server is not running, please start it first.\n")
    
    try:
        # Quick health check - try multiple endpoints
        endpoints_to_try = ["/health", "/", "/docs"]
        server_running = False
        
        for endpoint in endpoints_to_try:
            try:
                response = requests.get(f"{API_BASE}{endpoint}", timeout=5)
                if response.status_code in [200, 404]:  # 404 is ok, means server is running
                    server_running = True
                    print(f"[OK] Server is running (checked {endpoint})\n")
                    break
            except:
                continue
        
        if not server_running:
            print("[ERROR] Server is not responding. Please start the server first.\n")
            print("Run: python server.py\n")
            exit(1)
    except Exception as e:
        print(f"[ERROR] Could not connect to server: {e}\n")
        exit(1)
    
    analyze_routing_behavior()
