"""
Clean, production-grade Weaviate v4 schema definitions for a Branching RAG Knowledge Base.

✅ Goals:
- Source-based collections (NOT file-type collections)
- Universal Parent-Document Retrieval fields everywhere
- RBAC-ready metadata (permissions filters)
- Incremental ingestion support (doc_id, version, last_indexed_at)
- Summary chunk support (chunk_role)
- Weaviate v4 client.collections API only (no mixed schema styles)

Recommended Collections:
- SharePointDocs  (pdf/doc/docx/md/html from SharePoint)
- Blogs           (internal blogs/wiki posts)
- JiraTickets     (Jira issues/tickets)
- Transcripts     (VTT/SRT/demo call transcripts)
- Spreadsheets    (Excel files/sheets/rows from SharePoint)
- EmailThreads    (email threads/conversations)

Author: RAG Platform Migration
"""

from __future__ import annotations

import logging
from typing import List, Optional, Dict, Any

from weaviate.classes.config import Property, DataType, VectorDistances, Configure
from app.weaviate_client import get_weaviate_client

logger = logging.getLogger(__name__)

# ==========================
# 1) Collection Names
# ==========================
COLLECTIONS = [
    "SharePointDocs",
    "Blogs",
    "JiraTickets",
    "Transcripts",
    "Spreadsheets",
    "EmailThreads",
]

# Mapping from collection name to source_type (for consistency)
COLLECTION_TO_SOURCE_TYPE = {
    "SharePointDocs": "sharepoint",
    "Blogs": "blog",
    "JiraTickets": "jira",
    "Transcripts": "transcript",
    "Spreadsheets": "excel",
    "EmailThreads": "email",
}


def get_source_type_for_collection(collection_name: str) -> str:
    """
    Get the correct source_type for a collection name.
    
    Ensures consistency: SharePointDocs → "sharepoint", Blogs → "blog", etc.
    
    Args:
        collection_name: Collection name (e.g., "SharePointDocs", "Blogs")
    
    Returns:
        Corresponding source_type string
    
    Raises:
        ValueError: If collection_name is not recognized
    """
    if collection_name not in COLLECTION_TO_SOURCE_TYPE:
        raise ValueError(
            f"Unknown collection: '{collection_name}'. Valid collections: {list(COLLECTION_TO_SOURCE_TYPE.keys())}"
        )
    return COLLECTION_TO_SOURCE_TYPE[collection_name]


# ==========================
# 1.5) Chunk Role Constants (Standardized)
# ==========================
# Standardized chunk_role values for consistent retrieval
CHUNK_ROLE_CONTENT = "content"
CHUNK_ROLE_DOC_SUMMARY = "doc_summary"
CHUNK_ROLE_SHEET_SUMMARY = "sheet_summary"
CHUNK_ROLE_TICKET_SUMMARY = "ticket_summary"
CHUNK_ROLE_THREAD_SUMMARY = "thread_summary"
CHUNK_ROLE_MESSAGE_SUMMARY = "message_summary"
CHUNK_ROLE_MEETING_SUMMARY = "meeting_summary"
CHUNK_ROLE_DECISIONS_SUMMARY = "decisions_summary"
CHUNK_ROLE_ACTION_ITEMS_SUMMARY = "action_items_summary"

# All valid chunk roles
VALID_CHUNK_ROLES = [
    CHUNK_ROLE_CONTENT,
    CHUNK_ROLE_DOC_SUMMARY,
    CHUNK_ROLE_SHEET_SUMMARY,
    CHUNK_ROLE_TICKET_SUMMARY,
    CHUNK_ROLE_THREAD_SUMMARY,
    CHUNK_ROLE_MESSAGE_SUMMARY,
    CHUNK_ROLE_MEETING_SUMMARY,
    CHUNK_ROLE_DECISIONS_SUMMARY,
    CHUNK_ROLE_ACTION_ITEMS_SUMMARY,
]


