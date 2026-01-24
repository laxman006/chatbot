"""
Graph store for document relationships using SQLite.

Stores document-chunk relationships, email thread relationships,
and prepares for future entity relationships.
"""

import sqlite3
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import os


class GraphStore:
    """
    SQLite-based graph store for document relationships.
    """
    
    def __init__(self, db_path: str = "./data/graph_relations.db"):
        """
        Initialize graph store.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # Initialize database
        # check_same_thread=False allows connection to be used from multiple threads
        # SQLite handles thread safety internally with proper locking
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Enable dict-like access
        self.create_tables()
    
    def create_tables(self):
        """Create database tables for graph storage."""
        cursor = self.conn.cursor()
        
        # Documents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                url TEXT,
                filename TEXT,
                filetype TEXT,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id TEXT PRIMARY KEY,
                doc_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                embedding_id TEXT,
                char_range TEXT,
                token_count INTEGER,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (doc_id) REFERENCES documents(doc_id)
            )
        """)
        
        # Relationships table (generic)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS relationships (
                rel_id INTEGER PRIMARY KEY AUTOINCREMENT,
                from_id TEXT NOT NULL,
                to_id TEXT NOT NULL,
                rel_type TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(from_id, to_id, rel_type)
            )
        """)
        
        # Entities table (for future NER)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entities (
                entity_id TEXT PRIMARY KEY,
                entity_name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                metadata_json TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_from ON relationships(from_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_to ON relationships(to_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_relationships_type ON relationships(rel_type)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source)
        """)
        
        self.conn.commit()
    
    def add_document(
        self,
        doc_id: str,
        source: str,
        url: str = "",
        filename: str = "",
        filetype: str = "",
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Add or update a document.
        
        Args:
            doc_id: Unique document identifier
            source: Source type (sharepoint, email, blog)
            url: Document URL
            filename: Document filename
            filetype: File type
            metadata: Additional metadata as dict
        
        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()
            metadata_json = json.dumps(metadata or {})
            
            cursor.execute("""
                INSERT OR REPLACE INTO documents 
                (doc_id, source, url, filename, filetype, metadata_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (doc_id, source, url, filename, filetype, metadata_json, datetime.now().isoformat()))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to add document {doc_id}: {e}")
            return False
    
    def add_chunk(
        self,
        chunk_id: str,
        doc_id: str,
        chunk_index: int,
        embedding_id: str = "",
        char_range: str = "",
        token_count: int = 0,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Add a chunk.
        
        Args:
            chunk_id: Unique chunk identifier
            doc_id: Parent document ID
            chunk_index: Index of chunk in document
            embedding_id: ID in vector store (optional)
            char_range: Character range (e.g., "0-1000")
            token_count: Number of tokens
            metadata: Additional metadata
        
        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()
            metadata_json = json.dumps(metadata or {})
            
            cursor.execute("""
                INSERT OR REPLACE INTO chunks
                (chunk_id, doc_id, chunk_index, embedding_id, char_range, token_count, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (chunk_id, doc_id, chunk_index, embedding_id, char_range, token_count, metadata_json))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to add chunk {chunk_id}: {e}")
            return False
    
    def add_relationship(
        self,
        from_id: str,
        to_id: str,
        rel_type: str,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Add a relationship between two entities.
        
        Args:
            from_id: Source entity ID
            to_id: Target entity ID
            rel_type: Relationship type (DOCUMENT_CONTAINS_CHUNK, EMAIL_REPLIES_TO, etc.)
            metadata: Additional metadata
        
        Returns:
            True if successful
        """
        try:
            cursor = self.conn.cursor()
            metadata_json = json.dumps(metadata or {})
            
            cursor.execute("""
                INSERT OR IGNORE INTO relationships
                (from_id, to_id, rel_type, metadata_json)
                VALUES (?, ?, ?, ?)
            """, (from_id, to_id, rel_type, metadata_json))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to add relationship {from_id}->{to_id}: {e}")
            return False
    
    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_document_chunks(self, doc_id: str) -> List[Dict[str, Any]]:
        """Get all chunks for a document."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM chunks WHERE doc_id = ? ORDER BY chunk_index
        """, (doc_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_chunk(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get chunk by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        row = cursor.fetchone()
        
        if row:
            return dict(row)
        return None
    
    def get_relationships(
        self,
        from_id: str = None,
        to_id: str = None,
        rel_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Get relationships matching criteria.
        
        Args:
            from_id: Filter by source ID
            to_id: Filter by target ID
            rel_type: Filter by relationship type
        
        Returns:
            List of matching relationships
        """
        cursor = self.conn.cursor()
        
        query = "SELECT * FROM relationships WHERE 1=1"
        params = []
        
        if from_id:
            query += " AND from_id = ?"
            params.append(from_id)
        
        if to_id:
            query += " AND to_id = ?"
            params.append(to_id)
        
        if rel_type:
            query += " AND rel_type = ?"
            params.append(rel_type)
        
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    
    def get_email_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        """
        Get all emails in a thread.
        
        Args:
            thread_id: Thread/conversation ID
        
        Returns:
            List of documents in thread
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM documents 
            WHERE source = 'email' 
            AND json_extract(metadata_json, '$.thread_id') = ?
            ORDER BY created_at
        """, (thread_id,))
        
        return [dict(row) for row in cursor.fetchall()]
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about graph store."""
        cursor = self.conn.cursor()
        
        stats = {}
        
        # Count documents by source
        cursor.execute("SELECT source, COUNT(*) as count FROM documents GROUP BY source")
        for row in cursor.fetchall():
            stats[f"documents_{row['source']}"] = row['count']
        
        # Total documents
        cursor.execute("SELECT COUNT(*) as count FROM documents")
        stats["total_documents"] = cursor.fetchone()['count']
        
        # Total chunks
        cursor.execute("SELECT COUNT(*) as count FROM chunks")
        stats["total_chunks"] = cursor.fetchone()['count']
        
        # Total relationships
        cursor.execute("SELECT COUNT(*) as count FROM relationships")
        stats["total_relationships"] = cursor.fetchone()['count']
        
        # Relationships by type
        cursor.execute("SELECT rel_type, COUNT(*) as count FROM relationships GROUP BY rel_type")
        for row in cursor.fetchall():
            stats[f"relationships_{row['rel_type']}"] = row['count']
        
        return stats
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document and its chunks."""
        try:
            cursor = self.conn.cursor()
            
            # Delete chunks
            cursor.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            
            # Delete relationships
            cursor.execute("DELETE FROM relationships WHERE from_id = ? OR to_id = ?", (doc_id, doc_id))
            
            # Delete document
            cursor.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to delete document {doc_id}: {e}")
            return False
    
    def clear_all(self) -> bool:
        """Clear all data from graph store."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM relationships")
            cursor.execute("DELETE FROM chunks")
            cursor.execute("DELETE FROM documents")
            cursor.execute("DELETE FROM entities")
            self.conn.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to clear graph store: {e}")
            return False
    
    def close(self):
        """Close database connection."""
        self.conn.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Singleton instance
_graph_store_instance = None

def get_graph_store(db_path: str = "./data/graph_relations.db") -> GraphStore:
    """Get or create singleton graph store instance."""
    global _graph_store_instance
    
    if _graph_store_instance is None:
        _graph_store_instance = GraphStore(db_path)
    
    return _graph_store_instance

