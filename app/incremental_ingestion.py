"""
Incremental ingestion tracker for change detection and delta updates.

Uses doc_hash (MD5 of normalized document text) for reliable change detection.
Handles deletions and content_hash tracking.
"""

import hashlib
import json
import logging
import os
from typing import Dict, List, Set, Optional, Tuple
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Default storage path for tracking data
DEFAULT_TRACKING_DIR = "data/ingestion_tracking"


class IncrementalIngestionTracker:
    """
    Tracks document versions and changes for incremental ingestion.
    
    Features:
    - doc_hash tracking (MD5 of normalized doc text) - more reliable than version numbers
    - Change detection: new, modified, deleted documents
    - Deletion handling: track and delete stale chunks
    - content_hash tracking for chunk-level dedup
    """
    
    def __init__(
        self,
        tracking_dir: str = DEFAULT_TRACKING_DIR,
        source_type: Optional[str] = None
    ):
        """
        Initialize incremental ingestion tracker.
        
        Args:
            tracking_dir: Directory to store tracking files
            source_type: Source type (for separate tracking per source)
        """
        self.tracking_dir = Path(tracking_dir)
        self.source_type = source_type or "default"
        self.tracking_file = self.tracking_dir / f"{self.source_type}_tracking.json"
        
        # In-memory tracking data
        self._doc_hashes: Dict[str, str] = {}  # doc_id -> doc_hash
        self._content_hashes: Set[str] = set()  # Set of content_hash values
        
        # Load existing tracking data
        self._load_tracking_data()
        
        logger.info(
            f"[INCREMENTAL] Initialized tracker for source_type={self.source_type}, "
            f"tracking_file={self.tracking_file}, "
            f"loaded {len(self._doc_hashes)} doc hashes"
        )
    
    def _load_tracking_data(self):
        """Load tracking data from file."""
        if not self.tracking_file.exists():
            logger.info(f"[INCREMENTAL] Tracking file not found, starting fresh: {self.tracking_file}")
            return
        
        try:
            with open(self.tracking_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._doc_hashes = data.get("doc_hashes", {})
                self._content_hashes = set(data.get("content_hashes", []))
            
            logger.info(
                f"[INCREMENTAL] Loaded tracking data: {len(self._doc_hashes)} docs, "
                f"{len(self._content_hashes)} content hashes"
            )
        except Exception as e:
            logger.warning(f"[INCREMENTAL] Failed to load tracking data: {e}. Starting fresh.")
            self._doc_hashes = {}
            self._content_hashes = set()
    
    def _save_tracking_data(self):
        """Save tracking data to file."""
        self.tracking_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            data = {
                "source_type": self.source_type,
                "last_updated": datetime.now().isoformat(),
                "doc_hashes": self._doc_hashes,
                "content_hashes": list(self._content_hashes)
            }
            
            with open(self.tracking_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.debug(f"[INCREMENTAL] Saved tracking data to {self.tracking_file}")
        except Exception as e:
            logger.error(f"[INCREMENTAL] Failed to save tracking data: {e}")
    
    def compute_doc_hash(self, content: str, metadata: Optional[Dict] = None) -> str:
        """
        Compute document hash from normalized content.
        
        More reliable than version numbers (SharePoint/Jira versions may not update correctly).
        
        Args:
            content: Document content text
            metadata: Optional metadata to include in hash
        
        Returns:
            MD5 hash string
        """
        # Normalize content (strip whitespace, lowercase for comparison)
        normalized = content.strip().lower()
        
        # Optionally include key metadata in hash
        if metadata:
            # Include important metadata fields that affect document identity
            key_fields = ["title", "source_ref", "ticket_key", "meeting_id", "thread_id"]
            metadata_str = "|".join(
                str(metadata.get(k, "")) for k in key_fields if k in metadata
            )
            normalized += "|" + metadata_str
        
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    def detect_changes(
        self,
        current_docs: Dict[str, Tuple[str, Dict]]  # doc_id -> (content, metadata)
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        Detect changes: new, modified, deleted documents.
        
        Args:
            current_docs: Dictionary of current documents {doc_id: (content, metadata)}
        
        Returns:
            Tuple of (new_doc_ids, modified_doc_ids, deleted_doc_ids)
        """
        # Compute current hashes
        current_hashes = {}
        for doc_id, (content, metadata) in current_docs.items():
            doc_hash = self.compute_doc_hash(content, metadata)
            current_hashes[doc_id] = doc_hash
        
        # Detect changes
        new_doc_ids = [
            doc_id for doc_id in current_hashes.keys()
            if doc_id not in self._doc_hashes
        ]
        
        modified_doc_ids = [
            doc_id for doc_id, doc_hash in current_hashes.items()
            if doc_id in self._doc_hashes and self._doc_hashes[doc_id] != doc_hash
        ]
        
        deleted_doc_ids = [
            doc_id for doc_id in self._doc_hashes.keys()
            if doc_id not in current_hashes
        ]
        
        logger.info(
            f"[INCREMENTAL] Change detection: {len(new_doc_ids)} new, "
            f"{len(modified_doc_ids)} modified, {len(deleted_doc_ids)} deleted"
        )
        
        return new_doc_ids, modified_doc_ids, deleted_doc_ids
    
    def update_doc_hash(self, doc_id: str, doc_hash: str):
        """
        Update stored document hash.
        
        Args:
            doc_id: Document ID
            doc_hash: Document hash
        """
        self._doc_hashes[doc_id] = doc_hash
        self._save_tracking_data()
    
    def update_doc_hashes(self, doc_hashes: Dict[str, str]):
        """
        Update multiple document hashes at once.
        
        Args:
            doc_hashes: Dictionary of {doc_id: doc_hash}
        """
        self._doc_hashes.update(doc_hashes)
        self._save_tracking_data()
    
    def remove_doc_hash(self, doc_id: str):
        """
        Remove document hash (for deleted documents).
        
        Args:
            doc_id: Document ID to remove
        """
        if doc_id in self._doc_hashes:
            del self._doc_hashes[doc_id]
            self._save_tracking_data()
    
    def add_content_hash(self, content_hash: str):
        """
        Add content hash to tracking (for chunk-level dedup).
        
        Args:
            content_hash: Content hash string
        """
        self._content_hashes.add(content_hash)
        self._save_tracking_data()
    
    def has_content_hash(self, content_hash: str) -> bool:
        """
        Check if content hash exists (for chunk-level dedup).
        
        Args:
            content_hash: Content hash to check
        
        Returns:
            True if hash exists
        """
        return content_hash in self._content_hashes
    
    def get_doc_hash(self, doc_id: str) -> Optional[str]:
        """
        Get stored document hash.
        
        Args:
            doc_id: Document ID
        
        Returns:
            Document hash or None if not found
        """
        return self._doc_hashes.get(doc_id)
    
    def get_all_doc_ids(self) -> Set[str]:
        """
        Get all tracked document IDs.
        
        Returns:
            Set of document IDs
        """
        return set(self._doc_hashes.keys())
    
    def clear_tracking(self):
        """Clear all tracking data (use with caution)."""
        self._doc_hashes = {}
        self._content_hashes = set()
        self._save_tracking_data()
        logger.warning("[INCREMENTAL] Cleared all tracking data")