def validate_chunk_role(chunk_role: str) -> bool:
    """
    Validate that chunk_role is in VALID_CHUNK_ROLES.
    
    Args:
        chunk_role: Chunk role to validate
    
    Returns:
        True if valid, False otherwise
    
    Raises:
        ValueError: If chunk_role is not in VALID_CHUNK_ROLES (for strict validation)
    """
    if chunk_role not in VALID_CHUNK_ROLES:
        raise ValueError(
            f"Invalid chunk_role: '{chunk_role}'. Must be one of: {VALID_CHUNK_ROLES}"
        )
    return True


# ==========================
# 2) Universal Properties
# ==========================
# NOTE:
# - "content" is the chunk text that gets embedded externally
# - "permissions" enables RBAC filtering at retrieval time
# - "parent_id" + "chunk_id" enables Parent-Doc expansion (neighbors)
# - "chunk_role" enables summary chunks (doc_summary/sheet_summary/ticket_summary)
#
# FILTERABLE FIELDS (for fast Parent-Doc retrieval):
# These fields are kept short/structured for efficient filtering:
# - parent_id (TEXT, stable UUID)
# - chunk_id (INT, 0..N or -1 for summaries)
# - permissions (TEXT_ARRAY, RBAC groups)
# - Collection-specific: ticket_key, thread_id, sheet_name (all TEXT, short identifiers)
#
# ⚠️ CRITICAL: Parent-Doc Expansion Logic - chunk_id = -1 Exclusion
# ================================================================
# When fetching neighbor chunks for parent-doc expansion:
#
# Example: Expanding around chunk_id=3 with expand_k=1
#   ✅ CORRECT: Fetch chunk_id IN [2, 3, 4] (exclude -1)
#   ❌ WRONG:   Fetch chunk_id IN [2, 3, 4, -1]
#
# Why: Summary chunks (chunk_id = -1) are not sequential neighbors.
#      They should be fetched separately if needed, not as part of
#      sequential neighbor expansion queries.
#
# Correct Weaviate filter pattern:
#   {
#     "operator": "And",
#     "operands": [
#       {"path": ["parent_id"], "operator": "Equal", "valueText": parent_id},
#       {"path": ["chunk_id"], "operator": "GreaterThanEqual", "valueInt": 0},  # Exclude -1
#       {"path": ["chunk_id"], "operator": "ContainsAny", "valueInt": [2, 3, 4]}
#     ]
#   }
#
# Summary chunks should be fetched separately:
#   {
#     "operator": "And",
#     "operands": [
#       {"path": ["parent_id"], "operator": "Equal", "valueText": parent_id},
#       {"path": ["chunk_id"], "operator": "Equal", "valueInt": -1},
#       {"path": ["chunk_role"], "operator": "Equal", "valueText": "doc_summary"}  # or appropriate role
#     ]
#   }
UNIVERSAL_PROPERTIES: List[Property] = [
    # --- Chunk payload ---
    Property(name="content", data_type=DataType.TEXT, description="Chunk content text"),

    # --- Source and typing ---
    # ⚠️ IMPORTANT: source_type must match collection name for consistency:
    # SharePointDocs → "sharepoint", Blogs → "blog", JiraTickets → "jira",
    # Transcripts → "transcript", Spreadsheets → "excel", EmailThreads → "email"
    Property(
        name="source_type",
        data_type=DataType.TEXT,
        description="Source type: sharepoint|blog|jira|transcript|excel|email (must match collection name)",
    ),
    Property(
        name="source_ref",
        data_type=DataType.TEXT,
        description="Source reference identifier (ticket key, filename, etc.) e.g., 'PROJ-123', 'policy.pdf'",
    ),
    Property(
        name="file_type",
        data_type=DataType.TEXT,
        description="File type: pdf|docx|xlsx|md|html|txt (if applicable)",
    ),

    # --- Parent document identity (Parent-Doc retrieval) ---
    Property(
        name="doc_id",
        data_type=DataType.TEXT,
        description="Stable document ID (SharePoint file id, Jira key, blog slug, transcript id)",
    ),
    Property(
        name="parent_id",
        data_type=DataType.TEXT,
        description="Stable UUID/string for parent document (same across all chunks of a doc)",
    ),
    Property(
        name="parent_key",
        data_type=DataType.TEXT,
        description="Path-like identifier (e.g., 'sharepoint/limitations/policy.pdf')",
    ),

    # --- Chunk identity ---
    Property(
        name="chunk_id",
        data_type=DataType.INT,
        description="Order within parent scope (0..N). Use -1 for summary chunks. "
                    "⚠️ IMPORTANT: When fetching neighbor chunks for parent-doc expansion, "
                    "ALWAYS exclude chunk_id = -1 from neighbor queries. Summary chunks should "
                    "be fetched separately if needed, not as part of sequential neighbor expansion.",
    ),
    Property(
        name="chunk_key",
        data_type=DataType.TEXT,
        description="Globally unique chunk key, e.g., parent_key + '#chunk_' + chunk_id",
    ),
    Property(
        name="chunk_role",
        data_type=DataType.TEXT,
        description="Chunk role: content|doc_summary|sheet_summary|ticket_summary|thread_summary|message_summary|meeting_summary|decisions_summary|action_items_summary. "
                    "⚠️ Must be validated against VALID_CHUNK_ROLES during ingestion.",
    ),

    # --- Document metadata for UX + citations ---
    Property(name="title", data_type=DataType.TEXT, description="Document title"),
    Property(name="url", data_type=DataType.TEXT, description="Document URL / SharePoint link / Jira link"),
    Property(name="created_at", data_type=DataType.DATE, description="Creation date (ISO-8601)"),
    Property(name="updated_at", data_type=DataType.DATE, description="Last update date (ISO-8601)"),

    # --- RBAC / permission filtering ---
    Property(
        name="permissions",
        data_type=DataType.TEXT_ARRAY,
        description="RBAC permission groups e.g. ['eng','admin','sales']",
    ),

    # --- Multi-tenant / organizational structure ---
    Property(
        name="tenant_id",
        data_type=DataType.TEXT,
        description="Org tenant/team identifier for multi-tenant deployments",
    ),
    Property(
        name="department",
        data_type=DataType.TEXT,
        description="Department name for organizational filtering and security boundaries",
    ),

    # --- Ingestion + operations ---
    Property(name="version", data_type=DataType.INT, description="Document version number (increment on change)"),
    Property(name="last_indexed_at", data_type=DataType.DATE, description="When this chunk was last indexed"),
    Property(name="token_count", data_type=DataType.INT, description="Token count for this chunk"),
]

