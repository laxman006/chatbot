"""
Enhanced helper functions for building vectorstore with new features.

Integrates semantic chunking, deduplication, graph storage, and unified metadata.
"""

from typing import List, Optional
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma

from app.metadata_schema import UnifiedMetadata, create_chunk_metadata
from app.chunking_strategy import SemanticChunker
from app.deduplication import Deduplicator
from app.graph_store import get_graph_store
from app.ingest_reporter import IngestReporter
from app.unstructured_processor import UnstructuredProcessor

from config import (
    CHROMA_DB_PATH,
    CHUNK_TARGET_TOKENS, CHUNK_OVERLAP_TOKENS, CHUNK_MIN_TOKENS,
    ENABLE_DEDUPLICATION, DEDUP_THRESHOLD,
    ENABLE_UNSTRUCTURED, ENABLE_OCR, OCR_LANGUAGE,
    ENABLE_GRAPH_STORAGE, GRAPH_DB_PATH,
    JIRA_CHUNK_TARGET_TOKENS, JIRA_CHUNK_OVERLAP_TOKENS, JIRA_CHUNK_MIN_TOKENS
)

import os
import uuid


class EnhancedVectorstoreBuilder:
    """
    Build vectorstore with enhanced ingestion pipeline.
    """
    
    def __init__(self):
        """Initialize builder with all components."""
        # Initialize chunker
        self.chunker = SemanticChunker(
            target_tokens=CHUNK_TARGET_TOKENS,
            overlap_tokens=CHUNK_OVERLAP_TOKENS,
            min_tokens=CHUNK_MIN_TOKENS
        )
        
        # Initialize deduplicator
        self.deduplicator = None
        if ENABLE_DEDUPLICATION:
            self.deduplicator = Deduplicator(threshold=DEDUP_THRESHOLD)
        
        # Initialize unstructured processor
        self.unstructured_processor = None
        if ENABLE_UNSTRUCTURED:
            self.unstructured_processor = UnstructuredProcessor(
                enable_ocr=ENABLE_OCR,
                ocr_language=OCR_LANGUAGE
            )
        
        # Initialize graph store
        self.graph_store = None
        if ENABLE_GRAPH_STORAGE:
            self.graph_store = get_graph_store(GRAPH_DB_PATH)
        
        # Initialize reporter
        self.reporter = IngestReporter()
    
    def process_documents(
        self,
        raw_docs: List[Document],
        source_type: str = "unknown"
    ) -> List[Document]:
        """
        Process raw documents through enhanced pipeline.
        
        Steps:
        1. Add unified metadata and doc_id
        2. Chunk semantically (field-aware for Jira tickets)
        3. Deduplicate (if enabled)
        4. Store graph relationships (if enabled)
        
        Args:
            raw_docs: Raw documents from source
            source_type: Source type (sharepoint, email, blog, jira)
        
        Returns:
            Processed and chunked documents
        """
        if not raw_docs:
            return []
        
        print(f"\n[*] Processing {len(raw_docs)} documents from {source_type}...")
        
        # Step 1: Ensure all documents have doc_id
        for doc in raw_docs:
            if "doc_id" not in doc.metadata:
                doc.metadata["doc_id"] = str(uuid.uuid4())
            if "source" not in doc.metadata:
                doc.metadata["source"] = source_type
        
        self.reporter.add_documents(raw_docs, source_type)
        
        # Step 2: Field-aware chunking for Jira tickets, standard chunking for others
        if source_type == "jira":
            chunks = self._chunk_jira_documents(raw_docs)
            print(f"[OK] Created {len(chunks)} field-aware chunks for Jira tickets")
        else:
            # Standard semantic chunking for other sources
            print(f"[*] Chunking with semantic strategy (target={CHUNK_TARGET_TOKENS} tokens)...")
            chunks = self.chunker.chunk_documents(raw_docs)
            print(f"[OK] Created {len(chunks)} chunks")
        
        # Add chunk_id to each chunk
        for chunk in chunks:
            if "chunk_id" not in chunk.metadata:
                chunk.metadata["chunk_id"] = str(uuid.uuid4())
        
        self.reporter.add_chunks(chunks, source_type)
        
        # Step 3: Deduplication
        if self.deduplicator:
            print(f"[*] Running deduplication (threshold={DEDUP_THRESHOLD})...")
            chunks, dedup_stats = self.deduplicator.deduplicate_within_batch(chunks)
            print(f"[OK] Deduplication: {dedup_stats['duplicates_found']} duplicates found, {len(chunks)} unique chunks")
            self.reporter.add_deduplication_stats(dedup_stats)
        
        # Step 4: Store graph relationships
        if self.graph_store:
            print(f"[*] Storing graph relationships...")
            self._store_graph_relationships(raw_docs, chunks)
            graph_stats = self.graph_store.get_stats()
            self.reporter.add_graph_stats(graph_stats)
            print(f"[OK] Graph relationships stored")
        
        return chunks
    
    def _chunk_jira_documents(self, docs: List[Document]) -> List[Document]:
        """
        Field-aware chunking for Jira tickets.
        
        Strategy:
        - Summary: No chunking (single chunk)
        - Root Cause: No chunking (NEVER split - critical section)
        - Comments: No chunking (one chunk per comment)
        - AI Suggestions: No chunking (single chunk)
        - Description: Semantic chunking only (400-500 tokens)
        
        This preserves field integrity and improves retrieval accuracy.
        """
        chunks = []
        
        # Jira-specific chunker with smaller size (400-600 tokens)
        jira_chunker = SemanticChunker(
            target_tokens=JIRA_CHUNK_TARGET_TOKENS,
            overlap_tokens=JIRA_CHUNK_OVERLAP_TOKENS,
            min_tokens=JIRA_CHUNK_MIN_TOKENS
        )
        
        for doc in docs:
            section = doc.metadata.get("section", "unknown")
            section_priority = doc.metadata.get("section_priority", "medium")
            
            # Never chunk these sections - keep them intact
            if section in ["summary", "root_cause", "comment", "ai_suggestions"]:
                chunks.append(doc)
                continue
            
            # Only chunk Description section semantically
            if section == "description":
                # Use semantic chunking for description (400-500 tokens)
                description_chunks = jira_chunker.chunk_documents([doc])
                # Preserve section metadata in all chunks
                for chunk in description_chunks:
                    chunk.metadata["section"] = "description"
                    chunk.metadata["section_priority"] = "high"
                    # Preserve ticket metadata
                    for key in ["ticket_key", "ticket_summary", "combination", "root_cause"]:
                        if key in doc.metadata:
                            chunk.metadata[key] = doc.metadata[key]
                chunks.extend(description_chunks)
            else:
                # Unknown section - keep as-is
                chunks.append(doc)
        
        return chunks
    
    def _store_graph_relationships(
        self,
        documents: List[Document],
        chunks: List[Document]
    ):
        """Store document-chunk relationships in graph store."""
        if not self.graph_store:
            return
        
        # Store documents
        for doc in documents:
            doc_id = doc.metadata.get("doc_id")
            if not doc_id:
                continue
            
            self.graph_store.add_document(
                doc_id=doc_id,
                source=doc.metadata.get("source", "unknown"),
                url=doc.metadata.get("url", ""),
                filename=doc.metadata.get("filename", ""),
                filetype=doc.metadata.get("filetype", ""),
                metadata=doc.metadata
            )
        
        # Store chunks and relationships
        for chunk in chunks:
            chunk_id = chunk.metadata.get("chunk_id")
            doc_id = chunk.metadata.get("doc_id")
            
            if not chunk_id or not doc_id:
                continue
            
            # Store chunk
            self.graph_store.add_chunk(
                chunk_id=chunk_id,
                doc_id=doc_id,
                chunk_index=chunk.metadata.get("chunk_index", 0),
                char_range=chunk.metadata.get("char_range", ""),
                token_count=chunk.metadata.get("token_count", 0),
                metadata=chunk.metadata
            )
            
            # Store DOCUMENT_CONTAINS_CHUNK relationship
            self.graph_store.add_relationship(
                from_id=doc_id,
                to_id=chunk_id,
                rel_type="DOCUMENT_CONTAINS_CHUNK"
            )
        
        # Store email thread relationships (if applicable)
        for doc in documents:
            if doc.metadata.get("source") == "email":
                in_reply_to = doc.metadata.get("in_reply_to")
                if in_reply_to:
                    doc_id = doc.metadata.get("doc_id")
                    self.graph_store.add_relationship(
                        from_id=doc_id,
                        to_id=in_reply_to,
                        rel_type="EMAIL_REPLIES_TO",
                        metadata={"thread_id": doc.metadata.get("thread_id")}
                    )
    
    def build_vectorstore(
        self,
        all_chunks: List[Document],
        persist_directory: str = CHROMA_DB_PATH
    ) -> Chroma:
        """
        Build ChromaDB vectorstore from processed chunks.
        Supports incremental builds - loads existing vectorstore if available.
        
        Args:
            all_chunks: All processed chunks
            persist_directory: Directory to persist vectorstore
        
        Returns:
            ChromaDB vectorstore instance
        """
        print(f"\n[*] Building vectorstore with {len(all_chunks)} chunks...")
        
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Convert metadata to ChromaDB-compatible format
        for chunk in all_chunks:
            # Ensure all metadata values are compatible
            clean_metadata = {}
            for key, value in chunk.metadata.items():
                if isinstance(value, (str, int, float, bool)):
                    clean_metadata[key] = value
                elif value is None:
                    continue
                else:
                    clean_metadata[key] = str(value)
            chunk.metadata = clean_metadata
        
        # STEP 1: Check if vectorstore exists - load and append instead of recreating
        if os.path.exists(persist_directory):
            print("[*] Loading existing vectorstore for incremental update...")
            try:
                vectorstore = Chroma(
                    persist_directory=persist_directory,
                    embedding_function=embeddings,
                    collection_metadata={
                        "hnsw:space": "cosine",
                        "hnsw:construction_ef": 200,
                        "hnsw:search_ef": 100,
                        "hnsw:M": 48,
                    }
                )
                
                # STEP 2: Prevent duplicate blog embeddings
                print("[*] Checking for duplicate blog posts...")
                existing_slugs = set()
                existing_urls = set()
                
                try:
                    existing_docs = vectorstore.get(include=["metadatas"])
                    for meta in existing_docs.get("metadatas", []):
                        slug = meta.get("post_slug")
                        url = meta.get("post_url")
                        if slug:
                            existing_slugs.add(slug)
                        if url:
                            existing_urls.add(url)
                    print(f"[INFO] Found {len(existing_slugs)} existing blog posts in vectorstore")
                except Exception as e:
                    print(f"[WARN] Could not check existing blogs: {e}")
                
                # Filter out duplicates
                new_chunks = []
                duplicates = 0
                for chunk in all_chunks:
                    slug = chunk.metadata.get("post_slug")
                    url = chunk.metadata.get("post_url")
                    # Check both slug and URL to be safe
                    if (slug and slug in existing_slugs) or (url and url in existing_urls):
                        duplicates += 1
                    else:
                        new_chunks.append(chunk)
                        # Track what we're adding
                        if slug:
                            existing_slugs.add(slug)
                        if url:
                            existing_urls.add(url)
                
                if duplicates > 0:
                    print(f"[INFO] Skipping {duplicates} duplicate blog posts")
                
                if new_chunks:
                    print(f"[*] Adding {len(new_chunks)} new chunks to existing vectorstore...")
                    vectorstore.add_documents(new_chunks)
                    print(f"[OK] Successfully added {len(new_chunks)} new chunks")
                else:
                    print("[INFO] No new chunks to add - all are already in vectorstore")
                
                total_count = vectorstore._collection.count()
                print(f"[OK] Vectorstore updated with HNSW graph indexing")
                print(f"[OK] Total chunks in vectorstore: {total_count}")
                
                return vectorstore
                
            except Exception as e:
                print(f"[WARN] Failed to load existing vectorstore: {e}")
                print("[*] Creating new vectorstore...")
        
        # Create new vectorstore if it doesn't exist or loading failed
        print("[*] Creating new vectorstore...")
        vectorstore = Chroma.from_documents(
            all_chunks,
            embeddings,
            persist_directory=persist_directory,
            collection_metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200,
                "hnsw:search_ef": 100,
                "hnsw:M": 48,
            }
        )
        
        print(f"[OK] Vectorstore created with HNSW graph indexing")
        print(f"[OK] Total chunks in vectorstore: {vectorstore._collection.count()}")
        
        return vectorstore
    
    def get_report(self) -> str:
        """Get ingestion report."""
        self.reporter.end_ingestion()
        return self.reporter.generate_report()
    
    def save_reports(self, txt_path: str = None, json_path: str = None):
        """Save ingestion reports."""
        self.reporter.end_ingestion()
        
        if txt_path:
            self.reporter.save_report(txt_path)
        
        if json_path:
            self.reporter.save_json(json_path)


