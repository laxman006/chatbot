"""
Test script to verify vectors are stored correctly in Weaviate.

Run this after ingestion to confirm vectors exist:
    python test_vector_storage.py
"""

import sys
from app.weaviate_client import get_weaviate_client

def test_vector_storage(collection_name: str = "SharePointDocs", limit: int = 5):
    """
    Test that vectors are stored in Weaviate collection.
    
    Args:
        collection_name: Collection name to test
        limit: Number of objects to check
    """
    print(f"[TEST] Vector storage in collection: {collection_name}")
    print("-" * 60)
    
    client = get_weaviate_client()
    if client is None:
        print("[ERROR] Failed to get Weaviate client")
        return False
    
    try:
        collection = client.collections.get(collection_name)
        
        # Fetch objects with vectors
        result = collection.query.fetch_objects(limit=limit, include_vector=True)
        
        if not result.objects:
            print(f"[WARNING] No objects found in collection '{collection_name}'")
            print("   Run ingestion first to populate the collection.")
            return False
        
        print(f"[OK] Found {len(result.objects)} objects")
        print()
        
        all_have_vectors = True
        for i, obj in enumerate(result.objects, 1):
            # In Weaviate v4, vectors are returned as dict with "default" key
            # Extract the actual vector list from the dict
            vector_data = None
            if obj.vector is not None:
                if isinstance(obj.vector, dict):
                    # Weaviate v4 format: {"default": [vector list]}
                    vector_data = obj.vector.get("default")
                elif isinstance(obj.vector, list):
                    # Direct list format (fallback)
                    vector_data = obj.vector
                else:
                    vector_data = None
            
            has_vector = vector_data is not None and len(vector_data) > 0
            vector_dim = len(vector_data) if has_vector else 0
            
            status = "[OK]" if has_vector else "[ERROR]"
            print(f"{status} Object {i}: vector_dim={vector_dim}, has_vector={has_vector}")
            
            if not has_vector:
                all_have_vectors = False
                print(f"   [WARNING] Object UUID: {obj.uuid}")
                if hasattr(obj, 'properties') and 'chunk_key' in obj.properties:
                    print(f"   [WARNING] chunk_key: {obj.properties.get('chunk_key')}")
        
        print()
        print("-" * 60)
        if all_have_vectors:
            print("[SUCCESS] All objects have vectors stored!")
            print("   Your vectorizer=None setup is working correctly.")
            return True
        else:
            print("[FAILURE] Some objects are missing vectors!")
            print("   Check your ingestion pipeline - vectors may not be generated.")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error testing vector storage: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Close client to avoid resource warnings
        try:
            if client:
                client.close()
        except:
            pass


if __name__ == "__main__":
    # Test default collection
    collection_name = sys.argv[1] if len(sys.argv) > 1 else "SharePointDocs"
    success = test_vector_storage(collection_name)
    sys.exit(0 if success else 1)
