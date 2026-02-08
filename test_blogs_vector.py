
import logging
from app.weaviate_client import get_weaviate_client
from weaviate.classes.query import MetadataQuery

logging.basicConfig(level=logging.INFO)

def test_blogs_vector():
    print("--- Testing with actual vector from Blogs ---\n")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        col = client.collections.get("Blogs")
        
        # Fetch one object to get its vector
        response = col.query.fetch_objects(
            limit=1,
            include_vector=True,
            return_properties=["title"]
        )
        
        if not response.objects:
            print("No objects found in Blogs!")
            return
        
        obj = response.objects[0]
        print(f"Fetched blog: {obj.properties.get('title', 'N/A')}")
        
        # Get the vector
        if isinstance(obj.vector, dict):
            test_vector = obj.vector.get('default')
        else:
            test_vector = obj.vector
        
        if not test_vector:
            print("No vector found in blog object!")
            return
            
        print(f"Vector length: {len(test_vector)}\n")
        
        # Now search using this exact vector
        print("Searching with this vector in Blogs...")
        search_resp = col.query.near_vector(
            near_vector=test_vector,
            limit=5,
            return_metadata=MetadataQuery(distance=True)
        )
        
        print(f"Results: {len(search_resp.objects)} documents\n")
        for i, result_obj in enumerate(search_resp.objects, 1):
             print(f"{i}. Title: {result_obj.properties.get('title')}, Dist: {result_obj.metadata.distance}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_blogs_vector()