# ==========================
# 3) Collection-Specific Properties
# ==========================

BLOG_PROPERTIES: List[Property] = [
    Property(name="author", data_type=DataType.TEXT, description="Blog author (legacy)"),
    Property(name="author_name", data_type=DataType.TEXT, description="Blog author display name"),
    Property(name="doc_summary", data_type=DataType.TEXT, description="Document-level summary of the blog post"),
    Property(name="tags", data_type=DataType.TEXT_ARRAY, description="Blog tags"),
    Property(name="category", data_type=DataType.TEXT, description="Blog category"),
    Property(name="heading_path", data_type=DataType.TEXT, description="Heading hierarchy e.g. 'Intro > Setup > Install'"),
    Property(name="section_title", data_type=DataType.TEXT, description="Section title"),
    Property(name="publish_date", data_type=DataType.DATE, description="Publish date"),
]

JIRA_PROPERTIES: List[Property] = [
    Property(name="ticket_key", data_type=DataType.TEXT, description="Jira ticket key e.g. PROJ-123"),
    Property(name="project_key", data_type=DataType.TEXT, description="Jira project key"),
    Property(name="issue_type", data_type=DataType.TEXT, description="Bug|Story|Task|Epic"),
    Property(name="status", data_type=DataType.TEXT, description="Ticket status"),
    Property(name="priority", data_type=DataType.TEXT, description="Ticket priority"),
    Property(name="assignee", data_type=DataType.TEXT, description="Ticket assignee"),
    Property(name="reporter", data_type=DataType.TEXT, description="Ticket reporter"),
    Property(name="labels", data_type=DataType.TEXT_ARRAY, description="Ticket labels"),
    Property(name="components", data_type=DataType.TEXT_ARRAY, description="Ticket components"),
    Property(name="sprint", data_type=DataType.TEXT, description="Sprint name or id"),
    Property(name="ticket_chunk_type", data_type=DataType.TEXT, description="Semantic type: problem|error|resolution|steps|summary for retrieval filtering"),
]

