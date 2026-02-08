# Image extraction from PPTX is disabled; only slide text is extracted.
import os
import json
import tempfile
import base64
from typing import List, Dict, Any, Optional
from pathlib import Path
from langchain_core.documents import Document
from datetime import datetime

# Try to import python-pptx for native extraction
try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False

# Try to import unstructured as fallback
try:
    from app.unstructured_processor import UnstructuredProcessor
    UNSTRUCTURED_AVAILABLE = True
except ImportError:
    UNSTRUCTURED_AVAILABLE = False


class PPTXProcessor:
    """
    Process PowerPoint files separately from main ingestion pipeline.
    
    Extracts slide content and stores it separately (JSON/text/optional vectorstore).
    """
    
    def __init__(self, output_dir: str = "./data/pptx_extracted"):
        """
        Initialize PPTX processor.
        
        Args:
            output_dir: Directory to store extracted PPTX content
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        if not PPTX_AVAILABLE and not UNSTRUCTURED_AVAILABLE:
            print("[WARNING] Neither python-pptx nor unstructured available. PPTX extraction will be limited.")
    
    def extract_with_pptx_library(self, pptx_path: str) -> List[Dict[str, Any]]:
        """
        Extract text from PPTX using python-pptx library (native, fast).
        
        Args:
            pptx_path: Path to PPTX file
            
        Returns:
            List of slide dictionaries with extracted content
        """
        if not PPTX_AVAILABLE:
            return []
        
        try:
            prs = Presentation(pptx_path)
            slides = []
            
            for i, slide in enumerate(prs.slides):
                slide_text_parts = []
                slide_notes = []
                slide_images = []
                slide_title = f"Slide {i+1}"
                
                # Extract content from shapes
                for shape in slide.shapes:
                    # 1. Text extraction
                    if hasattr(shape, "text") and shape.text.strip():
                        # Check if it's a title or content
                        if hasattr(shape, "is_placeholder") and shape.is_placeholder:
                            if shape.placeholder_format.idx == 0:  # Title placeholder
                                slide_title = shape.text.strip()
                                slide_text_parts.insert(0, f"# {slide_title}")
                            else:
                                slide_text_parts.append(shape.text.strip())
                        else:
                            slide_text_parts.append(shape.text.strip())
                    
                    # Image extraction disabled: only slide text is used for ingestion

                # Extract notes if available
                if hasattr(slide, "has_notes_slide") and slide.has_notes_slide:
                    notes_slide = slide.notes_slide
                    if notes_slide and notes_slide.notes_text_frame:
                        slide_notes.append(notes_slide.notes_text_frame.text)
                
                # Combine slide content
                slide_content = "\n".join(slide_text_parts)
                notes_content = "\n".join(slide_notes)
                
                slides.append({
                    "slide_number": i + 1,
                    "title": slide_title,
                    "content": slide_content,
                    "notes": notes_content if notes_content else None,
                    "images": slide_images,
                    "has_content": bool(slide_content.strip()) or bool(slide_images)
                })
            
            return slides
            
        except Exception as e:
            print(f"[ERROR] Failed to extract with python-pptx: {e}")
            return []
    
    def extract_with_unstructured(self, pptx_path: str) -> List[Dict[str, Any]]:
        """
        Extract text from PPTX using Unstructured library (fallback).
        
        Args:
            pptx_path: Path to PPTX file
            
        Returns:
            List of slide dictionaries with extracted content
        """
        if not UNSTRUCTURED_AVAILABLE:
            return []
        
        try:
            processor = UnstructuredProcessor()
            documents = processor.process_pptx(pptx_path)
            
            slides = []
            for doc in documents:
                slide_num = doc.metadata.get("page_number", len(slides) + 1)
                slides.append({
                    "slide_number": slide_num,
                    "content": doc.page_content,
                    "notes": None,
                    "has_content": bool(doc.page_content.strip())
                })
            
            return slides
            
        except Exception as e:
            print(f"[ERROR] Failed to extract with unstructured: {e}")
            return []
    
    def extract_pptx(self, pptx_path: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Extract content from a PPTX file.
        
        Args:
            pptx_path: Path to PPTX file
            metadata: Additional metadata to include
            
        Returns:
            Dictionary with extracted content and metadata
        """
        pptx_path_obj = Path(pptx_path)
        if not pptx_path_obj.exists():
            print(f"[ERROR] PPTX file not found: {pptx_path}")
            return None
        
        # Try native extraction first, fallback to unstructured
        slides = self.extract_with_pptx_library(pptx_path)
        if not slides:
            print(f"[INFO] Trying unstructured fallback for {pptx_path_obj.name}")
            slides = self.extract_with_unstructured(pptx_path)
        
        if not slides:
            print(f"[WARNING] Could not extract content from {pptx_path_obj.name}")
            return None
        
        # Combine all slide content for summary
        all_content = [
            f"\n\n--- Slide {slide['slide_number']} ---\n{slide['content']}"
            for slide in slides if slide["has_content"]
        ]
        combined_content = "\n".join(all_content)
        
        result = {
            "file_name": pptx_path_obj.name,
            "file_path": str(pptx_path_obj),
            "extraction_date": datetime.now().isoformat(),
            "total_slides": len(slides),
            "slides_with_content": sum(1 for s in slides if s["has_content"]),
            "slides": slides,
            "combined_content": combined_content,
            "metadata": metadata or {}
        }
        
        return result
    
    def save_extraction(self, extraction_result: Dict[str, Any], format: str = "json") -> str:
        """
        Save extracted PPTX content to file.
        
        Args:
            extraction_result: Result from extract_pptx()
            format: Output format ("json" or "text")
            
        Returns:
            Path to saved file
        """
        if not extraction_result:
            return None
        
        file_name = Path(extraction_result["file_name"]).stem
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format == "json":
            output_file = self.output_dir / f"{file_name}_{timestamp}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(extraction_result, f, indent=2, ensure_ascii=False)
        elif format == "text":
            output_file = self.output_dir / f"{file_name}_{timestamp}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(f"File: {extraction_result['file_name']}\n")
                f.write(f"Total Slides: {extraction_result['total_slides']}\n")
                f.write(f"Extraction Date: {extraction_result['extraction_date']}\n")
                f.write("\n" + "="*80 + "\n\n")
                f.write(extraction_result["combined_content"])
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        print(f"[OK] Saved PPTX extraction to: {output_file}")
        return str(output_file)
    
    def process_pptx_from_bytes(self, pptx_bytes: bytes, file_name: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Process PPTX file from bytes (e.g., downloaded from SharePoint).
        
        Args:
            pptx_bytes: PPTX file content as bytes
            file_name: Original file name
            metadata: Additional metadata
            
        Returns:
            Dictionary with extracted content
        """
        # Save to temp file
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pptx") as tmp_file:
                tmp_file.write(pptx_bytes)
                tmp_path = tmp_file.name
            
            # Extract content
            result = self.extract_pptx(tmp_path, metadata)
            return result
            
        finally:
            # Clean up temp file
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass
    
    def batch_extract_directory(self, directory: str) -> List[Dict[str, Any]]:
        """
        Extract all PPTX files from a directory.
        
        Args:
            directory: Directory path containing PPTX files
            
        Returns:
            List of extraction results
        """
        directory_path = Path(directory)
        if not directory_path.exists():
            print(f"[ERROR] Directory not found: {directory}")
            return []
        
        pptx_files = list(directory_path.rglob("*.pptx"))
        print(f"[*] Found {len(pptx_files)} PPTX files in {directory}")
        
        results = []
        for pptx_file in pptx_files:
            print(f"[*] Processing: {pptx_file.name}")
            result = self.extract_pptx(str(pptx_file))
            if result:
                results.append(result)
                # Auto-save extraction
                self.save_extraction(result, format="json")
        
        return results


def extract_pptx_from_sharepoint_file(
    file_bytes: bytes,
    file_name: str,
    metadata: Dict[str, Any],
    output_dir: str = "./data/pptx_extracted",
    save_to_file: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Convenience function to extract PPTX from SharePoint file bytes.
    
    Args:
        file_bytes: PPTX file content
        file_name: File name
        metadata: SharePoint metadata
        output_dir: Output directory for extracted content
        save_to_file: Whether to save extraction to file (default: False for production)
        
    Returns:
        Extraction result dictionary or None
    """
    processor = PPTXProcessor(output_dir=output_dir)
    result = processor.process_pptx_from_bytes(file_bytes, file_name, metadata)
    
    if result and save_to_file:
        # Only save if explicitly requested
        processor.save_extraction(result, format="json")
    
    return result

