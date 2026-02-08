"""
Debug script: report how many SharePoint documents are in Weaviate and list them.

Run from repo root:
  python scripts/debug_sharepoint_ingested.py
  python scripts/debug_sharepoint_ingested.py --doc-id "https://..../file.pdf"

Uses cursor-based pagination like debug_blogs_ingested.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.weaviate_client import get_weaviate_client


def _props(obj) -> dict:
    """Safe read of object properties."""
    p = getattr(obj, "properties", None)
    if p is None:
        return {}
    return dict(p) if hasattr(p, "items") else {}


def _fetch_all_objects_paginated(coll, *, page_size: int = 100, max_objects: int = 50_000):
    """
    Fetch all objects using cursor-based pagination to avoid "query maximum results exceeded".
    """
    cursor = None
    total = 0
    while total < max_objects:
        kwargs = {"limit": page_size}
        if cursor is not None:
            kwargs["after"] = cursor
        result = coll.query.fetch_objects(**kwargs)
        objects = list(getattr(result, "objects", []) or [])
        if not objects:
            break
        for obj in objects:
            yield obj
            total += 1
            if total >= max_objects:
                return
        cursor = getattr(objects[-1], "uuid", None)
        if cursor is None:
            break


def check_doc_id(coll, doc_id: str) -> bool:
    """Check that a specific SharePoint doc exists by doc_id; print chunk count and sample."""
    from weaviate.classes.query import Filter

    result = coll.query.fetch_objects(
        limit=500,
        filters=Filter.by_property("doc_id").equal(doc_id),
    )
    objects = list(getattr(result, "objects", []) or [])
    print(f"  doc_id filter: {doc_id!r}")
    print(f"  Chunks found:  {len(objects)}")
    if objects:
        for i, obj in enumerate(objects[:3], 1):
            props = _props(obj)
            title = (props.get("title") or props.get("source_ref") or "")[:60]
            url = (props.get("url") or "")[:70]
            site = (props.get("site_name") or "")[:30]
            folder = (props.get("folder_name") or "")[:40]
            print(f"  Sample {i}: title={title!r} site={site!r} folder={folder!r} url={url!r}")
        if len(objects) > 3:
            print(f"  ... and {len(objects) - 3} more chunks")
        return True
    print("  (none)")
    return False


def debug_sharepoint_ingested(
    *,
    page_size: int = 100,
    max_objects: int = 50_000,
    doc_id_filter: str | None = None,
) -> bool:
    """
    Query Weaviate SharePointDocs collection and print counts + list of ingested documents.
    """
    print("=" * 70)
    print("SHAREPOINT DOCS IN WEAVIATE – DEBUG")
    print("=" * 70)

    client = get_weaviate_client()
    if client is None:
        print("[ERROR] Weaviate client unavailable. Is Weaviate running?")
        return False

    try:
        if not client.collections.exists("SharePointDocs"):
            print("[WARNING] Collection 'SharePointDocs' does not exist.")
            return False

        coll = client.collections.get("SharePointDocs")

        if doc_id_filter:
            print("\nCheck by doc_id:")
            print("-" * 70)
            found = check_doc_id(coll, doc_id_filter)
            print("-" * 70)
            return found

        # Total count via aggregate if available
        total_chunks = None
        try:
            agg = coll.aggregate.over_all(total_count=True)
            if hasattr(agg, "total_count") and agg.total_count is not None:
                total_chunks = int(agg.total_count)
        except Exception:
            pass

        objects = []
        for obj in _fetch_all_objects_paginated(coll, page_size=page_size, max_objects=max_objects):
            objects.append(obj)

        if total_chunks is None:
            total_chunks = len(objects)
        if len(objects) >= max_objects:
            print(f"[INFO] Stopped at {max_objects} objects (safety cap). Total in DB may be higher.")

        # Group by doc_id (SharePoint doc_id is often file URL or url#key)
        by_doc: dict[str, dict] = {}
        for obj in objects:
            props = _props(obj)
            doc_id = (props.get("doc_id") or props.get("source_ref") or "").strip() or "(empty)"
            if doc_id not in by_doc:
                by_doc[doc_id] = {
                    "doc_id": doc_id,
                    "title": (props.get("title") or props.get("source_ref") or "")[:80],
                    "url": (props.get("url") or "")[:100],
                    "site_name": (props.get("site_name") or "")[:50],
                    "folder_name": (props.get("folder_name") or "")[:50],
                    "chunk_count": 0,
                }
            by_doc[doc_id]["chunk_count"] += 1

        unique_docs = len(by_doc)

        print()
        print("SUMMARY")
        print("-" * 70)
        print(f"  Total chunks in SharePointDocs:  {total_chunks}")
        print(f"  Unique documents (by doc_id):    {unique_docs}")
        print()

        if not by_doc:
            print("  No SharePoint documents found.")
            return True

        # Sort by doc_id for stable output
        rows = sorted(by_doc.values(), key=lambda r: (r["doc_id"],))

        print("SHAREPOINT DOCUMENTS (doc_id | title | site_name | folder_name | url | chunks)")
        print("-" * 70)
        for r in rows:
            doc_id = (r["doc_id"] or "")[:45]
            title = (r["title"] or "-")[:35]
            site = (r["site_name"] or "-")[:25]
            folder = (r["folder_name"] or "-")[:30]
            url = (r["url"] or "-")[:50]
            n = r["chunk_count"]
            print(f"  {doc_id:45} | {title:35} | {site:25} | {folder:30} | {url:50} | {n:5}")
        print("-" * 70)
        return True

    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Debug: list SharePoint documents in Weaviate (paginated). Optionally check one doc_id."
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        metavar="DOC_ID",
        help="Check that this doc_id exists; print chunk count and sample.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Objects per request (default 100).",
    )
    parser.add_argument(
        "--max-objects",
        type=int,
        default=50_000,
        help="Stop after this many objects when listing all (default 50_000).",
    )
    args = parser.parse_args()

    ok = debug_sharepoint_ingested(
        page_size=args.page_size,
        max_objects=args.max_objects,
        doc_id_filter=args.doc_id,
    )
    sys.exit(0 if ok else 1)