TRANSCRIPT_PROPERTIES: List[Property] = [
    # --- Meeting Identity ---
    # ⚠️ IMPORTANT: Always set doc_id = meeting_id for Transcripts (no mismatch)
    Property(
        name="meeting_id",
        data_type=DataType.TEXT,
        description="Unique meeting/session ID. ⚠️ MUST be set equal to doc_id (doc_id = meeting_id always)",
    ),
    Property(
        name="meeting_title",
        data_type=DataType.TEXT,
        description="Meeting/demo title (e.g., 'CloudFuze Manage Demo - Customer Name')",
    ),
    Property(
        name="meeting_date",
        data_type=DataType.DATE,
        description="Meeting date (ISO-8601)",
    ),
    Property(
        name="meeting_time",
        data_type=DataType.TEXT,
        description="Meeting time (HH:MM:SS format, if available)",
    ),
    Property(
        name="transcript_source",
        data_type=DataType.TEXT,
        description="Transcript source: sharepoint_transcripts|zoom|teams|gmeet",
    ),
    
    # --- Context Metadata ---
    Property(
        name="customer",
        data_type=DataType.TEXT,
        description="Customer name/organization from the demo",
    ),
    Property(
        name="industry",
        data_type=DataType.TEXT,
        description="Customer industry sector (e.g., Education, Healthcare, Finance)",
    ),
    Property(
        name="participants",
        data_type=DataType.TEXT_ARRAY,
        description="List of participant names in the meeting",
    ),
    Property(
        name="speaker_roles",
        data_type=DataType.TEXT_ARRAY,
        description="Speaker roles mapped to names (e.g., ['John (Sales)', 'Jane (Customer)'])",
    ),
    Property(
        name="topic",
        data_type=DataType.TEXT_ARRAY,
        description="Topics discussed in the transcript (multi-topic tagging)",
    ),
    
    # --- Reliability Controls ---
    Property(
        name="kb_tier",
        data_type=DataType.TEXT,
        description="Knowledge base tier: always 'secondary' for transcripts",
    ),
    Property(
        name="reliability",
        data_type=DataType.TEXT,
        description="Reliability level: 'contextual' for transcripts (not contractual)",
    ),
    Property(
        name="not_contractual",
        data_type=DataType.BOOL,
        description="True - transcript content is not contractual/guaranteed",
    ),
    Property(
        name="internal_use_only",
        data_type=DataType.BOOL,
        description="True - transcript is for internal use only",
    ),
    
    # --- Extraction Metadata ---
    Property(
        name="artifact_type",
        data_type=DataType.TEXT,
        description="Type of extracted artifact: qa|objection|feature|decision|action_item|raw",
    ),
    Property(
        name="contains_pricing",
        data_type=DataType.BOOL,
        description="True if transcript contains pricing discussions",
    ),
    
    # --- Legacy/Additional Fields (for backward compatibility) ---
    Property(
        name="speaker",
        data_type=DataType.TEXT,
        description="Speaker name (for individual chunk context, if applicable)",
    ),
    Property(
        name="t_start",
        data_type=DataType.NUMBER,
        description="Start timestamp in seconds (for time-based chunking, if applicable)",
    ),
    Property(
        name="t_end",
        data_type=DataType.NUMBER,
        description="End timestamp in seconds (for time-based chunking, if applicable)",
    ),
]

