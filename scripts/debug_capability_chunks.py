"""
Debug how capability/limitation chunks are created.

Builds the same documents as the ingest script (from SharePoint or local paths)
and prints each chunk: metadata + page_content (truncated or full) so you can
see exactly how chunks are created.

Usage:
  Same env as ingest (ENABLE_CAPABILITY_FROM_SHAREPOINT or local paths).
  python scripts/debug_capability_chunks.py
  python scripts/debug_capability_chunks.py --full              # print full page_content
  python scripts/debug_capability_chunks.py --limit 5          # only first 5 chunks per source type
  python scripts/debug_capability_chunks.py --output chunks.json  # write all chunks to JSON
"""

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def main():
    parser = argparse.ArgumentParser(description="Debug capability/limitation chunk creation")
    parser.add_argument("content_excel", nargs="?", default=os.getenv("CONTENT_MIGRATION_EXCEL_PATH", ""))
    parser.add_argument("message_excel", nargs="?", default=os.getenv("MESSAGE_LIMITATIONS_EXCEL_PATH", ""))
    parser.add_argument("--full", action="store_true", help="Print full page_content (no truncation)")
    parser.add_argument("--limit", type=int, default=None, help="Max chunks to print per source_type (default: all)")
    parser.add_argument("--output", type=str, default=None, help="Write all chunks to JSON file")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def resolve_path(p):
        if not p:
            return p
        p = p.strip()
        if not os.path.isabs(p):
            p = os.path.normpath(os.path.join(project_root, p))
        return p

    content_path = resolve_path(args.content_excel or "")
    message_path = resolve_path(args.message_excel or "")

    from app.capability_limitations_ingest import (
        get_capability_limitation_documents,
        get_capability_limitation_documents_from_sharepoint,
    )
    from config import ENABLE_CAPABILITY_FROM_SHAREPOINT

    if ENABLE_CAPABILITY_FROM_SHAREPOINT:
        print("[debug] ENABLE_CAPABILITY_FROM_SHAREPOINT=true: reading from SharePoint...")
        documents = get_capability_limitation_documents_from_sharepoint()
    else:
        if not content_path and not message_path:
            print("Set ENABLE_CAPABILITY_FROM_SHAREPOINT=true or provide Excel paths.")
            sys.exit(1)
        documents = get_capability_limitation_documents(
            content_excel_path=content_path or None,
            message_excel_path=message_path or None,
        )

    if not documents:
        print("No documents (chunks) produced. Check paths or SharePoint.")
        sys.exit(0)

    # Summary by source_type
    by_type = {}
    for d in documents:
        t = d.metadata.get("source_type", "unknown")
        by_type[t] = by_type.get(t, 0) + 1
    print("\n" + "=" * 60)
    print("CHUNK SUMMARY")
    print("=" * 60)
    print(f"Total chunks: {len(documents)}")
    for t, count in sorted(by_type.items()):
        print(f"  {t}: {count}")

    truncate = 400 if not args.full else None
    limit = args.limit

    print("\n" + "=" * 60)
    print("CHUNKS (metadata + content)")
    print("=" * 60)

    current_type = None
    type_count = 0
    for i, doc in enumerate(documents):
        st = doc.metadata.get("source_type", "unknown")
        if st != current_type:
            current_type = st
            type_count = 0
        if limit is not None and type_count >= limit:
            if type_count == limit:
                print(f"\n  ... ({by_type.get(st, 0) - limit} more chunks of source_type={st})\n")
            continue
        type_count += 1

        content = doc.page_content or ""
        if truncate and len(content) > truncate:
            content_preview = content[:truncate] + "\n... [truncated]"
        else:
            content_preview = content

        print(f"\n--- Chunk {i + 1} (source_type={st}) ---")
        print("Metadata:", {k: v for k, v in doc.metadata.items() if v is not None})
        print("Content:")
        print(content_preview)

    if args.output:
        out_path = os.path.join(project_root, args.output) if not os.path.isabs(args.output) else args.output
        payload = [
            {"index": i + 1, "metadata": dict(doc.metadata), "page_content": doc.page_content or ""}
            for i, doc in enumerate(documents)
        ]
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"\n[debug] Wrote {len(documents)} chunks to {out_path}")


if __name__ == "__main__":
    main()
