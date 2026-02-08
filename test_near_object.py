
import logging
from app.weaviate_client import get_weaviate_client
from weaviate.classes.query import MetadataQuery

logging.basicConfig(level=logging.INFO)

def test_near_object():
    print("--- Testing near_object in SharePointDocs ---\n")
    client = get_weaviate_client()
    if not client:
        return

    try:
        col = client.collections.get("SharePointDocs")
        
        # Get one object
        response = col.query.fetch_objects(limit=1)
        if not response.objects:
            print("No objects found!")
            return
            
        target_uuid = response.objects[0].uuid
        print(f"Target object UUID: {target_uuid}")
        
        # Search near this object
        print("Searching near_object...")
        search_resp = col.query.near_object(
            near_object=target_uuid,
            limit=5,
            target_vector="default", # Try with target_vector
            return_metadata=MetadataQuery(distance=True)
        )
        
        print(f"Results with target_vector='default': {len(search_resp.objects)}")
        for i, obj in enumerate(search_resp.objects, 1):
            print(f"  {i}. {obj.uuid}, distance: {obj.metadata.distance}")

        # Search without target_vector
        print("\nSearching near_object without target_vector...")
        search_resp2 = col.query.near_object(
            near_object=target_uuid,
            limit=5,
            return_metadata=MetadataQuery(distance=True)
        )
        print(f"Results without target_vector: {len(search_resp2.objects)}")
        for i, obj in enumerate(search_resp2.objects, 1):
            print(f"  {i}. {obj.uuid}, distance: {obj.metadata.distance}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_near_object()