SPREADSHEET_PROPERTIES: List[Property] = [
    # --- Sheet Structure ---
    Property(name="sheet_name", data_type=DataType.TEXT, description="Excel sheet name"),
    Property(name="sheet_index", data_type=DataType.INT, description="Sheet index (ordering)"),
    Property(name="row_start", data_type=DataType.INT, description="Start row number"),
    Property(name="row_end", data_type=DataType.INT, description="End row number"),
    
    # --- SharePoint Source (Excel files are stored in SharePoint) ---
    Property(
        name="sharepoint_site_name",
        data_type=DataType.TEXT,
        description="SharePoint site name where Excel file is stored",
    ),
    Property(
        name="sharepoint_folder_name",
        data_type=DataType.TEXT,
        description="SharePoint folder name/path where Excel file is stored",
    ),
    Property(
        name="sharepoint_file_id",
        data_type=DataType.TEXT,
        description="SharePoint file ID for the Excel file (used as doc_id)",
    ),
    
    # --- Generic Row Storage (works for all Excels) ---
    # ⚠️ IMPORTANT: row_data must be a JSON string, and row_keys must always include all keys from row_data
    Property(
        name="row_data",
        data_type=DataType.TEXT,
        description="JSON string of row key-value pairs (universal format for any Excel row). "
                    "⚠️ Must be stored as JSON string, not object. All keys in row_data must be present in row_keys.",
    ),
    Property(
        name="row_keys",
        data_type=DataType.TEXT_ARRAY,
        description="Column names present in row (for filtering and querying). "
                    "⚠️ Must always include all keys that exist in row_data JSON.",
    ),
    
    # --- Optional Standardized Fields (only if present, e.g., limitations Excel) ---
    Property(
        name="feature_name",
        data_type=DataType.TEXT,
        description="Feature name (optional - only for standardized formats like limitations Excel)",
    ),
    Property(
        name="limitations",
        data_type=DataType.TEXT,
        description="Limitations/notes (optional - only for standardized formats like limitations Excel)",
    ),
    Property(
        name="supported",
        data_type=DataType.TEXT,
        description="yes|no|na (optional - only for standardized formats like limitations Excel)",
    ),
]

SHAREPOINT_DOC_PROPERTIES: List[Property] = [
    Property(name="folder_name", data_type=DataType.TEXT, description="SharePoint folder name"),
    Property(name="site_name", data_type=DataType.TEXT, description="SharePoint site name"),
    Property(name="page_start", data_type=DataType.INT, description="Start page number (if PDF)"),
    Property(name="page_end", data_type=DataType.INT, description="End page number (if PDF)"),
    Property(name="section_title", data_type=DataType.TEXT, description="Section title / heading"),
    # Layered ingestion: raw_content | table_row | feature_capability | limitation | migration_capability_summary | rule | process
    Property(
        name="chunk_type",
        data_type=DataType.TEXT,
        description="raw_content|table_row|feature_capability|limitation|migration_capability_summary|rule|process|fact|qa|summary",
    ),
    Property(
        name="layout",
        data_type=DataType.TEXT,
        description="Table layout: A (migration per row) | B (feature per row) | C (key-value) | D (narrative)",
    ),
    Property(name="feature", data_type=DataType.TEXT, description="Feature/capability name (for feature/limitation chunks)"),
    Property(name="supported", data_type=DataType.TEXT, description="Yes|No|NA (for feature chunks)"),
    Property(
        name="is_limitation",
        data_type=DataType.BOOL,
        description="True if chunk describes a limitation/restriction (retrieval-time filter)",
    ),
    Property(
        name="raw_kv",
        data_type=DataType.TEXT,
        description="JSON of original columns + sheet_name/row_index for audit and grounding (no information loss)",
    ),
    Property(
        name="migration_type",
        data_type=DataType.TEXT,
        description="Canonical migration path: source__TO__target (e.g. slack__TO__teams, teams__TO__teams)",
    ),
    Property(
        name="migration_combination",
        data_type=DataType.TEXT,
        description="Display name for migration path (e.g. Slack to Teams)",
    ),
    Property(name="vertical_position", data_type=DataType.NUMBER, description="Vertical position on page (for interleaved rendering)"),
]

