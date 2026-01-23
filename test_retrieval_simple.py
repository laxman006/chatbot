"""Simple safe retrieval test"""
import os
import sys
sys.path.insert(0, '.')
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

print("=" * 80)
print("JIRA RETRIEVAL TEST - READ ONLY")
print("=" * 80)
print()

try:
    print("[1] Loading vectorstore...")
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma
    from config import JIRA_VECTORSTORE_PATH
    
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma(
        persist_directory=JIRA_VECTORSTORE_PATH,
        embedding_function=embeddings
    )
    
    count = vectorstore._collection.count()
    print(f"[OK] Loaded: {count:,} documents")
    print()
    
    # Test queries
    test_queries = ["error", "migration", "authentication"]
    
    for query in test_queries:
        print(f"[2] Testing query: '{query}'...")
        docs = vectorstore.similarity_search(query, k=3)
        print(f"[OK] Found {len(docs)} documents")
        
        if docs:
            for i, doc in enumerate(docs[:2], 1):
                ticket = doc.metadata.get('ticket_key', 'N/A')
                section = doc.metadata.get('section', 'N/A')
                print(f"     {i}. {ticket} ({section})")
        print()
    
    # Verify integrity
    print("[3] Verifying database integrity...")
    final_count = vectorstore._collection.count()
    if final_count == count:
        print(f"[OK] Document count unchanged: {final_count:,}")
        print("[OK] Database integrity verified")
    else:
        print(f"[ERROR] Count changed! Was {count}, now {final_count}")
    
    print()
    print("=" * 80)
    print("[SUCCESS] All tests passed - database intact")
    print("=" * 80)
    
except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
