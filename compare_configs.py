
from app.weaviate_client import get_weaviate_client
import json

def compare_configs():
    client = get_weaviate_client()
    for name in ['Blogs', 'SharePointDocs']:
        col = client.collections.get(name)
        cfg = col.config.get()
        print(f"\n--- {name} ---")
        print(f"Vectorizer: {cfg.vectorizer_config}")
        # print(f"Vector Config: {cfg.vector_config}")
        
        # Check specific HNSW settings
        if 'default' in cfg.vector_config:
            hnsw = cfg.vector_config['default'].vector_index_config
            print(f"HNSW Config: distance={hnsw.distance_metric}, ef={hnsw.ef}, ef_construction={hnsw.ef_construction}, max_connections={hnsw.max_connections}")
            print(f"HNSW Skip: {hnsw.skip}")
        else:
            print("No 'default' vector config found")

if __name__ == "__main__":
    compare_configs()