EMAIL_PROPERTIES: List[Property] = [
    # Thread-level metadata
    # NOTE: thread_summary and message_summary are NOT stored as properties.
    # They are stored as chunks with chunk_role="thread_summary" or chunk_role="message_summary"
    Property(name="thread_id", data_type=DataType.TEXT, description="Gmail thread id / Outlook conversation id"),
    Property(name="subject", data_type=DataType.TEXT, description="Email thread subject"),
    Property(name="mailbox_id", data_type=DataType.TEXT, description="Mailbox identifier (e.g., support@company.com, engineering@company.com)"),
    Property(name="mail_source", data_type=DataType.TEXT, description="Email source: gmail|outlook|exchange"),
    Property(name="participant_emails", data_type=DataType.TEXT_ARRAY, description="List of participant email addresses"),
    Property(name="participant_names", data_type=DataType.TEXT_ARRAY, description="List of participant names (optional)"),
    Property(name="message_count", data_type=DataType.INT, description="Number of messages in the thread"),
    Property(name="is_external_thread", data_type=DataType.BOOL, description="Whether thread contains external participants"),
    Property(name="external_domains", data_type=DataType.TEXT_ARRAY, description="List of external email domains in thread"),
    
    # Message-level metadata
    Property(name="message_id", data_type=DataType.TEXT, description="Unique email message ID"),
    Property(name="from_email", data_type=DataType.TEXT, description="Sender email address"),
    Property(name="to_emails", data_type=DataType.TEXT_ARRAY, description="Recipient email addresses"),
    Property(name="cc_emails", data_type=DataType.TEXT_ARRAY, description="CC email addresses"),
    Property(name="sent_at", data_type=DataType.DATE, description="Message sent timestamp (ISO-8601)"),
    Property(name="in_reply_to", data_type=DataType.TEXT, description="Message ID this email is replying to"),
    Property(name="references", data_type=DataType.TEXT_ARRAY, description="Email references header (thread chain)"),
    
    # User email tracking
    Property(name="user_email_ids", data_type=DataType.TEXT_ARRAY, description="Organization member email IDs involved in thread"),
    Property(name="external_email_ids", data_type=DataType.TEXT_ARRAY, description="External participant email IDs (optional)"),
]

# ==========================
# 4) Vector Index Config
# ==========================
# These are safe defaults for mid-scale corpora.
# Tune later based on recall vs latency needs.
DEFAULT_HNSW = {
    "distance": VectorDistances.COSINE,
    "ef_construction": 128,
    "max_connections": 32,
}

# ==========================
# 5) Helpers: Properties per Collection
# ==========================

def get_properties_for_collection(name: str) -> List[Property]:
    """
    Get Property objects for a specific collection.
    
    Args:
        name: Collection name
    
    Returns:
        List of Property objects
    """
    props = list(UNIVERSAL_PROPERTIES)

    if name == "Blogs":
        props.extend(BLOG_PROPERTIES)

    elif name == "JiraTickets":
        props.extend(JIRA_PROPERTIES)

    elif name == "Transcripts":
        props.extend(TRANSCRIPT_PROPERTIES)

    elif name == "Spreadsheets":
        props.extend(SPREADSHEET_PROPERTIES)

    elif name == "SharePointDocs":
        props.extend(SHAREPOINT_DOC_PROPERTIES)

    elif name == "EmailThreads":
        props.extend(EMAIL_PROPERTIES)

    else:
        raise ValueError(f"Unknown collection name: {name}")

    return props


# ==========================
# 6) Create / Delete Collections
# ==========================

def create_collection(name: str, recreate: bool = False) -> bool:
    """
    Create a Weaviate v4 collection with external vectors (vectorizer_config=None).

    Args:
        name: Collection name
        recreate: delete+recreate if exists

    Returns:
        True if created/existed successfully, False otherwise
    """
    client = get_weaviate_client()
    if client is None:
        logger.error("[WEAVIATE] Client unavailable")
        return False

    try:
        if client.collections.exists(name):
            if recreate:
                logger.info(f"[WEAVIATE] Deleting existing collection: {name}")
                client.collections.delete(name)
            else:
                logger.info(f"[WEAVIATE] Collection already exists: {name}")
                return True

        props = get_properties_for_collection(name)

        # Create collection using v4 API - single legacy vector (no name)
        # This fixes issues with named vectors not being found during retrieval.
        client.collections.create(
            name=name,
            description=f"RAG Knowledge Base Collection: {name}",
            properties=props,
            vectorizer_config=Configure.Vectorizer.none(),
            vector_index_config=Configure.VectorIndex.hnsw(
                distance_metric=DEFAULT_HNSW["distance"],
                ef_construction=DEFAULT_HNSW["ef_construction"],
                max_connections=DEFAULT_HNSW["max_connections"],
            ),
        )
        
        # NOTE: chunk_key uniqueness is enforced at ingestion time by using
        # deterministic UUID based on chunk_key as the Weaviate object ID.
        # This makes updates idempotent: same chunk_key = same UUID = overwrite.
        # Example: uuid = uuid5(NAMESPACE_DNS, chunk_key)
        # Then: .data.insert(uuid=uuid, properties=...)

        logger.info(f"[WEAVIATE] ✓ Created collection: {name}")
        return True

    except Exception as e:
        logger.exception(f"[WEAVIATE] Failed to create collection '{name}': {e}")
        return False


