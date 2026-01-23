# -*- coding: utf-8 -*-
"""
SharePoint Content Extractor using Microsoft Graph API
More reliable than Selenium for files and folders.
"""

import os
import time
from typing import List, Optional, Set
from urllib.parse import unquote
from langchain_core.documents import Document
import requests
import tempfile

from app.sharepoint_auth import sharepoint_auth
from config import SHAREPOINT_EXCLUDE_FOLDERS, SHAREPOINT_DOWNLOADABLE_FOLDERS

class SharePointGraphExtractor:
    """Extract SharePoint files and folders using Microsoft Graph API."""
    
    def __init__(self):
        self.site_url = os.getenv("SHAREPOINT_SITE_URL", "https://cloudfuzecom.sharepoint.com/sites/DOC360")
        self.graph_base_url = "https://graph.microsoft.com/v1.0"
        self.excluded_folders = SHAREPOINT_EXCLUDE_FOLDERS
        self.downloadable_folders = SHAREPOINT_DOWNLOADABLE_FOLDERS
        
        # Parse site URL to get site ID
        self.site_id = None
        self.drive_id = None
        
        print(f"[*] SharePoint Graph Extractor initialized")
        print(f"   Site URL: {self.site_url}")
        if self.excluded_folders:
            print(f"   Excluded folders: {', '.join(self.excluded_folders)}")
    
    def get_site_id(self) -> Optional[str]:
        """Get the SharePoint site ID from Graph API."""
        if self.site_id:
            return self.site_id
        
        try:
            # Extract hostname and site path from URL
            # Format: https://{hostname}/sites/{sitename}
            from urllib.parse import urlparse
            parsed = urlparse(self.site_url)
            hostname = parsed.netloc  # e.g., cloudfuzecom.sharepoint.com
            path_parts = [p for p in parsed.path.split('/') if p]
            
            # Find 'sites' in path
            if 'sites' in path_parts:
                site_idx = path_parts.index('sites')
                site_name = path_parts[site_idx + 1] if site_idx + 1 < len(path_parts) else None
                
                if site_name:
                    # Construct Graph API URL: sites/{hostname}:/sites/{sitename}
                    site_path = f"/sites/{site_name}"
                    graph_url = f"{self.graph_base_url}/sites/{hostname}:{site_path}"
                    
                    headers = sharepoint_auth.get_headers()
                    response = requests.get(graph_url, headers=headers, timeout=30)
                    
                    if response.status_code == 200:
                        site_data = response.json()
                        self.site_id = site_data.get('id')
                        print(f"[OK] Found site ID: {self.site_id[:50]}...")
                        return self.site_id
                    else:
                        print(f"[ERROR] Failed to get site ID: {response.status_code} - {response.text}")
                        return None
        except Exception as e:
            print(f"[ERROR] Error getting site ID: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def get_drive_id(self) -> Optional[str]:
        """Get the Documents library drive ID."""
        if self.drive_id:
            return self.drive_id
        
        site_id = self.get_site_id()
        if not site_id:
            return None
        
        try:
            # Get the default drive (Documents library)
            graph_url = f"{self.graph_base_url}/sites/{site_id}/drive"
            headers = sharepoint_auth.get_headers()
            
            response = requests.get(graph_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                drive_data = response.json()
                self.drive_id = drive_data.get('id')
                print(f"[OK] Found drive ID: {self.drive_id[:50]}...")
                return self.drive_id
            else:
                print(f"[ERROR] Failed to get drive ID: {response.status_code} - {response.text}")
                return None
        except Exception as e:
            print(f"[ERROR] Error getting drive ID: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def list_items(self, item_id: str = None, folder_path: List[str] = None) -> List[dict]:
        """List files and folders in a SharePoint drive or folder."""
        drive_id = self.get_drive_id()
        if not drive_id:
            return []
        
        try:
            # If item_id is None, list root items, otherwise list folder contents
            if item_id:
                graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{item_id}/children"
            else:
                graph_url = f"{self.graph_base_url}/drives/{drive_id}/root/children"
            
            headers = sharepoint_auth.get_headers()
            response = requests.get(graph_url, headers=headers, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                items = data.get('value', [])
                print(f"   [INFO] Found {len(items)} items in folder: {' > '.join(folder_path) if folder_path else 'Documents'}")
                return items
            else:
                print(f"[ERROR] Failed to list items: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            print(f"[ERROR] Error listing items: {e}")
            return []
    
    def download_file_content(self, item_id: str, file_name: str) -> Optional[str]:
        """Download and extract text content from SharePoint file."""
        drive_id = self.get_drive_id()
        if not drive_id:
            return None
        
        try:
            # Get file content
            graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{item_id}/content"
            headers = sharepoint_auth.get_headers()
            
            response = requests.get(graph_url, headers=headers, timeout=60, stream=True)
            
            if response.status_code == 200:
                # Determine file type from extension
                file_ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else ''
                content_type = response.headers.get('content-type', '')
                
                # Handle different file types
                if file_ext in ['pdf']:
                    # PDF file - use PDF processor
                    tmp_path = None
                    try:
                        import tempfile
                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf')
                        tmp_path = tmp_file.name
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp_file.write(chunk)
                        tmp_file.close()  # Explicitly close before processing
                        
                        from app.pdf_processor import extract_text_from_pdf
                        content = extract_text_from_pdf(tmp_path)
                        return content
                    except Exception as e:
                        print(f"      [WARNING] PDF extraction failed for {file_name}: {e}")
                        return None
                    finally:
                        # Clean up temp file after processing is complete
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                # Wait a bit and retry if file is locked
                                import time
                                time.sleep(0.1)
                                os.unlink(tmp_path)
                            except Exception:
                                pass  # Ignore cleanup errors
                
                elif file_ext in ['doc', 'docx']:
                    # Word document - use DOC processor
                    tmp_path = None
                    try:
                        import tempfile
                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}')
                        tmp_path = tmp_file.name
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp_file.write(chunk)
                        tmp_file.close()  # Explicitly close before processing
                        
                        from app.doc_processor import extract_text_from_docx
                        content = extract_text_from_docx(tmp_path)
                        return content
                    except Exception as e:
                        print(f"      [WARNING] Word extraction failed for {file_name}: {e}")
                        return None
                    finally:
                        # Clean up temp file after processing is complete
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                import time
                                time.sleep(0.1)
                                os.unlink(tmp_path)
                            except Exception:
                                pass  # Ignore cleanup errors
                
                elif file_ext in ['xls', 'xlsx']:
                    # Excel file - use Excel processor
                    tmp_path = None
                    try:
                        import tempfile
                        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f'.{file_ext}')
                        tmp_path = tmp_file.name
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp_file.write(chunk)
                        tmp_file.close()  # Explicitly close before processing
                        
                        from app.excel_processor import extract_text_from_excel
                        content = extract_text_from_excel(tmp_path)
                        return content
                    except Exception as e:
                        print(f"      [WARNING] Excel extraction failed for {file_name}: {e}")
                        return None
                    finally:
                        # Clean up temp file after processing is complete
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                import time
                                time.sleep(0.1)  # Give file handles time to release
                                # Retry deletion up to 3 times
                                for _ in range(3):
                                    try:
                                        os.unlink(tmp_path)
                                        break
                                    except PermissionError:
                                        time.sleep(0.2)
                            except Exception:
                                pass  # Ignore cleanup errors
                
                elif file_ext in ['txt', 'csv', 'json', 'xml', 'html', 'md']:
                    # Text file - read directly
                    try:
                        content = response.text
                        if len(content) > 50:  # Only return if substantial content
                            return content
                    except:
                        return None
                
                else:
                    # Unknown/binary file type - return None (we'll just store metadata)
                    print(f"      [INFO] Skipping binary file content for {file_name} (type: {file_ext})")
                    return None
            else:
                print(f"      [WARNING] Failed to download {file_name}: {response.status_code}")
                return None
        except Exception as e:
            print(f"      [WARNING] Error downloading {file_name}: {e}")
            return None
    
    def extract_from_folder(self, item_id: str = None, folder_path: List[str] = None, visited_ids: Set[str] = None, depth: int = 0) -> List[Document]:
        """Recursively extract documents from SharePoint folders."""
        if visited_ids is None:
            visited_ids = set()
        
        if folder_path is None:
            folder_path = []
        
        # Prevent infinite loops
        folder_key = item_id or "root"
        if folder_key in visited_ids:
            return []
        
        visited_ids.add(folder_key)
        all_documents = []
        
        try:
            folder_name = " > ".join(folder_path) if folder_path else "Documents"
            print(f"\n[*] Depth {depth}: Extracting from: {folder_name}")
            
            # List all items in this folder
            items = self.list_items(item_id, folder_path)
            
            if not items:
                return []
            
            # Process each item
            for item in items:
                item_name = item.get('name', 'Unknown')
                item_id_current = item.get('id')
                item_type = 'folder' if 'folder' in item else 'file'
                web_url = item.get('webUrl', '')
                
                # Check if current folder path should be excluded
                current_folder_path_str = " > ".join(folder_path) if folder_path else "Documents"
                current_folder_path_lower = current_folder_path_str.lower()
                
                # Check if any excluded folder path matches current path
                folder_excluded = False
                for excluded_path in self.excluded_folders:
                    excluded_lower = excluded_path.lower()
                    # Check if excluded path is in current folder path (allows partial matches)
                    if excluded_lower in current_folder_path_lower:
                        folder_excluded = True
                        print(f"   [SKIP] Folder path excluded: {current_folder_path_str} (matched: {excluded_path})")
                        break
                
                if folder_excluded:
                    continue
                
                # Skip call recordings and demo videos
                item_lower = item_name.lower()
                is_call_recording = (
                    'call' in item_lower and 
                    ('recording' in item_lower or 'call' in item_lower)
                )
                is_video = any(item_lower.endswith(f'.{ext}') for ext in ['mp4', 'avi', 'mov', 'wmv', 'mkv'])
                
                if is_call_recording:
                    print(f"   [SKIP] Skipping call recording: {item_name}")
                    continue
                
                if is_video:
                    print(f"   [SKIP] Skipping video file: {item_name}")
                    continue
                
                # Build tag: sharepoint/folder/subfolder
                current_folder_path = folder_path + [item_name] if item_id else [item_name]
                sanitized_path = [f.replace('/', '-').replace('\\', '-').strip() for f in current_folder_path if f.strip()]
                tag = "/".join(["sharepoint"] + sanitized_path)
                
                # Check if it's a file
                if 'file' in item and not 'folder' in item:
                    # It's a file - extract content
                    print(f"   [*] Processing file: {item_name}")
                    
                    # Check if it's a PPTX file and if separate PPTX pipeline is enabled
                    file_ext = item_name.rsplit('.', 1)[-1].lower() if '.' in item_name else ''
                    is_pptx = file_ext in ['ppt', 'pptx']
                    
                    # Handle PPTX files if pipeline is enabled
                    if is_pptx:
                        from config import ENABLE_PPTX_PIPELINE, ENABLE_PPTX_SAVE_FILES, PPTX_OUTPUT_DIR
                        if ENABLE_PPTX_PIPELINE:
                            try:
                                # Download PPTX file bytes
                                drive_id = self.get_drive_id()
                                if drive_id:
                                    graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{item_id_current}/content"
                                    headers = sharepoint_auth.get_headers()
                                    pptx_response = requests.get(graph_url, headers=headers, timeout=60, stream=True)
                                    
                                    if pptx_response.status_code == 200:
                                        pptx_bytes = pptx_response.content
                                        
                                        # Extract PPTX content
                                        from app.pptx_processor import PPTXProcessor
                                        processor = PPTXProcessor(output_dir=PPTX_OUTPUT_DIR)
                                        
                                        # Prepare metadata
                                        pptx_metadata = {
                                            "source": "sharepoint_sales" if "CFSales" in str(self.site_url) else "sharepoint",
                                            "file_name": item_name,
                                            "file_url": web_url,
                                            "folder_path": " > ".join(folder_path) if folder_path else "Documents",
                                            "webUrl": web_url,
                                            "site_url": str(self.site_url)
                                        }
                                        
                                        print(f"      [PPTX] Extracting PPTX: {item_name}")
                                        extraction_result = processor.process_pptx_from_bytes(
                                            pptx_bytes,
                                            item_name,
                                            pptx_metadata
                                        )
                                        
                                        if extraction_result:
                                            print(f"      [OK] PPTX extracted: {extraction_result['total_slides']} slides")
                                            
                                            # Optionally save to file (disabled by default for production)
                                            if ENABLE_PPTX_SAVE_FILES:
                                                processor.save_extraction(extraction_result, format="json")
                                                print(f"      [OK] PPTX saved to file: {item_name}")
                                            
                                            # ADD TO VECTORSTORE - Use extracted content
                                            file_content = extraction_result.get("combined_content", "")
                                            
                                            # Create metadata for vectorstore
                                            folder_path_str = " > ".join(folder_path).lower() if folder_path else ""
                                            is_certificate = (
                                                ('certificate' in folder_path_str or 'cert' in folder_path_str) and
                                                '2025' in folder_path_str
                                            )
                                            
                                            is_downloadable = False
                                            if is_certificate:
                                                is_downloadable = True
                                            else:
                                                for downloadable_path in self.downloadable_folders:
                                                    if downloadable_path in folder_path_str:
                                                        is_downloadable = True
                                                        break
                                            
                                            # Build tag
                                            current_folder_path = folder_path + [item_name] if folder_path else [item_name]
                                            sanitized_path = [f.replace('/', '-').replace('\\', '-').strip() for f in current_folder_path if f.strip()]
                                            tag = "/".join(["sharepoint"] + sanitized_path)
                                            
                                            metadata = {
                                                "source_type": "sharepoint",
                                                "source": "cloudfuze_doc360",
                                                "file_name": item_name,
                                                "file_url": web_url,
                                                "folder_path": " > ".join(folder_path) if folder_path else "Documents",
                                                "folder_tags": tag,
                                                "tag": tag,
                                                "page_url": web_url,
                                                "content_type": "pptx_slide",
                                                "is_certificate": is_certificate,
                                                "is_downloadable": is_downloadable,
                                                "total_slides": extraction_result.get("total_slides", 0),
                                                "depth": depth
                                            }
                                            
                                            if is_downloadable:
                                                metadata["download_url"] = web_url
                                            
                                            # Create document with extracted PPTX content
                                            doc = Document(
                                                page_content=file_content[:15000],  # Limit content size
                                                metadata=metadata
                                            )
                                            all_documents.append(doc)
                                            print(f"      [OK] Added PPTX to vectorstore: {item_name}")
                                            continue  # Skip normal processing
                                        else:
                                            print(f"      [WARNING] PPTX extraction failed for {item_name}")
                            except Exception as e:
                                print(f"      [WARNING] PPTX extraction error for {item_name}: {e}")
                                import traceback
                                traceback.print_exc()
                        
                        # If PPTX pipeline is disabled, fall through to normal processing (will skip with "Skipping binary file")
                    
                    # Download file content (for non-PPTX files, or if PPTX pipeline is disabled)
                    file_content = self.download_file_content(item_id_current, item_name)
                    
                    # If we couldn't download text content, create a document with enriched metadata context
                    if not file_content or len(file_content.strip()) < 50:
                        # Enrich with folder context, file name parts, and path information for better searchability
                        folder_context = " > ".join(folder_path) if folder_path else "Documents"
                        file_name_parts = item_name.rsplit('.', 1)[0].replace('_', ' ').replace('-', ' ')
                        file_content = f"""
File Name: {item_name}
Location: {folder_context}
Folder Path: {folder_context}

This document is located in the SharePoint folder: {folder_context}
File type: {item_name.rsplit('.', 1)[-1] if '.' in item_name else 'unknown'}
File name keywords: {file_name_parts}

Note: Full text content could not be extracted from this file, but it is available in the SharePoint location specified above.
"""
                    
                    # Check if it's a certificate (folder path contains "certificate"/"cert" and "2025")
                    folder_path_str = " > ".join(folder_path).lower() if folder_path else ""
                    is_certificate = (
                        ('certificate' in folder_path_str or 'cert' in folder_path_str) and
                        '2025' in folder_path_str
                    )
                    
                    # Check if file is in a downloadable folder (policy documents, etc.)
                    is_downloadable = False
                    if is_certificate:
                        # Certificates are always downloadable
                        is_downloadable = True
                    else:
                        # Check if file is in any downloadable folder path
                        for downloadable_path in self.downloadable_folders:
                            if downloadable_path in folder_path_str:
                                is_downloadable = True
                                break
                    
                    # Note: Videos are now skipped entirely (see filtering above)
                    # Keeping this logic commented out for future use
                    is_video = False
                    video_type = None
                    # file_ext = item_name.rsplit('.', 1)[-1].lower() if '.' in item_name else ''
                    # if file_ext in ['mp4', 'avi', 'mov', 'wmv', 'mkv']:
                    #     if 'video' in folder_path_str and 'demo' in folder_path_str:
                    #         is_video = True
                    #         video_type = "demo_video"
                    #     elif 'video' in folder_path_str:
                    #         is_video = True
                    #         video_type = "video"
                    
                    # Detect Excel files for proper metadata tagging
                    is_excel = file_ext in ['xls', 'xlsx']
                    
                    # Create metadata
                    metadata = {
                        "source_type": "sharepoint",
                        "source": "cloudfuze_doc360",
                        "file_name": item_name,
                        "file_url": web_url,
                        "folder_path": " > ".join(folder_path) if folder_path else "Documents",
                        "folder_tags": tag,
                        "tag": tag,
                        "page_url": web_url,
                        "content_type": "excel_data" if is_excel else ("sharepoint_video" if is_video else "sharepoint_file"),  # Mark Excel files
                        "is_certificate": is_certificate,
                        "depth": depth
                    }
                    
                    # Add Excel-specific metadata
                    if is_excel:
                        metadata["file_format"] = file_ext
                        metadata["excel_tag"] = "excel"  # Additional tag for better retrieval
                    
                    # Add download URL for certificates and downloadable files (policy documents, etc.)
                    if is_certificate or is_downloadable:
                        metadata["download_url"] = web_url
                        metadata["is_downloadable"] = True
                    else:
                        metadata["is_downloadable"] = False
                    
                    # Add video URL for videos
                    if is_video:
                        metadata["video_url"] = web_url
                        metadata["video_type"] = video_type
                        metadata["video_name"] = item_name.rsplit('.', 1)[0]
                    
                    doc = Document(
                        page_content=file_content[:15000],
                        metadata=metadata
                    )
                    all_documents.append(doc)
                    print(f"   [OK] Extracted file: {item_name}")
                    
                elif 'folder' in item:
                    # Check if this folder should be excluded
                    next_folder_path = folder_path + [item_name] if folder_path else [item_name]
                    next_folder_path_str = " > ".join(next_folder_path)
                    next_folder_path_lower = next_folder_path_str.lower()
                    
                    folder_excluded = False
                    for excluded_path in self.excluded_folders:
                        excluded_lower = excluded_path.lower()
                        if excluded_lower in next_folder_path_lower:
                            folder_excluded = True
                            print(f"   [SKIP] Skipping excluded folder: {next_folder_path_str} (matched: {excluded_path})")
                            break
                    
                    if not folder_excluded:
                        # It's a folder - recurse
                        print(f"   [*] Found folder: {item_name}")
                        sub_docs = self.extract_from_folder(item_id_current, next_folder_path, visited_ids, depth + 1)
                        all_documents.extend(sub_docs)
            
            return all_documents
            
        except Exception as e:
            print(f"   [ERROR] Error extracting from folder {folder_name}: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def extract_all(self) -> List[Document]:
        """Extract all files and folders from SharePoint Documents library."""
        print("=" * 60)
        print("SHAREPOINT GRAPH API CONTENT EXTRACTION")
        print("=" * 60)
        
        # Get site and drive IDs
        site_id = self.get_site_id()
        if not site_id:
            print("[ERROR] Could not get site ID")
            return []
        
        drive_id = self.get_drive_id()
        if not drive_id:
            print("[ERROR] Could not get drive ID")
            return []
        
        print("[OK] Connected to SharePoint via Graph API")
        
        # Extract recursively from root
        all_documents = self.extract_from_folder()
        
        print(f"\n[OK] Extraction complete!")
        print(f"   Documents extracted: {len(all_documents)}")
        
        return all_documents


def extract_sharepoint_via_graph() -> List[Document]:
    """Main function for Graph API extraction."""
    extractor = SharePointGraphExtractor()
    return extractor.extract_all()

if __name__ == "__main__":
    docs = extract_sharepoint_via_graph()
    print(f"\n📄 Total documents: {len(docs)}")
    
    for doc in docs[:5]:
        print(f"\n   - {doc.metadata.get('file_name')}: {len(doc.page_content)} chars")

