"""
Delete all SharePoint Presales chunks from Weaviate (SharePointDocs collection).

Presales chunks are identified by parent_key containing "Pre-SalesTrining"
(the Presales Training site path). Other SharePoint scopes (DOC360, Limitations)
are not touched.

Use this when you need to clear Presales ingestion and re-ingest (e.g. after
fixing chunking or metadata).

Run from repo root:
  python scripts/delete_sharepoint_presales_chunks.py

Then re-ingest Presales:
  python scripts/ingest_to_weaviate.py --source sharepoint
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.weaviate_batch_inserter import WeaviateBatchInserter
from app.weaviate_client import reset_weaviate_client

# Parent_key for Presales contains this (from Presales Training site path)
PRESALES_PARENT_KEY_SUBSTRING = "Pre-SalesTrining"
COLLECTION = "SharePointDocs"


def main():
    parser = argparse.ArgumentParser(
        description="Delete all SharePoint Presales chunks from Weaviate (parent_key contains Pre-SalesTrining)"
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=COLLECTION,
        help=f"Weaviate collection name (default: {COLLECTION})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print what would be deleted; do not delete",
    )
    args = parser.parse_args()

    if args.dry_run:
        print(f"[DRY RUN] Would delete chunks where parent_key contains {PRESALES_PARENT_KEY_SUBSTRING!r}")
        print(f"[DRY RUN] Collection: {args.collection}")
        print("[DRY RUN] Run without --dry-run to perform deletion.")
        return 0

    print(f"Deleting SharePoint Presales chunks (parent_key contains {PRESALES_PARENT_KEY_SUBSTRING!r})...")
    print(f"Collection: {args.collection}")
    try:
        inserter = WeaviateBatchInserter()
        ok = inserter.delete_chunks_by_parent_key_contains(
            args.collection,
            PRESALES_PARENT_KEY_SUBSTRING,
        )
        if ok:
            print("Done. Presales chunks removed from Weaviate.")
            print("Re-ingest with: python scripts/ingest_to_weaviate.py --source sharepoint")
        else:
            print("Delete failed (check logs).", file=sys.stderr)
            return 1
    finally:
        reset_weaviate_client()

    return 0


if __name__ == "__main__":
    sys.exit(main())
