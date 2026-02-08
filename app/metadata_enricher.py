"""
Metadata enricher for transforming LangChain Documents to WeaviateChunk format.

Handles parent_key generation, content_hash, token_count, and RBAC permissions.
"""

import hashlib
import uuid
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import tiktoken

from langchain_core.documents import Document
from app.weaviate_models import WeaviateChunk
from app.weaviate_schema import (
    get_source_type_for_collection,
    validate_chunk_role,
    VALID_CHUNK_ROLES,
    CHUNK_ROLE_CONTENT
)

logger = logging.getLogger(__name__)

# Default RBAC permissions (deny-by-default)
DEFAULT_PERMISSIONS = ["admin"]  # Restrictive default - prevents data leaks

# Token counter (using tiktoken for accurate counting)
_token_encoder = None


def _get_token_encoder():
    """Get or create tiktoken encoder."""
    global _token_encoder
    if _token_encoder is None:
        _token_encoder = tiktoken.get_encoding("cl100k_base")  # Used by text-embedding-3-small
    return _token_encoder


def _site_name_from_url(url: str) -> str:
    """Parse site name from SharePoint URL (e.g. .../sites/Repository25/... -> Repository25)."""
    if not url or not isinstance(url, str):
        return ""
    try:
        if "/sites/" in url:
            rest = url.split("/sites/", 1)[1]
            site_part = rest.split("/", 1)[0].strip()
            if site_part:
                return site_part
    except Exception:
        pass
    return ""


class ParentKeyBuilder:
    """
    Builds stable parent_key identifiers per source type.
    
    Ensures consistent parent_key format across all sources for stable UUID generation.
    """
    
    @staticmethod
    def build_parent_key(
        source_type: str,
        doc_metadata: Dict[str, Any]
    ) -> str:
        """
        Build parent_key using source-specific convention.
        
        Conventions:
        - SharePoint: sharepoint/{site}/{folder}/{file}
        - Jira: jira/{project}/{ticket_key}
        - Blogs: blog/{slug}
        - Transcript: transcript/{customer}/{meeting_date}/{meeting_id}
        - Email: email/{mailbox_id}/{thread_id}
        - Excel: excel/{sharepoint_file_id}/{sheet_name}
        
        Args:
            source_type: Source type (sharepoint, jira, blog, transcript, email, excel)
            doc_metadata: Document metadata dictionary
        
        Returns:
            Stable parent_key string
        """
        source_type = source_type.lower()
        
        if source_type == "sharepoint":
            site = (
                doc_metadata.get("site_name")
                or _site_name_from_url(doc_metadata.get("site_url", ""))
                or "unknown"
            )
            folder = (
                doc_metadata.get("folder_name")
                or (doc_metadata.get("folder_path", "") or "").replace(" > ", "_").replace("/", "_")
            ).strip() or "_"
            file = (
                doc_metadata.get("source_ref")
                or doc_metadata.get("file_name")
                or doc_metadata.get("filename", "unknown")
            )
            return f"sharepoint/{site}/{folder}/{file}"
        
        elif source_type == "jira":
            project = doc_metadata.get("project_key", "unknown")
            ticket_key = doc_metadata.get("ticket_key", doc_metadata.get("source_ref", "unknown"))
            return f"jira/{project}/{ticket_key}"
        
        elif source_type == "blog":
            slug = doc_metadata.get("post_slug", doc_metadata.get("source_ref", "unknown"))
            return f"blog/{slug}"
        
        elif source_type == "transcript":
            customer = doc_metadata.get("customer", "unknown")
            meeting_date = doc_metadata.get("meeting_date", "unknown")
            meeting_id = doc_metadata.get("meeting_id", doc_metadata.get("doc_id", "unknown"))
            return f"transcript/{customer}/{meeting_date}/{meeting_id}"
        
        elif source_type == "email":
            mailbox_id = doc_metadata.get("mailbox_id", "unknown")
            thread_id = doc_metadata.get("thread_id", doc_metadata.get("source_ref", "unknown"))
            return f"email/{mailbox_id}/{thread_id}"
        
        elif source_type == "excel":
            file_id = doc_metadata.get("sharepoint_file_id", doc_metadata.get("doc_id", "unknown"))
            sheet_name = doc_metadata.get("sheet_name", "Sheet1")
            return f"excel/{file_id}/{sheet_name}"
        
        else:
            # Fallback: use source_type and doc_id
            doc_id = doc_metadata.get("doc_id", "unknown")
            return f"{source_type}/{doc_id}"


