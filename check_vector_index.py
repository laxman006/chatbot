
import logging
from app.weaviate_client import get_weaviate_client

logging.basicConfig(level=logging.INFO)

def check_vector_index():
    print("--- Checking SharePointDocs Vector Index Configuration ---\n")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        col = client.collections.get("SharePointDocs")
        config = col.config.get()
        
        print(f"Collection: {config.name}")
        print(f"Description: {config.description}")
        print(f"\nVector Config:")
        print(f"  {config.vector_config}")
        print(f"\nProperties (first 10):")
        for prop in list(config.properties)[:10]:
            print(f"  - {prop.name} ({prop.data_type})")
        
        # Try a simple fetch to see actual vector structure
        print(f"\n--- Fetching one object to inspect vector structure ---")
        response = col.query.fetch_objects(
            limit=1,
            include_vector=True
        )
        
        if response.objects:
            obj = response.objects[0]
            print(f"\nObject UUID: {obj.uuid}")
            print(f"Vector type: {type(obj.vector)}")
            print(f"Vector keys (if dict): {obj.vector.keys() if isinstance(obj.vector, dict) else 'N/A'}")
            if isinstance(obj.vector, dict):
                for key, vec in obj.vector.items():
                    print(f"  Vector '{key}': length={len(vec) if vec else 0}")
            elif isinstance(obj.vector, list):
                print(f"  Vector length: {len(obj.vector)}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_vector_index()
