import sys
import os
from pathlib import Path
import logging

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.weaviate_client import get_weaviate_client
from app.weaviate_schema import COLLECTIONS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def delete_collection(name: str):
    client = get_weaviate_client()
    if client is None:
        logger.error("Weaviate client unavailable")
        return
    
    if client.collections.exists(name):
        logger.info(f"Deleting collection: {name}...")
        client.collections.delete(name)
        logger.info(f"✓ Collection {name} deleted.")
    else:
        logger.info(f"Collection {name} does not exist.")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Clear Weaviate collections")
    parser.add_argument("--all", action="store_true", help="Delete all collections")
    parser.add_argument("--collection", type=str, choices=COLLECTIONS, help="Collection to delete")
    
    args = parser.parse_args()
    
    if args.all:
        confirm = input("Are you sure you want to delete ALL collections? (y/n): ")
        if confirm.lower() == 'y':
            for col in COLLECTIONS:
                delete_collection(col)
        else:
            print("Aborted.")
    elif args.collection:
        delete_collection(args.collection)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
