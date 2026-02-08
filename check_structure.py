
from app.weaviate_client import get_weaviate_client
import weaviate

def check_structure():
    client = get_weaviate_client()
    for name in ['Blogs', 'SharePointDocs']:
        try:
            col = client.collections.get(name)
            cfg = col.config.get()
            print(f"\n--- {name} ---")
            print(f"Vectorizer: {cfg.vectorizer_config}")
            print(f"Vector Config type: {type(cfg.vector_config)}")
            print(f"Vector Config: {cfg.vector_config}")
        except Exception as e:
            print(f"Error for {name}: {e}")

if __name__ == "__main__":
    check_structure()
