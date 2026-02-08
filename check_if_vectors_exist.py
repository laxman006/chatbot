
import logging
from app.weaviate_client import get_weaviate_client

logging.basicConfig(level=logging.INFO)

def check_if_vectors_exist():
    print("--- Checking if SharePointDocs objects have vectors ---\n")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        col = client.collections.get("SharePointDocs")
        
        # Fetch first 10 objects WITH vectors
        response = col.query.fetch_objects(
            limit=10,
            include_vector=True,
            return_properties=["title", "chunk_id"]
        )
        
        print(f"Checking first 10 objects:\n")
        
        with_vectors = 0
        without_vectors = 0
        
        for i, obj in enumerate(response.objects, 1):
            # Check if vector exists
            has_vector = False
            if hasattr(obj, 'vector') and obj.vector is not None:
                if isinstance(obj.vector, dict):
                    # Multi-vector case
                    has_vector = len(obj.vector.get('default', [])) > 0
                elif isinstance(obj.vector, list):
                    # Single vector case
                    has_vector = len(obj.vector) > 0
            
            if has_vector:
                with_vectors += 1
                vec_len = len(obj.vector.get('default', [])) if isinstance(obj.vector, dict) else len(obj.vector)
                print(f"Object {i}: HAS VECTOR (length: {vec_len})")
            else:
                without_vectors += 1
                print(f"Object {i}: NO VECTOR ❌")
            
            print(f"  Title: {obj.properties.get('title', 'N/A')}")
            print()
        
        print("=" * 60)
        print(f"Summary:")
        print(f"  Objects WITH vectors: {with_vectors}")
        print(f"  Objects WITHOUT vectors: {without_vectors}")
        print("=" * 60)
        
        if without_vectors > 0:
            print("\n⚠️  PROBLEM FOUND!")
            print("The SharePointDocs collection has objects WITHOUT vectors.")
            print("This is why vector search (near_vector) returns 0 results.")
            print("\nSOLUTION: Re-run ingestion to ensure vectors are generated and stored.")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_if_vectors_exist()
