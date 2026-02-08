
import logging
from app.weaviate_client import get_weaviate_client
from weaviate.classes.query import MetadataQuery

logging.basicConfig(level=logging.INFO)

def test_with_actual_vector():
    print("--- Testing with actual vector from SharePointDocs ---\n")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        col = client.collections.get("SharePointDocs")
        
        # Fetch one object to get its vector
        response = col.query.fetch_objects(
            limit=1,
            include_vector=True,
            return_properties=["title", "content"]
        )
        
        if not response.objects:
            print("No objects found!")
            return
        
        obj = response.objects[0]
        print(f"Fetched object: {obj.properties.get('title', 'N/A')}")
        
        # Get the vector
        if isinstance(obj.vector, dict):
            test_vector = obj.vector.get('default')
        else:
            test_vector = obj.vector
        
        print(f"Vector length: {len(test_vector)}\n")
        
        # Now search using this exact vector - should return the same object
        print("Searching with this vector (should return same object)...")
        search_resp = col.query.near_vector(
            near_vector=test_vector,
            limit=5,
            return_metadata=MetadataQuery(distance=True)
        )
        
        print(f"Results: {len(search_resp.objects)} documents\n")
        
        if len(search_resp.objects) == 0:
            print("⚠️  CRITICAL: Even searching with an object's own vector returns 0 results!")
            print("This means the vector index is NOT working or NOT built.")
            print("\nPossible causes:")
            print("1. Vector index was not built during ingestion")
            print("2. Weaviate needs to be restarted to rebuild the index")
            print("3. There's a mismatch in vector dimensions")
        else:
            for i, result_obj in enumerate(search_resp.objects, 1):
                props = result_obj.properties
                dist = result_obj.metadata.distance if result_obj.metadata else 0.0
                print(f"{i}. Distance: {dist:.6f}")
                print(f"   UUID: {result_obj.uuid}")
                print(f"   Title: {props.get('title', 'N/A')}")
                print()
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_with_actual_vector()
