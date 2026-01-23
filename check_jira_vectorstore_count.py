"""
Check Jira vectorstore document count and compare with cache
"""
import json
from app.jira_vectorstore import get_jira_vectorstore

# Load cache
print("=" * 80)
print("JIRA CACHE vs VECTORSTORE COMPARISON")
print("=" * 80)

with open('data/jira_tickets_cache.json', encoding='utf-8') as f:
    cache_data = json.load(f)
    tickets = cache_data.get('tickets', [])
    
unique_keys = set(t['key'] for t in tickets)

print(f"\n[CACHE]")
print(f"  Total entries: {len(tickets)}")
print(f"  Unique tickets: {len(unique_keys)}")
print(f"  Average chunks per ticket: {len(tickets)/len(unique_keys):.1f}")

# Check vectorstore
print(f"\n[JIRA VECTORSTORE]")
try:
    jira_vs = get_jira_vectorstore()
    if jira_vs:
        collection = jira_vs._collection
        doc_count = collection.count()
        print(f"  Documents in vectorstore: {doc_count}")
        print(f"  Collection name: {collection.name}")
        
        # Try to get some sample documents to verify structure
        sample = collection.get(limit=3, include=['metadatas', 'documents'])
        if sample and sample['ids']:
            print(f"\n[SAMPLE DOCUMENTS]")
            for i, (doc_id, metadata) in enumerate(zip(sample['ids'][:3], sample['metadatas'][:3])):
                ticket_key = metadata.get('ticket_key', 'N/A')
                section = metadata.get('section', 'N/A')
                print(f"  {i+1}. ID: {doc_id[:50]}...")
                print(f"     ticket_key: {ticket_key}, section: {section}")
        
        # Calculate coverage
        print(f"\n[COVERAGE ANALYSIS]")
        if doc_count == len(tickets):
            print(f"  ✓ PERFECT MATCH: All {len(tickets)} cache entries are in vectorstore")
        elif doc_count < len(tickets):
            missing = len(tickets) - doc_count
            print(f"  ✗ MISSING: {missing} documents ({missing/len(tickets)*100:.1f}%) not in vectorstore")
            print(f"  Action needed: Rebuild Jira vectorstore")
        else:
            extra = doc_count - len(tickets)
            print(f"  ⚠ EXTRA: {extra} documents in vectorstore but not in cache")
            print(f"  This might be from a previous version of the cache")
    else:
        print("  ✗ Jira vectorstore NOT FOUND or EMPTY")
        print("  Action needed: Build Jira vectorstore from scratch")
except Exception as e:
    print(f"  ✗ Error loading vectorstore: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
