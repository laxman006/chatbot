"""
Delete all Weaviate chunks for a single SharePoint document by doc_id.

Use this to remove one file's chunks so you can re-ingest it (e.g. after fixing
migration_type resolution) without touching other documents.

Run from repo root:
  python scripts/delete_sharepoint_doc_chunks.py
  python scripts/delete_sharepoint_doc_chunks.py --doc-id sharepoint:01PK5PNWOEADXOEDR5TREICKCXHGFQDFO5
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.weaviate_batch_inserter import WeaviateBatchInserter
from app.weaviate_client import reset_weaviate_client

# Default: Limitations and features.xlsx (Repository25)
DEFAULT_DOC_ID = "sharepoint:01PK5PNWOEADXOEDR5TREICKCXHGFQDFO5"
COLLECTION = "SharePointDocs"


def main():
    parser = argparse.ArgumentParser(
        description="Delete all Weaviate chunks for a SharePoint document by doc_id"
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        default=DEFAULT_DOC_ID,
        help=f"Document ID (default: {DEFAULT_DOC_ID})",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=COLLECTION,
        help=f"Weaviate collection name (default: {COLLECTION})",
    )
    args = parser.parse_args()

    print(f"Deleting chunks for doc_id={args.doc_id!r} in collection '{args.collection}'...")
    try:
        inserter = WeaviateBatchInserter()
        ok = inserter.delete_chunks_by_doc_id(args.collection, args.doc_id)
        if ok:
            print("Done.")
        else:
            print("Delete failed (check logs).", file=sys.stderr)
            sys.exit(1)
    finally:
        reset_weaviate_client()


if __name__ == "__main__":
    main()
