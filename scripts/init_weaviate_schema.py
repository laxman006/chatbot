"""
Initialize Weaviate schema - Create all required collections.

Run this script after starting Weaviate to set up the schema.
This creates source-based collections (SharePointDocs, Blogs, JiraTickets, etc.)

Examples:
  python scripts/init_weaviate_schema.py              # create missing collections only
  python scripts/init_weaviate_schema.py --recreate   # delete and recreate ALL collections
  python scripts/init_weaviate_schema.py --recreate-only Blogs   # recreate only Blogs (e.g. after schema change)
"""

import argparse
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.weaviate_schema import create_all_collections, create_collection, COLLECTIONS
from app.weaviate_client import get_weaviate_client, check_weaviate_health
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Initialize Weaviate schema."""
    parser = argparse.ArgumentParser(
        description="Create or recreate Weaviate collections.",
        epilog="Use --recreate-only Blogs to apply new blog schema (e.g. doc_summary, author_name) then run: python scripts/ingest_to_weaviate.py --source blog"
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Delete and recreate ALL collections (data in all collections will be lost)",
    )
    parser.add_argument(
        "--recreate-only",
        type=str,
        metavar="COLLECTION",
        choices=COLLECTIONS,
        help=f"Recreate only this collection (e.g. Blogs). Valid: {', '.join(COLLECTIONS)}",
    )
    args = parser.parse_args()

    if args.recreate and args.recreate_only:
        print("[!] ERROR: Use either --recreate or --recreate-only, not both.")
        return False

    print("\n" + "="*60)
    print("Weaviate Schema Initialization")
    print("="*60 + "\n")
    
    # Check Weaviate connection
    print("[*] Checking Weaviate connection...")
    if not check_weaviate_health():
        print("[!] ERROR: Weaviate is not available or not healthy")
        print("[!] Make sure Weaviate is running:")
        print("    docker-compose up -d weaviate")
        return False
    
    client = get_weaviate_client()
    if client is None:
        print("[!] ERROR: Failed to connect to Weaviate")
        return False
    
    print("[OK] Weaviate connection successful\n")
    
    if args.recreate_only:
        name = args.recreate_only
        print(f"[*] Recreating single collection: {name} (existing data will be lost)\n")
        success = create_collection(name, recreate=True)
        if not success:
            print(f"\n[!] Failed to recreate {name}. Check logs above.")
            try:
                client.close()
            except Exception:
                pass
            return False
        source_hint = {"Blogs": "blog", "SharePointDocs": "sharepoint", "JiraTickets": "jira", "Transcripts": "transcript", "Spreadsheets": "excel", "EmailThreads": "email"}.get(name, "<source>")
        print(f"\n[OK] {name} recreated successfully. Re-ingest with: python scripts/ingest_to_weaviate.py --source {source_hint}")
        try:
            client.close()
        except Exception:
            pass
        return True
    
    # Show what collections will be created
    print(f"[*] Will create {len(COLLECTIONS)} collections:")
    for coll in COLLECTIONS:
        print(f"    - {coll}")
    if args.recreate:
        print("\n[!] --recreate: existing collections will be deleted and recreated (all data lost).")
    print()
    
    # Create all collections
    print("[*] Creating Weaviate collections...")
    success = create_all_collections(recreate=args.recreate)
    
    if success:
        print("\n[OK] All collections created successfully!")
        print("\nCollections created:")
        from app.weaviate_schema import list_collections
        collections = list_collections()
        for coll in collections:
            print(f"  - {coll}")
        
        # Close connection after listing (optional - client will auto-reconnect if needed)
        try:
            client.close()
        except Exception:
            pass
        
        return True
    else:
        print("\n[!] Some collections failed to create. Check logs above.")
        # Close connection on failure too
        try:
            client.close()
        except Exception:
            pass
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
