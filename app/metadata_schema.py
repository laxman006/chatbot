"""
Unified metadata schema for all ingested documents.
Provides consistent metadata structure across SharePoint, Outlook, and blog sources.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


@dataclass
class UnifiedMetadata:
    """
    Unified metadata structure for all document sources.
    
    This schema provides consistent metadata extraction and storage
    across SharePoint files, Outlook emails, and blog posts.
    """
    # Core identifiers
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source: str = ""  # "sharepoint" | "email" | "blog" | "web"
    url: str = ""
    filename: str = ""
    filetype: str = ""  # pdf|docx|pptx|xlsx|html|eml|txt
    
    # Author and timestamp metadata
    author: Optional[str] = None
    created: Optional[str] = None  # ISO timestamp
    modified: Optional[str] = None  # ISO timestamp
    
    # Content location metadata
    page_number: Optional[int] = None
    
    # SharePoint specific
    site: Optional[str] = None
    path: Optional[str] = None  # library/folder path (e.g., "Documents > Folder > Subfolder")
    
    # Email specific
    thread_id: Optional[str] = None
    message_id: Optional[str] = None
    email_from: Optional[str] = None
    email_to: Optional[str] = None
    email_cc: Optional[str] = None
    email_subject: Optional[str] = None
    in_reply_to: Optional[str] = None  # For thread relationships
    references: Optional[str] = None  # Email references header
    
    # Blog/Web specific
    post_title: Optional[str] = None
    post_slug: Optional[str] = None
    post_url: Optional[str] = None
    
    # Content metadata
    language: str = "en"
    content_type: Optional[str] = None  # "text" | "table" | "faq" | "slide" | "email"
    
    # Chunking metadata
    chunk_id: Optional[str] = None
    chunk_index: Optional[int] = None
    total_chunks: Optional[int] = None
    char_range: Optional[str] = None  # e.g., "0-1000"
    token_count: Optional[int] = None
    
    # Additional metadata
    file_size: Optional[int] = None  # in bytes
    is_downloadable: bool = False
    download_url: Optional[str] = None
    tags: Optional[str] = None  # Comma-separated tags
    
    # Deduplication metadata
    relevance_count: int = 1  # Incremented when duplicates are merged
    original_sources: Optional[str] = None  # Comma-separated doc_ids of merged duplicates
    
    # Transcript/Demo Call specific metadata (Secondary KB)
    kb_tier: Optional[str] = None  # "primary" | "secondary" - None means primary
    customer: Optional[str] = None  # Customer name (e.g., "Phillips Exeter Academy")
    industry: Optional[str] = None  # Industry sector (e.g., "Education")
    speaker_roles: Optional[str] = None  # Comma-separated "Customer | CloudFuze"
    topic: Optional[str] = None  # Comma-separated topics (e.g., "Shadow IT | Pricing | Integrations")
    artifact_type: Optional[str] = None  # "Q&A | Objection | Feature | Pricing | Decision Driver"
    priority: Optional[str] = None  # "High | Medium | Low"
    reliability: Optional[str] = None  # "contextual" | "official" - defaults to "contextual" for transcripts
    not_contractual: bool = False  # True for transcripts (not official commitments)
    internal_use_only: bool = False  # True for customer-identifiable content
    contains_pricing: bool = False  # True if transcript contains pricing discussions
    customer_identifiable: bool = False  # True if transcript contains customer-specific info
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert metadata to dictionary, removing None values."""
        data = asdict(self)
        # Remove None values to keep metadata clean
        return {k: v for k, v in data.items() if v is not None}
    
    def to_chroma_metadata(self) -> Dict[str, Any]:
        """
        Convert to ChromaDB-compatible metadata.
        ChromaDB only accepts str, int, float, or bool values.
        """
        data = self.to_dict()
        chroma_metadata = {}
        
        for key, value in data.items():
            if value is None:
                continue
            elif isinstance(value, (str, int, float, bool)):
                chroma_metadata[key] = value
            elif isinstance(value, list):
                # Convert lists to comma-separated strings
                chroma_metadata[key] = ", ".join(str(v) for v in value)
            else:
                # Convert other types to string
                chroma_metadata[key] = str(value)
        
        return chroma_metadata
    
    @classmethod
    def from_sharepoint_file(cls, file_data: Dict[str, Any], folder_path: str = "") -> "UnifiedMetadata":
        """Create metadata from SharePoint file data."""
        return cls(
            source="sharepoint",
            url=file_data.get("webUrl", ""),
            filename=file_data.get("name", ""),
            filetype=cls._extract_filetype(file_data.get("name", "")),
            author=file_data.get("createdBy", {}).get("user", {}).get("displayName"),
            created=file_data.get("createdDateTime"),
            modified=file_data.get("lastModifiedDateTime"),
            site=file_data.get("site_url", ""),
            path=folder_path,
            file_size=file_data.get("size"),
            download_url=file_data.get("@microsoft.graph.downloadUrl"),
            is_downloadable=True if file_data.get("@microsoft.graph.downloadUrl") else False
        )
    
    @classmethod
    def from_outlook_email(cls, email_data: Dict[str, Any], folder_name: str = "") -> "UnifiedMetadata":
        """Create metadata from Outlook email data."""
        from_email = email_data.get("from", {}).get("emailAddress", {}).get("address", "")
        to_emails = ", ".join(
            r.get("emailAddress", {}).get("address", "")
            for r in email_data.get("toRecipients", [])
        )
        cc_emails = ", ".join(
            r.get("emailAddress", {}).get("address", "")
            for r in email_data.get("ccRecipients", [])
        )
        
        return cls(
            source="email",
            url=f"outlook:{email_data.get('id', '')}",
            filename=f"{email_data.get('subject', 'No Subject')}.eml",
            filetype="eml",
            created=email_data.get("receivedDateTime"),
            modified=email_data.get("lastModifiedDateTime"),
            thread_id=email_data.get("conversationId"),
            message_id=email_data.get("id"),
            email_from=from_email,
            email_to=to_emails if to_emails else None,
            email_cc=cc_emails if cc_emails else None,
            email_subject=email_data.get("subject"),
            content_type="email",
            tags=f"email/{folder_name.lower().replace(' ', '_')}"
        )
    
    @classmethod
    def from_blog_post(cls, post_data: Dict[str, Any]) -> "UnifiedMetadata":
        """Create metadata from blog post data."""
        return cls(
            source="blog",
            url=post_data.get("link", ""),
            filename=post_data.get("slug", ""),
            filetype="html",
            author=post_data.get("author_name"),
            created=post_data.get("date"),
            modified=post_data.get("modified"),
            post_title=post_data.get("title", {}).get("rendered", ""),
            post_slug=post_data.get("slug", ""),
            post_url=post_data.get("link", ""),
            content_type="blog_post",
            tags="blog"
        )
    
    @staticmethod
    def _extract_filetype(filename: str) -> str:
        """Extract file extension from filename."""
        if not filename:
            return ""
        
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        return ext


def create_chunk_metadata(
    base_metadata: UnifiedMetadata,
    chunk_index: int,
    total_chunks: int,
    char_start: int,
    char_end: int,
    token_count: int
) -> UnifiedMetadata:
    """
    Create metadata for a document chunk.
    
    Args:
        base_metadata: Base document metadata
        chunk_index: Index of this chunk (0-based)
        total_chunks: Total number of chunks in document
        char_start: Starting character position
        char_end: Ending character position
        token_count: Number of tokens in chunk
    
    Returns:
        UnifiedMetadata object for the chunk
    """
    # Create a copy of base metadata
    chunk_metadata = UnifiedMetadata(**base_metadata.to_dict())
    
    # Add chunk-specific metadata
    chunk_metadata.chunk_id = str(uuid.uuid4())
    chunk_metadata.chunk_index = chunk_index
    chunk_metadata.total_chunks = total_chunks
    chunk_metadata.char_range = f"{char_start}-{char_end}"
    chunk_metadata.token_count = token_count
    
    return chunk_metadata

