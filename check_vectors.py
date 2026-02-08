
import asyncio
import logging
from app.weaviate_client import get_weaviate_client

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_vectors():
    print("--- Checking All Collections ---")
    client = get_weaviate_client()
    if not client:
        print("ERROR: Could not connect to Weaviate.")
        return

    try:
        collections = client.collections.list_all()
        print(f"Collections found: {list(collections.keys())}")
        
        for name in collections.keys():
            try:
                col = client.collections.get(name)
                agg = col.aggregate.over_all(total_count=True)
                print(f"  - {name}: {agg.total_count} documents")
            except Exception as e:
                print(f"  - {name}: Error getting count ({e})")

    except Exception as e:
        print(f"Error checking collections: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    check_vectors()
