"""
Ingest reporter for generating statistics and sample outputs.

Provides detailed reports on ingestion process including file counts,
chunk statistics, and sample chunks with metadata.
"""

from typing import List, Dict, Any
from datetime import datetime
from langchain_core.documents import Document
import json


class IngestReporter:
    """
    Generate reports on document ingestion process.
    """
    
    def __init__(self):
        """Initialize reporter."""
        self.stats = {
            "total_documents": 0,
            "total_chunks": 0,
            "by_source": {},
            "by_filetype": {},
            "duplicates_merged": 0,
            "processing_time": 0,
            "start_time": None,
            "end_time": None
        }
        
        self.sample_chunks = []
    
    def start_ingestion(self):
        """Mark start of ingestion."""
        self.stats["start_time"] = datetime.now()
    
    def end_ingestion(self):
        """Mark end of ingestion."""
        self.stats["end_time"] = datetime.now()
        if self.stats["start_time"]:
            duration = self.stats["end_time"] - self.stats["start_time"]
            self.stats["processing_time"] = duration.total_seconds()
    
    def add_documents(self, documents: List[Document], source: str = "unknown"):
        """
        Add documents to statistics.
        
        Args:
            documents: List of processed documents
            source: Source type (sharepoint, email, blog)
        """
        self.stats["total_documents"] += len(documents)
        
        # Track by source
        if source not in self.stats["by_source"]:
            self.stats["by_source"][source] = {
                "documents": 0,
                "chunks": 0
            }
        
        self.stats["by_source"][source]["documents"] += len(documents)
        
        # Track by filetype
        for doc in documents:
            filetype = doc.metadata.get("filetype", "unknown")
            if filetype not in self.stats["by_filetype"]:
                self.stats["by_filetype"][filetype] = 0
            self.stats["by_filetype"][filetype] += 1
    
    def add_chunks(self, chunks: List[Document], source: str = "unknown"):
        """
        Add chunks to statistics.
        
        Args:
            chunks: List of chunk documents
            source: Source type
        """
        self.stats["total_chunks"] += len(chunks)
        
        # Track chunks by source
        if source not in self.stats["by_source"]:
            self.stats["by_source"][source] = {
                "documents": 0,
                "chunks": 0
            }
        
        self.stats["by_source"][source]["chunks"] += len(chunks)
        
        # Store sample chunks (first 5)
        if len(self.sample_chunks) < 5:
            remaining_slots = 5 - len(self.sample_chunks)
            self.sample_chunks.extend(chunks[:remaining_slots])
    
    def add_deduplication_stats(self, dedup_stats: Dict[str, int]):
        """
        Add deduplication statistics.
        
        Args:
            dedup_stats: Statistics from deduplication process
        """
        self.stats["duplicates_merged"] += dedup_stats.get("duplicates_found", 0)
    
    def add_graph_stats(self, graph_stats: Dict[str, int]):
        """
        Add graph relationship statistics.
        
        Args:
            graph_stats: Statistics from graph store
        """
        self.stats["graph_relationships"] = graph_stats
    
    def generate_report(self) -> str:
        """
        Generate formatted ingestion report.
        
        Returns:
            Formatted report string
        """
        report_lines = []
        report_lines.append("=" * 80)
        report_lines.append("INGESTION REPORT")
        report_lines.append("=" * 80)
        report_lines.append("")
        
        # Timestamp
        if self.stats["end_time"]:
            report_lines.append(f"Completed: {self.stats['end_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            report_lines.append(f"Processing Time: {self.stats['processing_time']:.2f} seconds")
        report_lines.append("")
        
        # Overall statistics
        report_lines.append("OVERALL STATISTICS")
        report_lines.append("-" * 80)
        report_lines.append(f"Total Documents Processed: {self.stats['total_documents']}")
        report_lines.append(f"Total Chunks Created: {self.stats['total_chunks']}")
        report_lines.append(f"Duplicates Merged: {self.stats['duplicates_merged']}")
        report_lines.append("")
        
        # By source
        if self.stats["by_source"]:
            report_lines.append("BY SOURCE")
            report_lines.append("-" * 80)
            for source, counts in self.stats["by_source"].items():
                report_lines.append(f"  {source.upper()}:")
                report_lines.append(f"    Documents: {counts['documents']}")
                report_lines.append(f"    Chunks: {counts['chunks']}")
            report_lines.append("")
        
        # By filetype
        if self.stats["by_filetype"]:
            report_lines.append("BY FILE TYPE")
            report_lines.append("-" * 80)
            for filetype, count in sorted(self.stats["by_filetype"].items()):
                report_lines.append(f"  {filetype.upper()}: {count}")
            report_lines.append("")
        
        # Graph relationships
        if "graph_relationships" in self.stats:
            report_lines.append("GRAPH RELATIONSHIPS")
            report_lines.append("-" * 80)
            for key, value in self.stats["graph_relationships"].items():
                formatted_key = key.replace("_", " ").title()
                report_lines.append(f"  {formatted_key}: {value}")
            report_lines.append("")
        
        # Chunking statistics
        if self.stats["total_chunks"] > 0:
            report_lines.append("CHUNKING STATISTICS")
            report_lines.append("-" * 80)
            
            # Calculate average chunks per document
            if self.stats["total_documents"] > 0:
                avg_chunks = self.stats["total_chunks"] / self.stats["total_documents"]
                report_lines.append(f"  Average Chunks per Document: {avg_chunks:.2f}")
            
            # Calculate average chunk size and token count
            total_chars = 0
            total_tokens = 0
            chunks_with_stats = 0
            
            for chunk in self.sample_chunks:
                if "token_count" in chunk.metadata:
                    total_tokens += chunk.metadata["token_count"]
                    chunks_with_stats += 1
                # Support both LangChain Document (page_content) and WeaviateChunk (content)
                content = getattr(chunk, 'content', getattr(chunk, 'page_content', ''))
                total_chars += len(content)
            
            if chunks_with_stats > 0:
                avg_tokens = total_tokens / chunks_with_stats
                report_lines.append(f"  Average Chunk Size (tokens): {avg_tokens:.0f}")
            
            if len(self.sample_chunks) > 0:
                avg_chars = total_chars / len(self.sample_chunks)
                report_lines.append(f"  Average Chunk Size (characters): {avg_chars:.0f}")
            
            report_lines.append("")
        
        # Sample chunks
        if self.sample_chunks:
            report_lines.append("SAMPLE CHUNKS (First 5)")
            report_lines.append("=" * 80)
            report_lines.append("")
            
            for i, chunk in enumerate(self.sample_chunks[:5], 1):
                report_lines.append(f"CHUNK {i}:")
                report_lines.append("-" * 80)
                
                # Metadata
                report_lines.append("Metadata:")
                metadata = chunk.metadata
                for key in ["source", "filetype", "filename", "url", "page_number", 
                           "chunk_index", "total_chunks", "token_count", "char_range"]:
                    if key in metadata:
                        report_lines.append(f"  {key}: {metadata[key]}")
                
                report_lines.append("")
                
                # Content preview
                # Support both LangChain Document (page_content) and WeaviateChunk (content)
                content = getattr(chunk, 'content', getattr(chunk, 'page_content', ''))
                content_preview = content[:200]
                if len(content) > 200:
                    content_preview += "..."
                
                report_lines.append("Content Preview:")
                report_lines.append(content_preview)
                report_lines.append("")
        
        report_lines.append("=" * 80)
        
        return "\n".join(report_lines)
    
    def save_report(self, output_path: str = "ingest_report.txt"):
        """
        Save report to file.
        
        Args:
            output_path: Path to save report
        """
        report = self.generate_report()
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"[OK] Report saved to: {output_path}")
    
    def save_json(self, output_path: str = "ingest_report.json"):
        """
        Save statistics as JSON.
        
        Args:
            output_path: Path to save JSON
        """
        # Convert datetime objects to strings
        stats_copy = self.stats.copy()
        if stats_copy["start_time"]:
            stats_copy["start_time"] = stats_copy["start_time"].isoformat()
        if stats_copy["end_time"]:
            stats_copy["end_time"] = stats_copy["end_time"].isoformat()
        
        # Add sample chunks as serializable data
        # Support both LangChain Document (page_content) and WeaviateChunk (content)
        stats_copy["sample_chunks"] = [
            {
                "metadata": chunk.metadata,
                "content_preview": (getattr(chunk, 'content', getattr(chunk, 'page_content', '')))[:200]
            }
            for chunk in self.sample_chunks[:5]
        ]
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(stats_copy, f, indent=2)
        
        print(f"[OK] JSON report saved to: {output_path}")
    
    def print_report(self):
        """Print report to console."""
        print(self.generate_report())


def generate_ingestion_report(
    documents: List[Document],
    chunks: List[Document],
    dedup_stats: Dict[str, int] = None,
    graph_stats: Dict[str, int] = None,
    processing_time: float = 0
) -> str:
    """
    Convenience function to generate ingestion report.
    
    Args:
        documents: Original documents
        chunks: Chunked documents
        dedup_stats: Deduplication statistics
        graph_stats: Graph relationship statistics
        processing_time: Processing time in seconds
    
    Returns:
        Formatted report string
    """
    reporter = IngestReporter()
    reporter.stats["processing_time"] = processing_time
    reporter.stats["end_time"] = datetime.now()
    
    # Add documents and chunks
    for doc in documents:
        source = doc.metadata.get("source", "unknown")
        reporter.add_documents([doc], source)
    
    for chunk in chunks:
        source = chunk.metadata.get("source", "unknown")
        reporter.add_chunks([chunk], source)
    
    # Add dedup and graph stats
    if dedup_stats:
        reporter.add_deduplication_stats(dedup_stats)
    
    if graph_stats:
        reporter.add_graph_stats(graph_stats)
    
    return reporter.generate_report()

