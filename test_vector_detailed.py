"""
Detailed diagnostic script to verify vector storage in Weaviate.

This script provides more detailed information about vector structure,
dimensions, and actual values to diagnose ingestion issues.
"""

import sys
from app.weaviate_client import get_weaviate_client

def test_vector_storage_detailed(collection_name: str = "Transcripts", limit: int = 5):
    """
    Detailed test of vector storage with full diagnostics.
    
    Args:
        collection_name: Collection name to test
        limit: Number of objects to check
    """
    print(f"[DETAILED] Vector Storage Test: {collection_name}")
    print("=" * 70)
    
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
            return False
        
        print(f"[OK] Found {len(result.objects)} objects\n")
        
        all_have_vectors = True
        for i, obj in enumerate(result.objects, 1):
            print(f"{'='*70}")
            print(f"Object {i}:")
            print(f"  UUID: {obj.uuid}")
            
            # Check vector type and structure
            print(f"  Vector type: {type(obj.vector)}")
            
            if obj.vector is None:
                print("  [ERROR] Vector is None")
                all_have_vectors = False
                continue
            
            # Handle different vector formats
            if isinstance(obj.vector, dict):
                print(f"  [WARNING] Vector is a dictionary: {list(obj.vector.keys())}")
                # In Weaviate v4, vectors might be in a dict format
                if "default" in obj.vector:
                    vector_data = obj.vector["default"]
                    print(f"  Using 'default' key from vector dict")
                else:
                    # Try to get first value
                    vector_data = list(obj.vector.values())[0] if obj.vector else None
                    print(f"  Using first value from vector dict")
            elif isinstance(obj.vector, list):
                vector_data = obj.vector
            else:
                print(f"  [WARNING] Unexpected vector type: {type(obj.vector)}")
                vector_data = None
            
            if vector_data is None:
                print("  [ERROR] Could not extract vector data")
                all_have_vectors = False
                continue
            
            # Check vector dimensions
            if isinstance(vector_data, list):
                vector_dim = len(vector_data)
                print(f"  [OK] Vector dimension: {vector_dim}")
                
                if vector_dim == 1:
                    print(f"  [WARNING] Vector dimension is 1 (should be 1536 for text-embedding-3-small)")
                    print(f"  Vector value: {vector_data}")
                    all_have_vectors = False
                elif vector_dim == 1536:
                    print(f"  [OK] Correct dimension for text-embedding-3-small")
                    # Show first few values
                    print(f"  First 5 values: {vector_data[:5]}")
                    print(f"  Last 5 values: {vector_data[-5:]}")
                    print(f"  Min value: {min(vector_data):.6f}")
                    print(f"  Max value: {max(vector_data):.6f}")
                    print(f"  Mean value: {sum(vector_data)/len(vector_data):.6f}")
                else:
                    print(f"  [WARNING] Unexpected dimension: {vector_dim} (expected 1536)")
                    print(f"  First 5 values: {vector_data[:5]}")
                    all_have_vectors = False
            else:
                print(f"  [ERROR] Vector data is not a list: {type(vector_data)}")
                print(f"  Vector data: {vector_data}")
                all_have_vectors = False
            
            # Show metadata
            if hasattr(obj, 'properties'):
                chunk_key = obj.properties.get('chunk_key', 'N/A')
                print(f"  chunk_key: {chunk_key}")
                content_preview = obj.properties.get('content', '')[:100] if obj.properties.get('content') else 'N/A'
                print(f"  content preview: {content_preview}...")
            
            print()
        
        print("=" * 70)
        if all_have_vectors:
            print("[SUCCESS] All objects have correctly dimensioned vectors!")
            return True
        else:
            print("[FAILURE] Some objects have incorrect or missing vectors!")
            return False
            
    except Exception as e:
        print(f"[ERROR] Error testing vector storage: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Close client to avoid resource warnings
        try:
            client.close()
        except:
            pass


if __name__ == "__main__":
    collection_name = sys.argv[1] if len(sys.argv) > 1 else "Transcripts"
    success = test_vector_storage_detailed(collection_name)
    sys.exit(0 if success else 1)
