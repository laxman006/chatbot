import os
import pandas as pd
from typing import List, Dict
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# Try to import openpyxl for Excel support
try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False
    print("openpyxl not available, Excel processing may be limited")

# Try to import xlrd for older Excel formats
try:
    import xlrd
    XLRD_AVAILABLE = True
except ImportError:
    XLRD_AVAILABLE = False
    print("xlrd not available, older Excel formats (.xls) may not be supported")

def extract_text_from_excel(excel_path: str) -> str:
    """
    Extract text content from an Excel file with enhanced structured format.
    Creates structured entries with explicit field names and natural language summaries
    for better semantic search and query accuracy.
    """
    text_content = []
    
    try:
        # Read all sheets from the Excel file
        excel_file = pd.ExcelFile(excel_path)
        
        # Add file-level metadata for better searchability
        text_content.append(f"Excel file: {os.path.basename(excel_path)}")
        text_content.append("Contains migration features, limitations, and capabilities for different migration paths.\n")
        
        for sheet_name in excel_file.sheet_names:
            try:
                # Read the sheet
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                
                # Add sheet header with migration path context
                text_content.append(f"\n=== Migration Path: {sheet_name} ===\n")
                
                if not df.empty:
                    cols = list(df.columns)
                    
                    # Track section headers (Features Included, Out of Scope, Limitations, etc.)
                    current_section = None
                    
                    # Process each row
                    for index, row in df.iterrows():
                        # Skip completely empty rows
                        if df.iloc[index].isna().all():
                            continue
                        
                        # Extract values (handle different column structures)
                        feature = str(row[cols[0]]) if len(cols) > 0 and pd.notna(row[cols[0]]) else ""
                        description = str(row[cols[1]]) if len(cols) > 1 and pd.notna(row[cols[1]]) else ""
                        status = str(row[cols[2]]) if len(cols) > 2 and pd.notna(row[cols[2]]) else ""
                        
                        # Additional columns if present (for flexibility)
                        additional_info = ""
                        if len(cols) > 3:
                            additional_values = []
                            for i in range(3, len(cols)):
                                if pd.notna(row[cols[i]]):
                                    additional_values.append(f"{cols[i]}: {row[cols[i]]}")
                            if additional_values:
                                additional_info = " | ".join(additional_values)
                        
                        # Check if this is a section header row
                        feature_lower = feature.lower().strip() if feature else ""
                        section_headers = [
                            'features included', 'out of scope features', 'limitations',
                            'feature name', 'feature', 'features', 'capabilities',
                            'supported features', 'unsupported features'
                        ]
                        
                        if feature_lower in section_headers:
                            current_section = feature
                            text_content.append(f"\n## {feature}\n")
                            continue
                        
                        # Skip if no feature name
                        if not feature or feature.strip() == "":
                            continue
                        
                        # Create structured entry with explicit field names
                        entry = f"""
Feature Name: {feature}
"""
                        
                        if description and description.strip():
                            entry += f"Description: {description}\n"
                        
                        if status and status.strip():
                            entry += f"Status: {status}\n"
                        
                        entry += f"Migration Path: {sheet_name}\n"
                        
                        if current_section:
                            entry += f"Category: {current_section}\n"
                        
                        if additional_info:
                            entry += f"Additional Information: {additional_info}\n"
                        
                        # Create natural language summary for better semantic search
                        status_upper = status.upper().strip() if status else ""
                        
                        if status_upper in ['YES', 'NO', 'NA', 'N/A']:
                            if status_upper == "YES":
                                status_text = "is supported"
                            elif status_upper == "NO":
                                status_text = "is not supported"
                            else:
                                status_text = "is not applicable"
                            
                            summary = f"For {sheet_name} migration: {feature} {status_text}."
                            if description and description.strip():
                                summary += f" {description}"
                        else:
                            # If status is not Yes/No/NA, include it as additional details
                            summary = f"For {sheet_name} migration: {feature}."
                            if description and description.strip():
                                summary += f" {description}"
                            if status and status.strip():
                                summary += f" Status or details: {status}"
                        
                        entry += f"Summary: {summary}\n"
                        text_content.append(entry)
                    
                    # Add summary statistics for numeric columns (if any)
                    numeric_cols = df.select_dtypes(include=['number']).columns
                    if len(numeric_cols) > 0:
                        text_content.append(f"\nSummary statistics for numeric columns:\n")
                        for col in numeric_cols:
                            if not df[col].isna().all():
                                stats = df[col].describe()
                                text_content.append(f"{col}: mean={stats.get('mean', 'N/A'):.2f}, "
                                                  f"min={stats.get('min', 'N/A'):.2f}, "
                                                  f"max={stats.get('max', 'N/A'):.2f}\n")
                
            except Exception as e:
                print(f"Error processing sheet '{sheet_name}' in {excel_path}: {e}")
                import traceback
                traceback.print_exc()
                text_content.append(f"\nError reading sheet '{sheet_name}': {str(e)}\n")
        
        return "\n".join(text_content)
        
    except Exception as e:
        print(f"Error reading Excel file {excel_path}: {e}")
        import traceback
        traceback.print_exc()
        return ""

