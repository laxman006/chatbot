
import logging
from app.weaviate_client import get_weaviate_client

logging.basicConfig(level=logging.INFO)

def check_migration_type():
    print("--- Checking migration_type in SharePointDocs ---")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        col = client.collections.get("SharePointDocs")
        
        # Fetch first 10 objects to check migration_type
        response = col.query.fetch_objects(
            limit=10,
            return_properties=["title", "migration_type", "chunk_id", "content"]
        )
        
        print(f"\nTotal objects in SharePointDocs: 1752")
        print(f"\nChecking first 10 objects for migration_type field:\n")
        
        for i, obj in enumerate(response.objects, 1):
            props = obj.properties
            migration_type = props.get('migration_type', 'MISSING')
            title = props.get('title', 'N/A')
            content_preview = props.get('content', '')[:100]
            
            print(f"Object {i}:")
            print(f"  Title: {title}")
            print(f"  migration_type: {migration_type}")
            print(f"  Content: {content_preview}...")
            print()
            
        # Check how many have slack__TO__slack specifically
        print("\n--- Checking for slack__TO__slack filter ---")
        from weaviate.classes.query import Filter
        
        filtered_response = col.query.fetch_objects(
            limit=5,
            filters=Filter.by_property("migration_type").equal("slack__TO__slack"),
            return_properties=["title", "migration_type"]
        )
        
        print(f"Objects with migration_type='slack__TO__slack': {len(filtered_response.objects)}")
        for obj in filtered_response.objects:
            print(f"  - {obj.properties.get('title', 'N/A')}")
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_migration_type()
