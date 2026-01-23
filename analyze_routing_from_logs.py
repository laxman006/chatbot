"""
Analyze intelligent routing behavior from terminal logs.
This provides insights into what sources are being retrieved for different queries.
"""
import re
import json
from collections import defaultdict

def parse_terminal_log(log_file_path):
    """Parse the terminal log to extract routing decisions."""
    print("=" * 80)
    print(" ROUTING ANALYSIS FROM TERMINAL LOGS")
    print("=" * 80)
    
    with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as f:
        log_content = f.read()
    
    # Find routing decisions
    routing_pattern = r'INTELLIGENT QUERY ROUTING.*?Query: (.+?)\n.*?Type: (\w+)\n.*?Intent: (.+?)\n.*?Confidence: ([\d.]+)'
    routing_matches = re.findall(routing_pattern, log_content, re.DOTALL)
    
    # Find retrieval results
    retrieval_pattern = r'Retrieved (\d+) docs from (\w+)\.\.\.\n.*?Retrieved (\d+) (\w+) documents'
    retrieval_matches = re.findall(retrieval_pattern, log_content)
    
    # Find final document counts
    final_count_pattern = r'Total candidates from all sources: (\d+)'
    final_counts = re.findall(final_count_pattern, log_content)
    
    print(f"\n[FOUND] {len(routing_matches)} routing decisions in logs")
    print(f"[FOUND] {len(final_counts)} retrieval results")
    
    # Analyze routing decisions
    print("\n" + "-" * 80)
    print(" RECENT ROUTING DECISIONS")
    print("-" * 80)
    
    for i, (query, qtype, intent, confidence) in enumerate(routing_matches[-10:], 1):  # Last 10
        print(f"\n{i}. Query: {query[:80]}...")
        print(f"   Type: {qtype}")
        print(f"   Intent: {intent[:80]}...")
        print(f"   Confidence: {confidence}")
    
    # Count query types
    query_types = defaultdict(int)
    for _, qtype, _, _ in routing_matches:
        query_types[qtype] += 1
    
    print("\n" + "-" * 80)
    print(" QUERY TYPE DISTRIBUTION")
    print("-" * 80)
    total = len(routing_matches)
    for qtype, count in sorted(query_types.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / total * 100) if total > 0 else 0
        print(f"   {qtype:20} {count:4d} ({percentage:5.1f}%)")
    
    # Analyze retrieval success
    print("\n" + "-" * 80)
    print(" RETRIEVAL SUCCESS ANALYSIS")
    print("-" * 80)
    
    zero_results = sum(1 for count in final_counts if int(count) == 0)
    total_queries = len(final_counts)
    
    if total_queries > 0:
        success_rate = ((total_queries - zero_results) / total_queries * 100)
        print(f"   Total queries analyzed: {total_queries}")
        print(f"   Queries with 0 results: {zero_results} ({(zero_results/total_queries*100):.1f}%)")
        print(f"   Queries with results: {total_queries - zero_results} ({success_rate:.1f}%)")
        
        # Find queries that returned 0 results
        zero_result_pattern = r'Query: (.+?)\n.*?Total candidates from all sources: 0'
        zero_result_queries = re.findall(zero_result_pattern, log_content, re.DOTALL)
        
        if zero_result_queries:
            print(f"\n   Recent queries with 0 results:")
            for query in zero_result_queries[-5:]:  # Last 5
                print(f"     - {query[:80]}...")
    
    # Recommendations
    print("\n" + "=" * 80)
    print(" RECOMMENDATIONS")
    print("=" * 80)
    
    if zero_results > 0:
        print(f"\n1. HIGH PRIORITY: {zero_results} queries returned 0 results")
        print("   - Check if vectorstore has relevant content for these query types")
        print("   - Adjust routing weights to cast a wider net")
        print("   - Consider adding query expansion/rewriting")
    
    if query_types.get("general_info", 0) > total * 0.5:
        print(f"\n2. Query Classification: {query_types.get('general_info', 0)} queries classified as 'general_info'")
        print("   - This might be too broad - consider adding more specific types:")
        print("     * migration_procedure")
        print("     * configuration")
        print("     * feature_comparison")
    
    print("\n3. Suggested new query types to add:")
    print("   - migration_procedure: for questions about changing settings during migrations")
    print("   - configuration: for questions about setup and configuration")
    print("   - feature_comparison: for comparing features between platforms")
    print("   - best_practices: for questions about recommended approaches")
    
    print("\n4. Source description improvements:")
    print("   - Blog: Add 'migration procedures', 'configuration guides', 'step-by-step'")
    print("   - Jira: Emphasize 'workarounds', 'known limitations', 'edge cases'")
    print("   - SharePoint: Add 'internal procedures', 'setup guides'")
    
    return {
        "total_routing_decisions": len(routing_matches),
        "query_types": dict(query_types),
        "total_queries": total_queries,
        "zero_results": zero_results,
        "success_rate": success_rate if total_queries > 0 else 0
    }


if __name__ == "__main__":
    # Try to find the terminal log file
    import os
    
    terminal_dir = r"c:\Users\LaxmanKadari\.cursor\projects\c-Users-LaxmanKadari-Desktop-v1-dev-chatbot\terminals"
    
    # Find the most recent terminal file
    terminal_files = [f for f in os.listdir(terminal_dir) if f.endswith('.txt')]
    
    if not terminal_files:
        print("[ERROR] No terminal log files found")
        exit(1)
    
    # Use terminal 3.txt (the one from the screenshots)
    log_file = os.path.join(terminal_dir, "3.txt")
    
    if not os.path.exists(log_file):
        print(f"[ERROR] Terminal log file not found: {log_file}")
        exit(1)
    
    print(f"[OK] Analyzing log file: {log_file}\n")
    
    results = parse_terminal_log(log_file)
    
    # Export results
    with open("routing_log_analysis.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n[OK] Analysis exported to: routing_log_analysis.json")
