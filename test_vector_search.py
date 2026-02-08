
import logging
from app.weaviate_client import get_weaviate_client
from app.embedding_service import EmbeddingService
from weaviate.classes.query import Filter, MetadataQuery

logging.basicConfig(level=logging.INFO)

def test_vector_search():
    print("--- Testing Vector Search on SharePointDocs ---\n")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    # Generate embedding for the query
    query = "what are the limitations of slack to slack"
    print(f"Query: {query}\n")
    
    from langchain_openai import OpenAIEmbeddings
    embeddings_model = OpenAIEmbeddings(model="text-embedding-3-small")
    query_vector = embeddings_model.embed_query(query)
    print(f"Generated embedding vector (length: {len(query_vector)})\n")

    try:
        col = client.collections.get("SharePointDocs")
        
        # Test 1: Vector search WITHOUT any filter
        print("=" * 60)
        print("TEST 1: Vector search WITHOUT filter (no target_vector)")
        print("=" * 60)
        resp1 = col.query.near_vector(
            near_vector=query_vector,
            limit=5,
            return_metadata=MetadataQuery(distance=True)
        )
        print(f"Results: {len(resp1.objects)} documents\n")
        
        # Test 1b: Vector search WITH target_vector='default'
        print("=" * 60)
        print("TEST 1b: Vector search WITHOUT filter (WITH target_vector='default')")
        print("=" * 60)
        resp1b = col.query.near_vector(
            near_vector=query_vector,
            target_vector="default",
            limit=5,
            return_metadata=MetadataQuery(distance=True)
        )
        print(f"Results: {len(resp1b.objects)} documents\n")
        for i, obj in enumerate(resp1b.objects, 1):
            props = obj.properties
            dist = obj.metadata.distance if obj.metadata else 0.0
            print(f"{i}. Distance: {dist:.4f}")
            print(f"   Title: {props.get('title', 'N/A')}")
            print(f"   migration_type: {props.get('migration_type', 'MISSING')}")
            print()
        
        # Test 2: Vector search WITH migration_type filter
        print("=" * 60)
        print("TEST 2: Vector search WITH migration_type='slack__TO__slack'")
        print("=" * 60)
        migration_filter = Filter.by_property("migration_type").equal("slack__TO__slack")
        resp2 = col.query.near_vector(
            near_vector=query_vector,
            limit=5,
            filters=migration_filter,
            return_metadata=MetadataQuery(distance=True)
        )
        print(f"Results: {len(resp2.objects)} documents\n")
        for i, obj in enumerate(resp2.objects, 1):
            props = obj.properties
            dist = obj.metadata.distance if obj.metadata else 0.0
            print(f"{i}. Distance: {dist:.4f}")
            print(f"   Title: {props.get('title', 'N/A')}")
            print(f"   migration_type: {props.get('migration_type', 'MISSING')}")
            print(f"   Content preview: {props.get('content', '')[:100]}...")
            print()
            
        if len(resp2.objects) == 0:
            print("⚠️  PROBLEM: Filter returned 0 results even though we know slack__TO__slack docs exist!")
            print("This suggests the vectors might be missing or the filter is not working correctly.")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_vector_search()