class MetadataEnricher:
    """
    Enriches LangChain Documents with Weaviate metadata.
    
    Transforms Documents to WeaviateChunk format with all required fields:
    - parent_id, parent_key, chunk_key, chunk_id
    - content_hash, token_count
    - RBAC permissions (deny-by-default)
    - source_type, chunk_role validation
    """
    
    def __init__(self, default_permissions: Optional[List[str]] = None):
        """
        Initialize metadata enricher.
        
        Args:
            default_permissions: Default RBAC permissions (deny-by-default)
        """
        self.default_permissions = default_permissions or DEFAULT_PERMISSIONS
        logger.info(f"[METADATA] Initialized with default_permissions={self.default_permissions}")
    
    def enrich_chunks(
        self,
        chunks: List[Document],
        doc_id: str,
        collection_name: str,
        doc_metadata: Optional[Dict[str, Any]] = None,
        is_summary: bool = False
    ) -> List[WeaviateChunk]:
        """
        Enrich multiple chunks from a document.
        
        Args:
            chunks: List of LangChain Document chunks
            doc_id: Stable document ID
            collection_name: Weaviate collection name
            doc_metadata: Document-level metadata (for parent_key generation)
            is_summary: Whether these are summary chunks (chunk_id=-1)
        
        Returns:
            List of WeaviateChunk objects with enriched metadata
        """
        if not chunks:
            return []
        
        # Get source_type for collection
        source_type = get_source_type_for_collection(collection_name)
        
        # Build parent_key from doc_metadata
        if doc_metadata is None:
            doc_metadata = chunks[0].metadata if chunks else {}
        
        parent_key = ParentKeyBuilder.build_parent_key(source_type, doc_metadata)
        
        # Generate parent_id from doc_id (UUID v5 for stability)
        parent_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, doc_id))
        
        # Enrich each chunk
        enriched_chunks = []
        for idx, chunk in enumerate(chunks):
            chunk_id = -1 if is_summary else idx
            enriched = self._enrich_single_chunk(
                chunk=chunk,
                doc_id=doc_id,
                parent_id=parent_id,
                parent_key=parent_key,
                chunk_id=chunk_id,
                collection_name=collection_name,
                source_type=source_type,
                doc_metadata=doc_metadata
            )
            enriched_chunks.append(enriched)
        
        logger.info(
            f"[METADATA] Enriched {len(enriched_chunks)} chunks "
            f"(doc_id={doc_id}, parent_key={parent_key})"
        )
        
        return enriched_chunks
    
    def _enrich_single_chunk(
        self,
        chunk: Document,
        doc_id: str,
        parent_id: str,
        parent_key: str,
        chunk_id: int,
        collection_name: str,
        source_type: str,
        doc_metadata: Dict[str, Any]
    ) -> WeaviateChunk:
        """
        Enrich a single chunk with Weaviate metadata.
        
        Args:
            chunk: LangChain Document chunk
            doc_id: Document ID
            parent_id: Parent document UUID
            parent_key: Parent key (path-like identifier)
            chunk_id: Chunk index (0..N for content, -1 for summaries)
            collection_name: Weaviate collection name
            source_type: Source type string
            doc_metadata: Document-level metadata
        
        Returns:
            WeaviateChunk with enriched metadata
        """
        # Generate chunk_key
        chunk_key = f"{parent_key}#chunk_{chunk_id}"
        
        # Generate content_hash
        content_hash = self._generate_content_hash(chunk.page_content)
        
        # Calculate token_count
        token_count = self._calculate_token_count(chunk.page_content)
        
        # Get chunk_role (validate if present)
        chunk_role = chunk.metadata.get("chunk_role", CHUNK_ROLE_CONTENT)
        if chunk_role not in VALID_CHUNK_ROLES:
            logger.warning(
                f"[METADATA] Invalid chunk_role '{chunk_role}' for chunk {chunk_key}. "
                f"Using default '{CHUNK_ROLE_CONTENT}'"
            )
            chunk_role = CHUNK_ROLE_CONTENT
        validate_chunk_role(chunk_role)  # Raises ValueError if invalid
        
        # Get RBAC permissions (deny-by-default)
        permissions = chunk.metadata.get("permissions")
        if not permissions:
            # Try to get from doc_metadata
            permissions = doc_metadata.get("permissions")
        if not permissions:
            # Use default (deny-by-default)
            permissions = self.default_permissions.copy()
        
        # Ensure permissions is a list
        if isinstance(permissions, str):
            permissions = [permissions]
        
        # Universal title/url/dates – for Blogs, add fallbacks from post_* when missing
        title_val = chunk.metadata.get("title") or doc_metadata.get("title") or ""
        url_val = chunk.metadata.get("url") or doc_metadata.get("url") or ""
        created_val = chunk.metadata.get("created_at") or doc_metadata.get("created_at")
        updated_val = chunk.metadata.get("updated_at") or doc_metadata.get("updated_at")
        if collection_name == "Blogs":
            title_val = title_val or doc_metadata.get("post_title", "")
            url_val = url_val or doc_metadata.get("post_url", "")
            created_val = created_val or doc_metadata.get("post_date")
            updated_val = updated_val or doc_metadata.get("post_date")
        # SharePoint: map file_name → title, file_url/page_url/webUrl → url
        if collection_name == "SharePointDocs" or source_type == "sharepoint":
            title_val = title_val or doc_metadata.get("file_name", "")
            url_val = url_val or (
                doc_metadata.get("file_url")
                or doc_metadata.get("page_url")
                or doc_metadata.get("webUrl", "")
            )
        source_ref_val = chunk.metadata.get("source_ref") or doc_metadata.get("source_ref") or ""
        if (collection_name == "SharePointDocs" or source_type == "sharepoint") and not source_ref_val:
            source_ref_val = doc_metadata.get("file_name", "")
        
        # Build Weaviate metadata
        weaviate_metadata = {
            # Universal properties
            "content": chunk.page_content,
            "source_type": source_type,
            "source_ref": source_ref_val,
            "file_type": chunk.metadata.get("file_type", ""),
            "doc_id": doc_id,
            "parent_id": parent_id,
            "parent_key": parent_key,
            "chunk_id": chunk_id,
            "chunk_key": chunk_key,
            "chunk_role": chunk_role,
            "title": title_val,
            "url": url_val,
            "created_at": self._parse_date(created_val),
            "updated_at": self._parse_date(updated_val),
            "permissions": permissions,
            "tenant_id": chunk.metadata.get("tenant_id", doc_metadata.get("tenant_id", "")),
            "department": chunk.metadata.get("department", doc_metadata.get("department", "")),
            "version": chunk.metadata.get("version", doc_metadata.get("version", 1)),
            "last_indexed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "token_count": token_count,
            
            # Optional: raw_text for debugging
            # "raw_text": chunk.page_content,  # Uncomment if needed for debugging
        }
        
        # Add collection-specific properties
        weaviate_metadata.update(self._get_collection_specific_metadata(chunk, doc_metadata, collection_name))
        
        # Create WeaviateChunk
        weaviate_chunk = WeaviateChunk(
            content=chunk.page_content,
            metadata=weaviate_metadata,
            vector=None,  # Will be populated by EmbeddingService
            content_hash=content_hash,
            token_count=token_count,
            chunk_key=chunk_key,
            parent_id=parent_id,
            parent_key=parent_key,
            chunk_id=chunk_id
        )
        
        return weaviate_chunk
    
    def _generate_content_hash(self, content: str) -> str:
        """
        Generate MD5 hash of content for deduplication.
        
        Args:
            content: Text content
        
        Returns:
            MD5 hash string
        """
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _calculate_token_count(self, content: str) -> int:
        """
        Calculate token count using tiktoken.
        
        Args:
            content: Text content
        
        Returns:
            Token count
        """
        try:
            encoder = _get_token_encoder()
            return len(encoder.encode(content))
        except Exception as e:
            logger.warning(f"[METADATA] Failed to calculate token count: {e}. Using character-based estimate.")
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(content) // 4
    
    def _to_rfc3339(self, s: str) -> str:
        """
        Ensure a date string is RFC3339 (Weaviate requires timezone on datetimes).
        Appends 'Z' when the string is YYYY-MM-DDTHH:MM:SS with no trailing offset.
        """
        if not s or not isinstance(s, str):
            return s
        s = s.strip()
        # Already has timezone (Z or ±HH:MM)
        if s.endswith("Z"):
            return s
        if len(s) >= 25 and s[-6] in "+-" and s[-3] == ":":
            return s
        # Date-only (YYYY-MM-DD): Weaviate requires full RFC3339 date-time
        if len(s) == 10 and s[4] == "-" and s[7] == "-":
            return s + "T00:00:00Z"
        # Datetime without offset: use first 19 chars and append Z (treat as UTC)
        if "T" in s and len(s) >= 19:
            return s[:19] + "Z"
        return s

    def _parse_date(self, date_value: Any) -> Optional[str]:
        """
        Parse date value to RFC3339 string for Weaviate.
        Weaviate DATE fields require RFC3339; datetimes must include timezone (e.g. Z or +00:00).
        
        Args:
            date_value: Date value (datetime, string, or None)
        
        Returns:
            RFC3339 string or None
        """
        if date_value is None:
            return None
        
        if isinstance(date_value, datetime):
            if date_value.tzinfo is None:
                return date_value.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
            out = date_value.isoformat()
            return out.replace("+00:00", "Z") if "+00:00" in out else out
        
        if isinstance(date_value, str):
            raw = date_value.strip()
            try:
                for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"]:
                    try:
                        part = raw[:19] if "T" in fmt else raw[:10]
                        dt = datetime.strptime(part, fmt)
                        if fmt == "%Y-%m-%d":
                            return dt.strftime("%Y-%m-%dT00:00:00") + "Z"
                        return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
                    except ValueError:
                        continue
            except Exception:
                pass
            return self._to_rfc3339(raw)
        
        return None
    
    def _get_collection_specific_metadata(
        self,
        chunk: Document,
        doc_metadata: Dict[str, Any],
        collection_name: str
    ) -> Dict[str, Any]:
        """
        Get collection-specific metadata properties.
        
        Args:
            chunk: LangChain Document chunk
            doc_metadata: Document-level metadata
            collection_name: Collection name
        
        Returns:
            Dictionary with collection-specific properties
        """
        metadata = {}
        
        # Merge chunk and doc metadata (chunk takes precedence)
        combined_metadata = {**doc_metadata, **chunk.metadata}
        
        if collection_name == "Blogs":
            metadata.update({
                "author": combined_metadata.get("author", ""),
                "author_name": (combined_metadata.get("author_name") or combined_metadata.get("author", "") or ""),
                "doc_summary": combined_metadata.get("doc_summary", "") or "",
                "tags": self._ensure_list(combined_metadata.get("tags", [])),
                "category": combined_metadata.get("category", ""),
                "heading_path": combined_metadata.get("heading_path", ""),
                "section_title": combined_metadata.get("section_title", ""),
                "publish_date": self._parse_date(
                    combined_metadata.get("publish_date") or combined_metadata.get("post_date")
                ),
            })
        
        elif collection_name == "JiraTickets":
            metadata.update({
                "ticket_key": combined_metadata.get("ticket_key", ""),
                "project_key": combined_metadata.get("project_key", ""),
                "issue_type": combined_metadata.get("issue_type", ""),
                "status": combined_metadata.get("status", ""),
                "priority": combined_metadata.get("priority", ""),
                "assignee": combined_metadata.get("assignee", ""),
                "reporter": combined_metadata.get("reporter", ""),
                "labels": self._ensure_list(combined_metadata.get("labels", [])),
                "components": self._ensure_list(combined_metadata.get("components", [])),
                "sprint": combined_metadata.get("sprint", ""),
                "ticket_chunk_type": combined_metadata.get("ticket_chunk_type", ""),
            })
        
        elif collection_name == "Transcripts":
            metadata.update({
                "meeting_id": combined_metadata.get("meeting_id", combined_metadata.get("doc_id", "")),
                "meeting_title": combined_metadata.get("meeting_title", ""),
                "meeting_date": self._parse_date(combined_metadata.get("meeting_date")),
                "meeting_time": combined_metadata.get("meeting_time", ""),
                "transcript_source": combined_metadata.get("transcript_source", ""),
                "customer": combined_metadata.get("customer", ""),
                "industry": combined_metadata.get("industry", ""),
                "participants": self._ensure_list(combined_metadata.get("participants", [])),
                "speaker_roles": self._ensure_list(combined_metadata.get("speaker_roles", [])),
                "topic": self._ensure_list(combined_metadata.get("topic", [])),
                "kb_tier": combined_metadata.get("kb_tier", "secondary"),
                "reliability": combined_metadata.get("reliability", "contextual"),
                "not_contractual": combined_metadata.get("not_contractual", True),
                "internal_use_only": combined_metadata.get("internal_use_only", True),
                "artifact_type": combined_metadata.get("artifact_type", ""),
                "contains_pricing": combined_metadata.get("contains_pricing", False),
                "speaker": combined_metadata.get("speaker", ""),
                "t_start": combined_metadata.get("t_start"),
                "t_end": combined_metadata.get("t_end"),
            })
        
        elif collection_name == "Spreadsheets":
            metadata.update({
                "sheet_name": combined_metadata.get("sheet_name", ""),
                "sheet_index": combined_metadata.get("sheet_index", 0),
                "row_start": combined_metadata.get("row_start", 0),
                "row_end": combined_metadata.get("row_end", 0),
                "sharepoint_site_name": combined_metadata.get("sharepoint_site_name", ""),
                "sharepoint_folder_name": combined_metadata.get("sharepoint_folder_name", ""),
                "sharepoint_file_id": combined_metadata.get("sharepoint_file_id", combined_metadata.get("doc_id", "")),
                "row_data": combined_metadata.get("row_data", ""),  # JSON string
                "row_keys": self._ensure_list(combined_metadata.get("row_keys", [])),
                "feature_name": combined_metadata.get("feature_name", ""),
                "limitations": combined_metadata.get("limitations", ""),
                "supported": combined_metadata.get("supported", ""),
            })
        
        elif collection_name == "SharePointDocs":
            chunk_type = combined_metadata.get("chunk_type") or "text"
            is_limitation = combined_metadata.get("is_limitation")
            if is_limitation is None:
                is_limitation = chunk_type == "limitation" if chunk_type else False
            folder_name = combined_metadata.get("folder_name") or combined_metadata.get("folder_path", "")
            site_name = combined_metadata.get("site_name") or _site_name_from_url(combined_metadata.get("site_url", ""))
            page_start = combined_metadata.get("page_start")
            page_end = combined_metadata.get("page_end")
            if combined_metadata.get("page_number") is not None and page_start is None:
                page_start = combined_metadata.get("page_number")
                page_end = combined_metadata.get("page_number")
            metadata.update({
                "folder_name": folder_name,
                "site_name": site_name,
                "page_start": page_start,
                "page_end": page_end,
                "section_title": combined_metadata.get("section_title", ""),
                "chunk_type": chunk_type,
                "layout": combined_metadata.get("layout") or "",
                "feature": combined_metadata.get("feature") or "",
                "supported": combined_metadata.get("supported") or "",
                "is_limitation": is_limitation,
                "raw_kv": combined_metadata.get("raw_kv") or "",
                "migration_type": combined_metadata.get("migration_type") or "",
                "migration_combination": combined_metadata.get("migration_combination") or "",
            })
            # Positional metadata for interleaved rendering (text chunks only; image ingestion disabled)
            if combined_metadata.get("vertical_position") is not None:
                metadata["vertical_position"] = float(combined_metadata.get("vertical_position"))
        
        elif collection_name == "EmailThreads":
            metadata.update({
                "thread_id": combined_metadata.get("thread_id", ""),
                "subject": combined_metadata.get("subject", ""),
                "mailbox_id": combined_metadata.get("mailbox_id", ""),
                "mail_source": combined_metadata.get("mail_source", ""),
                "participant_emails": self._ensure_list(combined_metadata.get("participant_emails", [])),
                "participant_names": self._ensure_list(combined_metadata.get("participant_names", [])),
                "message_count": combined_metadata.get("message_count", 0),
                "is_external_thread": combined_metadata.get("is_external_thread", False),
                "external_domains": self._ensure_list(combined_metadata.get("external_domains", [])),
                "message_id": combined_metadata.get("message_id", ""),
                "from_email": combined_metadata.get("from_email", ""),
                "to_emails": self._ensure_list(combined_metadata.get("to_emails", [])),
                "cc_emails": self._ensure_list(combined_metadata.get("cc_emails", [])),
                "sent_at": self._parse_date(combined_metadata.get("sent_at")),
                "in_reply_to": combined_metadata.get("in_reply_to", ""),
                "references": self._ensure_list(combined_metadata.get("references", [])),
                "user_email_ids": self._ensure_list(combined_metadata.get("user_email_ids", [])),
                "external_email_ids": self._ensure_list(combined_metadata.get("external_email_ids", [])),
            })
        
        return metadata
    
    def _ensure_list(self, value: Any) -> List[str]:
        """
        Ensure value is a list of strings.
        
        Args:
            value: Value to convert
        
        Returns:
            List of strings
        """
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [str(v) for v in value]
        return [str(value)]