def build_enhanced_vectorstore(
    sharepoint_docs: List[Document] = None,
    outlook_docs: List[Document] = None,
    blog_docs: List[Document] = None,
    persist_directory: str = CHROMA_DB_PATH
) -> tuple[Chroma, str]:
    """
    Build vectorstore with enhanced pipeline from multiple sources.
    
    Args:
        sharepoint_docs: SharePoint documents
        outlook_docs: Outlook email documents
        blog_docs: Blog post documents
        persist_directory: Directory to persist vectorstore
    
    Returns:
        Tuple of (vectorstore, report)
    """
    builder = EnhancedVectorstoreBuilder()
    builder.reporter.start_ingestion()
    
    all_chunks = []
    
    # Process SharePoint documents
    if sharepoint_docs:
        chunks = builder.process_documents(sharepoint_docs, "sharepoint")
        all_chunks.extend(chunks)
    
    # Process Outlook documents
    if outlook_docs:
        chunks = builder.process_documents(outlook_docs, "email")
        all_chunks.extend(chunks)
    
    # Process blog documents
    if blog_docs:
        chunks = builder.process_documents(blog_docs, "blog")
        all_chunks.extend(chunks)
    
    # Build vectorstore
    if all_chunks:
        vectorstore = builder.build_vectorstore(all_chunks, persist_directory)
    else:
        print("[WARNING] No documents to process")
        vectorstore = None
    
    # Get report
    report = builder.get_report()
    
    return vectorstore, report