def process_excel_directory(excel_directory: str) -> List[Document]:
    """Process all Excel files in a directory and return as LangChain Documents."""
    documents = []
    
    if not os.path.exists(excel_directory):
        print(f"Excel directory {excel_directory} does not exist")
        return documents
    
    # Supported Excel file extensions
    excel_extensions = ['.xlsx', '.xls']
    excel_files = []
    
    for file in os.listdir(excel_directory):
        if any(file.lower().endswith(ext) for ext in excel_extensions):
            excel_files.append(file)
    
    if not excel_files:
        print(f"No Excel files found in {excel_directory}")
        return documents
    
    print(f"Processing {len(excel_files)} Excel file(s)...")
    
    for excel_file in excel_files:
        excel_path = os.path.join(excel_directory, excel_file)
        print(f"Processing: {excel_file}")
        
        try:
            # Extract text from Excel file
            text = extract_text_from_excel(excel_path)
            source_type = "excel"
            
            if text.strip():
                # Create a document with metadata
                doc = Document(
                    page_content=text,
                    metadata={
                        "source": excel_file,
                        "source_type": source_type,
                        "file_path": excel_path,
                        "file_format": excel_file.split('.')[-1].lower(),
                        "content_type": "excel_data",
                        "searchable_terms": " ".join(text.split()[:20])  # Add first 20 words for better searchability
                    }
                )
                documents.append(doc)
                print(f"Successfully processed {excel_file} ({len(text)} characters)")
            else:
                print(f"Warning: No text extracted from {excel_file}")
                
        except Exception as e:
            print(f"Error processing {excel_file}: {e}")
    
    return documents

def chunk_excel_documents(documents: List[Document], chunk_size: int = 800, chunk_overlap: int = 150) -> List[Document]:
    """
    Split Excel documents into smaller chunks for better retrieval.
    Uses separators optimized for the enhanced structured format.
    """
    if not documents:
        return documents
    
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n\n", "\n\n", "\n=== ", "\n## ", "\n", " | ", " ", ""]  # Better separators for structured Excel data
    )
    
    chunked_docs = []
    for doc in documents:
        chunks = splitter.split_documents([doc])
        # Add metadata to each chunk for better searchability
        for chunk in chunks:
            chunk.metadata.update(doc.metadata)  # Preserve original metadata first
            chunk.metadata.update({
                "chunk_type": "excel_data",
                "searchable_content": " ".join(chunk.page_content.split()[:20]),  # First 20 words for search
                "tag": "excel"  # Tag for chatbot to identify Excel content
            })
        chunked_docs.extend(chunks)
    
    print(f"Split {len(documents)} Excel documents into {len(chunked_docs)} chunks")
    return chunked_docs

def get_excel_summary(excel_path: str) -> Dict:
    """Get a summary of an Excel file's structure."""
    try:
        excel_file = pd.ExcelFile(excel_path)
        summary = {
            "file_name": os.path.basename(excel_path),
            "sheet_count": len(excel_file.sheet_names),
            "sheet_names": excel_file.sheet_names,
            "total_rows": 0,
            "total_columns": 0
        }
        
        for sheet_name in excel_file.sheet_names:
            try:
                df = pd.read_excel(excel_path, sheet_name=sheet_name)
                summary["total_rows"] += len(df)
                summary["total_columns"] = max(summary["total_columns"], len(df.columns))
            except:
                continue
                
        return summary
    except Exception as e:
        return {"error": str(e)}
