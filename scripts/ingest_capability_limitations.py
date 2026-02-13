"""
Ingest migration capability and limitations documents into the DEDICATED ChromaDB only.

- Does NOT merge into the main ChromaDB (CHROMA_DB_PATH).
- Populates only CHROMA_CAPABILITIES_DB_PATH (./data/chroma_capabilities_db by default).

  When ENABLE_CAPABILITY_FROM_SHAREPOINT=true: reads the two Excel files directly from
  SharePoint (Repository25 / Neutara Labs/Limitations and features), chunks them, and
  ingests into the capabilities DB (no local download).

Usage:
  Set ENABLE_CAPABILITY_FROM_SHAREPOINT=true in .env to read from SharePoint.
  Or set local paths:
    CONTENT_MIGRATION_EXCEL_PATH  - path to Common_Features_In_Content_Migrations2.xlsx
    MESSAGE_LIMITATIONS_EXCEL_PATH - path to Limitations and features.xlsx
  Or pass as CLI args:
    python scripts/ingest_capability_limitations.py <content_excel> <message_excel>

  Example:
    python scripts/ingest_capability_limitations.py ./excel/Common_Features_In_Content_Migrations2.xlsx ./excel/Limitations_and_features.xlsx
"""

import os
import sys
import argparse

# Add project root so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env from project root so CONTENT_MIGRATION_EXCEL_PATH etc. are set
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))


def main():
    parser = argparse.ArgumentParser(description="Ingest capability/limitation Excels into dedicated ChromaDB")
    parser.add_argument(
        "content_excel",
        nargs="?",
        default=os.getenv("CONTENT_MIGRATION_EXCEL_PATH", ""),
        help="Path to content Excel (Common_Features_In_Content_Migrations2.xlsx)",
    )
    parser.add_argument(
        "message_excel",
        nargs="?",
        default=os.getenv("MESSAGE_LIMITATIONS_EXCEL_PATH", ""),
        help="Path to message/limitations Excel (Limitations and features.xlsx)",
    )
    parser.add_argument(
        "--db",
        default=os.getenv("CHROMA_CAPABILITIES_DB_PATH", ""),
        help="ChromaDB path (default: ./data/chroma_capabilities_db)",
    )
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def resolve_path(p: str):
        if not p:
            return p
        p = p.strip()
        # Resolve relative paths against project root so .env paths like ./excel/file.xlsx work
        if not os.path.isabs(p):
            p = os.path.normpath(os.path.join(project_root, p))
        return p

    content_path = resolve_path(args.content_excel or "")
    message_path = resolve_path(args.message_excel or "")
    db_path = (args.db or "").strip() or "./data/chroma_capabilities_db"
    if db_path and not os.path.isabs(db_path) and (db_path.startswith("./") or db_path.startswith(".\\")):
        db_path = os.path.normpath(os.path.join(project_root, db_path))

    from app.capability_limitations_ingest import (
        get_capability_limitation_documents,
        get_capability_limitation_documents_from_sharepoint,
        CHROMA_CAPABILITIES_DB_PATH,
    )
    from langchain_openai import OpenAIEmbeddings
    from langchain_chroma import Chroma

    use_db = db_path if db_path else CHROMA_CAPABILITIES_DB_PATH
    os.makedirs(os.path.dirname(use_db) or ".", exist_ok=True)

    # When enabled, read directly from SharePoint (no local download)
    from config import ENABLE_CAPABILITY_FROM_SHAREPOINT
    if ENABLE_CAPABILITY_FROM_SHAREPOINT:
        print("[ingest] ENABLE_CAPABILITY_FROM_SHAREPOINT=true: reading from SharePoint...")
        documents = get_capability_limitation_documents_from_sharepoint()
    else:
        if not content_path and not message_path:
            print("Provide at least one Excel path via CONTENT_MIGRATION_EXCEL_PATH / MESSAGE_LIMITATIONS_EXCEL_PATH or as positional args. Or set ENABLE_CAPABILITY_FROM_SHAREPOINT=true to read from SharePoint.")
            sys.exit(1)
        documents = get_capability_limitation_documents(
            content_excel_path=content_path or None,
            message_excel_path=message_path or None,
        )

    if not documents:
        print("No documents to ingest. Check Excel paths or SharePoint folder (SHAREPOINT_LIMITATIONS_FOLDER_PATH).")
        if not ENABLE_CAPABILITY_FROM_SHAREPOINT:
            print(f"  Content Excel (expected): {content_path or '(not set)'}")
            print(f"  Message Excel (expected): {message_path or '(not set)'}")
            print("  Or set ENABLE_CAPABILITY_FROM_SHAREPOINT=true to read from SharePoint.")
        sys.exit(0)

    print(f"[ingest] Creating dedicated ChromaDB at: {use_db}")
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    vectorstore = Chroma.from_documents(
        documents,
        embeddings,
        persist_directory=use_db,
        collection_metadata={"hnsw:space": "cosine"},
    )
    # Chroma with persist_directory auto-persists; no .persist() in newer langchain-chroma
    count = vectorstore._collection.count()
    print(f"[ingest] Done. Capabilities ChromaDB has {count} documents at {use_db}")


if __name__ == "__main__":
    main()