def create_all_collections(recreate: bool = False) -> bool:
    """
    Create all required collections.
    
    Args:
        recreate: If True, delete existing collections before creating
    
    Returns:
        True if all collections created successfully, False otherwise
    """
    ok = True
    for name in COLLECTIONS:
        ok = create_collection(name, recreate=recreate) and ok

    if ok:
        logger.info("[WEAVIATE] ✓ All collections created successfully")
    else:
        logger.error("[WEAVIATE] Some collections failed to create")

    return ok


def delete_collection(name: str) -> bool:
    """
    Delete a Weaviate collection.
    
    Args:
        name: Collection name to delete
    
    Returns:
        True if successful, False otherwise
    """
    client = get_weaviate_client()
    if client is None:
        logger.error("[WEAVIATE] Client unavailable")
        return False

    try:
        if not client.collections.exists(name):
            logger.warning(f"[WEAVIATE] Collection does not exist: {name}")
            return True

        client.collections.delete(name)
        logger.info(f"[WEAVIATE] ✓ Deleted collection: {name}")
        return True

    except Exception as e:
        logger.exception(f"[WEAVIATE] Failed to delete collection '{name}': {e}")
        return False


def list_collections() -> List[str]:
    """
    List all existing Weaviate collections.
    Auto-reconnects if client was closed.
    
    Returns:
        List of collection names
    """
    client = get_weaviate_client()
    if client is None:
        logger.error("[WEAVIATE] Client unavailable")
        return []

    try:
        # v4 API: list_all() may return dict or list/iterator depending on SDK version
        collections = client.collections.list_all()
        if isinstance(collections, dict):
            return list(collections.keys())
        # Handle list/iterator case
        return [c for c in collections] if hasattr(collections, '__iter__') and not isinstance(collections, str) else []
    except Exception as e:
        # If client was closed, try to reconnect and retry once
        error_str = str(e).lower()
        if "closed" in error_str or "connect" in error_str:
            logger.info("[WEAVIATE] Client was closed, reconnecting for list_collections...")
            try:
                # Reset client to force reconnection
                from app.weaviate_client import reset_weaviate_client
                reset_weaviate_client()
                client = get_weaviate_client()
                if client is not None:
                    collections = client.collections.list_all()
                    if isinstance(collections, dict):
                        return list(collections.keys())
                    return [c for c in collections] if hasattr(collections, '__iter__') and not isinstance(collections, str) else []
            except Exception as retry_e:
                logger.exception(f"[WEAVIATE] Failed to list collections after reconnect: {retry_e}")
                return []
        else:
            logger.exception(f"[WEAVIATE] Failed to list collections: {e}")
            return []


def get_collection_info(name: str) -> Optional[Dict[str, Any]]:
    """
    Get information about a specific collection.
    
    Args:
        name: Collection name
    
    Returns:
        Dictionary with collection schema info, or None if not found
    """
    client = get_weaviate_client()
    if client is None:
        return None

    try:
        if not client.collections.exists(name):
            return None

        col = client.collections.get(name)
        return {
            "name": name,
            "description": col.config.description,
            "properties": [p.name for p in col.config.properties],
        }

    except Exception as e:
        logger.exception(f"[WEAVIATE] Failed to get collection info for '{name}': {e}")
        return None
