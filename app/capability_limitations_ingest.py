"""
Capability and limitations document builder for the dedicated ChromaDB.

- Defines CHROMA_CAPABILITIES_DB_PATH (separate from main ChromaDB).
- Builds List[Document] from content Excel + message/limitations Excel (no Chroma here).
- When ENABLE_CAPABILITY_FROM_SHAREPOINT=true, reads the two Excels directly from SharePoint (stream to temp, chunk, no local copy).
- Ingest script uses this to populate the capabilities ChromaDB only.
"""

import os
import tempfile
from typing import List, Optional
from langchain_core.documents import Document

# Dedicated ChromaDB for migration capabilities/limitations (do not merge into main DB)
CHROMA_CAPABILITIES_DB_PATH = os.getenv("CHROMA_CAPABILITIES_DB_PATH", "./data/chroma_capabilities_db")


def get_capability_limitation_documents_from_sharepoint() -> List[Document]:
    """
    Fetch the two capability Excel files from SharePoint (Repository25), chunk them, and return Documents.
    No local download: streams file content to a temp file, runs extractors, then deletes temp file.
    Uses SHAREPOINT_LIMITATIONS_SITE_URL and SHAREPOINT_LIMITATIONS_FOLDER_PATH from config.
    """
    from urllib.parse import urlparse
    import requests
    from app.sharepoint_graph_extractor import SharePointGraphExtractor
    from app.sharepoint_auth import sharepoint_auth
    from app.helpers import find_folder_by_path_helper
    from config import SHAREPOINT_LIMITATIONS_SITE_URL, SHAREPOINT_LIMITATIONS_FOLDER_PATH
    from app.content_migration_extractor import extract_content_migration_documents
    from app.message_limitations_extractor import extract_message_limitations_documents

    documents: List[Document] = []

    parsed = urlparse(SHAREPOINT_LIMITATIONS_SITE_URL)
    path_parts = [p for p in parsed.path.split("/") if p]
    clean_site_url = SHAREPOINT_LIMITATIONS_SITE_URL
    if "sites" in path_parts and path_parts.index("sites") + 1 < len(path_parts):
        clean_site_url = f"{parsed.scheme}://{parsed.netloc}/sites/{path_parts[path_parts.index('sites') + 1]}"

    extractor = SharePointGraphExtractor()
    extractor.site_url = clean_site_url
    extractor.site_id = None
    extractor.drive_id = None

    drive_id = extractor.get_drive_id()
    if not drive_id:
        print("[capability_limitations_ingest] SharePoint: failed to get drive ID")
        return []

    folder_id = find_folder_by_path_helper(extractor, drive_id, SHAREPOINT_LIMITATIONS_FOLDER_PATH)
    if not folder_id:
        print(f"[capability_limitations_ingest] SharePoint: folder not found: {SHAREPOINT_LIMITATIONS_FOLDER_PATH}")
        return []

    graph_url = f"{extractor.graph_base_url}/drives/{drive_id}/items/{folder_id}/children"
    headers = sharepoint_auth.get_headers()
    resp = requests.get(graph_url, headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"[capability_limitations_ingest] SharePoint: list folder failed: {resp.status_code}")
        return []

    items = resp.json().get("value", [])
    content_item = None
    message_item = None
    for item in items:
        if "folder" in item:
            continue
        name = item.get("name", "")
        if "Common_Features_In_Content_Migrations2" in name and name.lower().endswith((".xlsx", ".xls")):
            content_item = item
        if "Limitations and features" in name and name.lower().endswith((".xlsx", ".xls")):
            message_item = item

    def download_to_temp(item_id: str, file_name: str) -> Optional[str]:
        url = f"{extractor.graph_base_url}/drives/{drive_id}/items/{item_id}/content"
        r = requests.get(url, headers=headers, timeout=60, stream=True)
        if r.status_code != 200:
            return None
        suffix = ".xlsx" if file_name.lower().endswith(".xlsx") else ".xls"
        f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        try:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
            path = f.name
        finally:
            f.close()
        return path

    if content_item:
        tmp = download_to_temp(content_item["id"], content_item["name"])
        if tmp:
            try:
                content_docs = extract_content_migration_documents(tmp, display_file_name=content_item["name"])
                documents.extend(content_docs)
                print(f"[capability_limitations_ingest] SharePoint content Excel: {len(content_docs)} docs")
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        else:
            print("[capability_limitations_ingest] SharePoint: failed to download content Excel")
    else:
        print("[capability_limitations_ingest] SharePoint: content Excel not found in folder")

    if message_item:
        tmp = download_to_temp(message_item["id"], message_item["name"])
        if tmp:
            try:
                message_docs = extract_message_limitations_documents(tmp, display_file_name=message_item["name"])
                documents.extend(message_docs)
                print(f"[capability_limitations_ingest] SharePoint message/limitations Excel: {len(message_docs)} docs")
            finally:
                try:
                    os.unlink(tmp)
                except Exception:
                    pass
        else:
            print("[capability_limitations_ingest] SharePoint: failed to download message Excel")
    else:
        print("[capability_limitations_ingest] SharePoint: message Excel not found in folder")

    print(f"[capability_limitations_ingest] Total documents from SharePoint: {len(documents)}")
    return documents


def get_capability_limitation_documents(
    content_excel_path: Optional[str] = None,
    message_excel_path: Optional[str] = None,
    content_display_name: Optional[str] = None,
    message_display_name: Optional[str] = None,
) -> List[Document]:
    """
    Build all capability/limitation documents from the two Excels.

    Args:
        content_excel_path: Path to content Excel (Common_Features_In_Content_Migrations2).
        message_excel_path: Path to message/limitations Excel (Limitations and features.xlsx).
        content_display_name: Optional display name for content file.
        message_display_name: Optional display name for message file.

    Returns:
        Combined List[Document] for ingestion into the capabilities ChromaDB.
    """
    from app.content_migration_extractor import extract_content_migration_documents
    from app.message_limitations_extractor import extract_message_limitations_documents

    documents: List[Document] = []

    if content_excel_path and os.path.isfile(content_excel_path):
        print(f"[capability_limitations_ingest] Extracting content Excel: {content_excel_path}")
        content_docs = extract_content_migration_documents(
            content_excel_path,
            display_file_name=content_display_name or os.path.basename(content_excel_path),
        )
        documents.extend(content_docs)
        print(f"[capability_limitations_ingest] Content migration docs: {len(content_docs)}")
    else:
        if content_excel_path:
            print(f"[capability_limitations_ingest] Content Excel not found: {content_excel_path}")

    if message_excel_path and os.path.isfile(message_excel_path):
        print(f"[capability_limitations_ingest] Extracting message/limitations Excel: {message_excel_path}")
        message_docs = extract_message_limitations_documents(
            message_excel_path,
            display_file_name=message_display_name or os.path.basename(message_excel_path),
        )
        documents.extend(message_docs)
        print(f"[capability_limitations_ingest] Message/limitations docs: {len(message_docs)}")
    else:
        if message_excel_path:
            print(f"[capability_limitations_ingest] Message Excel not found: {message_excel_path}")

    print(f"[capability_limitations_ingest] Total documents: {len(documents)}")
    return documents
