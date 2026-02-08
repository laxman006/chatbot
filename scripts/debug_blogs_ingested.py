"""
Debug script: report how many blogs are in Weaviate and which ones.

Run from repo root:
  python scripts/debug_blogs_ingested.py
  python scripts/debug_blogs_ingested.py --doc-id minimizing-api-throttling-risk-during-cloud-office-migration

Output includes created_at (or publish_date/post_date fallback) per blog.
Weaviate rejects fetch_objects(limit=very_large); this script uses cursor-based
pagination so it stays under the server's max-results cap.
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


def _date_str(props: dict, *keys: str) -> str:
    """First non-empty date from props for given keys (e.g. created_at, publish_date, post_date)."""
    for k in keys:
        v = props.get(k)
        if v is not None and str(v).strip():
            s = str(v).strip()
            return s[:10] if len(s) >= 10 else s  # YYYY-MM-DD or shorter
    return "-"


def _fetch_all_objects_paginated(coll, *, page_size: int = 100, max_objects: int = 50_000):
    """
    Fetch all objects using cursor-based pagination to avoid "query maximum results exceeded".
    Yields objects; stops when no more results or max_objects reached.
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
    """
    Verify that a specific blog exists by doc_id (slug). Uses filtered fetch;
    prints chunk count and sample url. Returns True if at least one chunk found.
    """
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
            url = (props.get("url") or props.get("post_url") or "")[:70]
            created = _date_str(props, "created_at", "publish_date", "post_date")
            print(f"  Sample {i}: created_at={created}  url={url!r}")
        if len(objects) > 3:
            print(f"  ... and {len(objects) - 3} more chunks")
        return True
    print("  (none)")
    return False


def debug_blogs_ingested(
    *,
    page_size: int = 100,
    max_objects: int = 50_000,
    doc_id_filter: str | None = None,
) -> bool:
    """
    Query Weaviate Blogs collection and print counts + list of ingested blogs.
    Uses cursor-based pagination to avoid Weaviate's "query maximum results exceeded" error.

    Args:
        page_size: Objects per request (keep ≤100–200 to stay under server cap).
        max_objects: Stop after this many objects (safety cap).
        doc_id_filter: If set, only run the "check this doc_id" snippet and exit.

    Returns:
        True if run completed, False if Weaviate unavailable or no Blogs collection.
    """
    print("=" * 70)
    print("BLOGS IN WEAVIATE – DEBUG")
    print("=" * 70)

    client = get_weaviate_client()
    if client is None:
        print("[ERROR] Weaviate client unavailable. Is Weaviate running?")
        return False

    try:
        if not client.collections.exists("Blogs"):
            print("[WARNING] Collection 'Blogs' does not exist.")
            return False

        coll = client.collections.get("Blogs")

        if doc_id_filter:
            print("\nCheck by doc_id (slug):")
            print("-" * 70)
            found = check_doc_id(coll, doc_id_filter)
            print("-" * 70)
            return found  # exit 1 if no chunks for this slug

        # Total count via aggregate if available
        total_chunks = None
        try:
            agg = coll.aggregate.over_all(total_count=True)
            if hasattr(agg, "total_count") and agg.total_count is not None:
                total_chunks = int(agg.total_count)
        except Exception:
            pass

        # Fetch objects in pages to avoid "query maximum results exceeded"
        objects = []
        for obj in _fetch_all_objects_paginated(coll, page_size=page_size, max_objects=max_objects):
            objects.append(obj)

        if total_chunks is None:
            total_chunks = len(objects)
        if len(objects) >= max_objects:
            print(f"[INFO] Stopped at {max_objects} objects (safety cap). Total in DB may be higher.")

        # Group by doc_id
        by_doc: dict[str, dict] = {}
        for obj in objects:
            props = _props(obj)
            doc_id = (props.get("doc_id") or props.get("post_slug") or "").strip() or "(empty)"
            if doc_id not in by_doc:
                by_doc[doc_id] = {
                    "doc_id": doc_id,
                    "title": (props.get("title") or props.get("post_title") or "")[:80],
                    "url": (props.get("url") or props.get("post_url") or "")[:100],
                    "created_at": _date_str(props, "created_at", "publish_date", "post_date"),
                    "chunk_count": 0,
                }
            by_doc[doc_id]["chunk_count"] += 1

        unique_blogs = len(by_doc)

        print()
        print("SUMMARY")
        print("-" * 70)
        print(f"  Total chunks in Blogs:  {total_chunks}")
        print(f"  Unique blogs (doc_id): {unique_blogs}")
        print()

        if not by_doc:
            print("  No blog objects found.")
            return True

        # Sort by created_at desc (newest first), then doc_id. Missing dates sort last.
        rows = sorted(
            by_doc.values(),
            key=lambda r: (r.get("created_at") or "-", r["doc_id"]),
            reverse=True,
        )

        print("BLOGS (doc_id | created_at | title | url | chunks)")
        print("-" * 70)
        for r in rows:
            doc_id = (r["doc_id"] or "")[:38]
            created = r.get("created_at", "-")
            title = (r["title"] or "-")[:40]
            url = (r["url"] or "-")[:48]
            n = r["chunk_count"]
            print(f"  {doc_id:38} | {created:10} | {title:40} | {url:48} | {n:5}")
        print("-" * 70)
        return True

    finally:
        try:
            client.close()
        except Exception:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Debug: list blogs in Weaviate (paginated). Optionally check one doc_id."
    )
    parser.add_argument(
        "--doc-id",
        type=str,
        metavar="SLUG",
        help="Check that this blog slug exists; print chunk count and sample url.",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=100,
        help="Objects per request (default 100; keep modest to avoid Weaviate cap).",
    )
    parser.add_argument(
        "--max-objects",
        type=int,
        default=50_000,
        help="Stop after this many objects when listing all (default 50_000).",
    )
    args = parser.parse_args()

    ok = debug_blogs_ingested(
        page_size=args.page_size,
        max_objects=args.max_objects,
        doc_id_filter=args.doc_id,
    )
    sys.exit(0 if ok else 1)
