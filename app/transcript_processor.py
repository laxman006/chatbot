# -*- coding: utf-8 -*-
"""
Transcript Processor for SharePoint Transcripts

Extracts transcript Word documents from SharePoint, processes them into
both raw conversation format and Q/A pairs, and creates LangChain Documents
for the knowledge base.
"""

import os
import re
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from urllib.parse import urlparse
from langchain_core.documents import Document
import requests
import tempfile
import tiktoken

from app.sharepoint_auth import sharepoint_auth
from app.sharepoint_graph_extractor import SharePointGraphExtractor
from app.doc_processor import extract_text_from_docx
from app.transcript_normalizer import TranscriptNormalizer
from app.transcript_artifact_extractor import TranscriptArtifactExtractor
from config import (
    SHAREPOINT_TRANSCRIPTS_SITE_URL,
    SHAREPOINT_TRANSCRIPTS_FOLDER_PATH,
    ENABLE_TRANSCRIPT_NORMALIZATION,
    ENABLE_ARTIFACT_EXTRACTION,
    TRANSCRIPT_KB_TIER
)

# Token counting for transcript chunking
TRANSCRIPT_TARGET_TOKENS = 250  # Target: 180-300 tokens, ideal: 250
TRANSCRIPT_MAX_TOKENS = 350
TRANSCRIPT_MIN_TOKENS = 180

# Initialize tokenizer for transcript chunking
_transcript_tokenizer = None

def get_transcript_tokenizer():
    """Lazy initialization of tokenizer."""
    global _transcript_tokenizer
    if _transcript_tokenizer is None:
        _transcript_tokenizer = tiktoken.get_encoding("cl100k_base")
    return _transcript_tokenizer

def count_tokens(text: str) -> int:
    """Count tokens in text using tiktoken."""
    if not text:
        return 0
    tokenizer = get_transcript_tokenizer()
    return len(tokenizer.encode(text))


def group_artifacts_for_chunking(
    artifacts: Dict[str, List[Dict[str, Any]]],
    metadata: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Group related artifacts together to create 180-300 token chunks.
    
    Groups artifacts by type and topic, combining them until reaching target token size.
    This ensures 2-5 chunks per transcript instead of 1 chunk per artifact.
    
    Args:
        artifacts: Dictionary with 'qa_pairs', 'objections', 'features', 'decision_drivers'
        metadata: Base metadata for building retrieval text
    
    Returns:
        List of grouped artifact dictionaries, each ready to become a document
    """
    grouped_docs = []
    
    # Map artifact keys to build_retrieval_text types
    type_mapping = {
        'qa_pairs': 'Q&A',
        'objections': 'Objection',
        'features': 'Feature',
        'decision_drivers': 'Decision Driver'
    }
    
    # Process each artifact type
    for artifact_key, artifact_list in artifacts.items():
        if not artifact_list:
            continue
        
        artifact_type = type_mapping.get(artifact_key, artifact_key)
        
        # Group artifacts by topic (for Q&A) or by similarity
        current_group = []
        current_tokens = 0
        
        for artifact in artifact_list:
            # Build retrieval text for this artifact
            retrieval_text = build_retrieval_text(artifact_type, artifact, metadata)
            if not retrieval_text:
                continue
            
            artifact_tokens = count_tokens(retrieval_text)
            
            # If adding this artifact would exceed max, finalize current group
            if current_group and (current_tokens + artifact_tokens) > TRANSCRIPT_MAX_TOKENS:
                # Finalize current group if it meets minimum
                if current_tokens >= TRANSCRIPT_MIN_TOKENS:
                    combined_text = "\n\n".join([build_retrieval_text(artifact_type, a, metadata) for a in current_group])
                    grouped_docs.append({
                        "artifact_type": artifact_type,
                        "artifact_key": artifact_key,
                        "artifacts": current_group.copy(),
                        "combined_text": combined_text
                    })
                # Start new group
                current_group = [artifact]
                current_tokens = artifact_tokens
            else:
                # Add to current group
                current_group.append(artifact)
                current_tokens += artifact_tokens
                
                # If we've reached target size, finalize group
                if current_tokens >= TRANSCRIPT_TARGET_TOKENS:
                    combined_text = "\n\n".join([build_retrieval_text(artifact_type, a, metadata) for a in current_group])
                    grouped_docs.append({
                        "artifact_type": artifact_type,
                        "artifact_key": artifact_key,
                        "artifacts": current_group.copy(),
                        "combined_text": combined_text
                    })
                    current_group = []
                    current_tokens = 0
        
        # Finalize remaining artifacts in group
        if current_group:
            # If group is too small, try to merge with previous group of same type
            if current_tokens < TRANSCRIPT_MIN_TOKENS and grouped_docs:
                last_group = grouped_docs[-1]
                if last_group["artifact_type"] == artifact_type:
                    # Merge with previous group if total doesn't exceed max
                    merged_text = last_group["combined_text"] + "\n\n" + "\n\n".join([build_retrieval_text(artifact_type, a, metadata) for a in current_group])
                    merged_tokens = count_tokens(merged_text)
                    if merged_tokens <= TRANSCRIPT_MAX_TOKENS:
                        last_group["artifacts"].extend(current_group)
                        last_group["combined_text"] = merged_text
                        continue
            
            # Create group even if small (better than losing content)
            combined_text = "\n\n".join([build_retrieval_text(artifact_type, a, metadata) for a in current_group])
            grouped_docs.append({
                "artifact_type": artifact_type,
                "artifact_key": artifact_key,
                "artifacts": current_group.copy(),
                "combined_text": combined_text
            })
    
    return grouped_docs


def build_retrieval_text(artifact_type: str, artifact_data: Dict[str, Any], metadata: Dict[str, Any]) -> str:
    """
    Convert transcript artifacts to natural language retrieval text.
    
    This is the CRITICAL layer that makes transcripts searchable.
    Converts structured JSON artifacts → natural language explanations.
    
    Args:
        artifact_type: "Q&A", "Feature", "Objection", "Decision Driver"
        artifact_data: The artifact content (dict with question/answer, feature details, etc.)
        metadata: Transcript metadata (customer, product, etc.)
    
    Returns:
        Natural language text optimized for semantic search
    """
    customer = metadata.get("customer", "a customer")
    product = "CloudFuze Manage"
    meeting_title = metadata.get("meeting_title", "demo")
    industry = metadata.get("industry", "")
    
    # Build customer prefix with industry if available
    if customer and customer != "a customer" and customer.lower() != "none":
        customer_prefix = f"During a {product} demo with {customer}"
        if industry:
            customer_prefix += f" from the {industry} sector"
    else:
        customer_prefix = f"During a {product} demo"
    
    if artifact_type == "Q&A":
        question = artifact_data.get('question', '').strip()
        answer = artifact_data.get('answer', '').strip()
        topic = artifact_data.get('topic', '')
        
        if not question or not answer:
            return ""
        
        # Clean answer - remove conversational phrases
        answer_clean = answer
        # Remove phrases like "That's where we come to the picture"
        conversational_phrases = [
            "that's where we come to the picture",
            "so we'll show you that",
            "let me show you",
            "i'll show you",
            "right, so",
            "ok, so",
            "yeah, so"
        ]
        for phrase in conversational_phrases:
            answer_clean = re.sub(rf'\b{re.escape(phrase)}\b[^.]*\.', '', answer_clean, flags=re.IGNORECASE)
        answer_clean = answer_clean.strip()
        
        retrieval_text = f"""{customer_prefix}, a question was asked: {question}

The CloudFuze team explained: {answer_clean}"""
        
        if topic:
            retrieval_text += f"\n\nThis discussion was about {topic}."
        
        retrieval_text += "\n\nThis information was shared in a customer discussion context and reflects how the product works based on the demo conversation."
        
        return retrieval_text.strip()
    
    elif artifact_type == "Feature":
        feature_name = artifact_data.get('feature', '').strip()
        capability = artifact_data.get('capability', '').strip()
        value = artifact_data.get('value', '')
        limitations = artifact_data.get('limitations', '')
        status = artifact_data.get('roadmap_status', '')
        
        if not feature_name or not capability:
            return ""
        
        retrieval_text = f"""{product} provides the following capability discussed during a customer demo:

{feature_name}: {capability}"""
        
        if value:
            retrieval_text += f"\n\nThe value and benefits: {value}"
        
        if limitations:
            retrieval_text += f"\n\nLimitations and considerations: {limitations}"
        
        if status:
            retrieval_text += f"\n\nStatus: {status}"
        
        retrieval_text += "\n\nThis feature explanation is based on a live demo conversation and represents current observed behavior."
        
        return retrieval_text.strip()
    
    elif artifact_type == "Objection":
        objection = artifact_data.get('objection', '').strip()
        response = artifact_data.get('response', '').strip()
        stage = artifact_data.get('stage', '')
        status = artifact_data.get('resolution_status', '')
        
        if not objection:
            return ""
        
        retrieval_text = f"""{customer_prefix}, the following concern was raised: {objection}"""
        
        if response:
            # Clean response
            response_clean = response
            for phrase in ["that's where we come to the picture", "so we'll show you that"]:
                response_clean = re.sub(rf'\b{re.escape(phrase)}\b[^.]*\.', '', response_clean, flags=re.IGNORECASE)
            response_clean = response_clean.strip()
            
            retrieval_text += f"\n\nThe CloudFuze team addressed this concern: {response_clean}"
        
        if stage:
            retrieval_text += f"\n\nThis occurred during the {stage} stage of the evaluation."
        
        if status:
            retrieval_text += f"\n\nResolution status: {status}"
        
        retrieval_text += "\n\nThis objection and response were part of a customer demo conversation."
        
        return retrieval_text.strip()
    
    elif artifact_type == "Decision Driver":
        priority = artifact_data.get('customer_priority', '').strip()
        blocking_factors = artifact_data.get('blocking_factors', [])
        timeline = artifact_data.get('timeline', '')
        
        if not priority:
            return ""
        
        retrieval_text = f"""In a customer evaluation discussion for {product}{f' with {customer}' if customer and customer != 'a customer' and customer.lower() != 'none' else ''}, the following priority was identified: {priority}"""
        
        if blocking_factors:
            factors_str = ", ".join(blocking_factors) if isinstance(blocking_factors, list) else str(blocking_factors)
            retrieval_text += f"\n\nBlocking factors or constraints: {factors_str}"
        
        if timeline:
            retrieval_text += f"\n\nTimeline considerations: {timeline}"
        
        retrieval_text += "\n\nThese factors influenced the customer's decision-making during the demo."
        
        return retrieval_text.strip()
    
    else:
        return ""


class TranscriptProcessor(SharePointGraphExtractor):
    """Process transcripts from SharePoint folder."""
    
    def __init__(self, site_url: str = None, folder_path: str = None):
        """
        Initialize transcript processor.
        
        Args:
            site_url: SharePoint site URL (defaults to config)
            folder_path: Transcript folder path (defaults to config)
        """
        # Initialize parent class first (it sets default site_url from env)
        super().__init__()
        
        # Override site_url for transcripts after parent init
        self.site_url = site_url or SHAREPOINT_TRANSCRIPTS_SITE_URL
        self.transcript_folder_path = folder_path or SHAREPOINT_TRANSCRIPTS_FOLDER_PATH
        
        # Reset site_id and drive_id since we're using a different site
        self.site_id = None
        self.drive_id = None
        
        # Initialize normalizer and artifact extractor
        self.normalizer = TranscriptNormalizer(preserve_timestamps=False)
        self.artifact_extractor = TranscriptArtifactExtractor() if ENABLE_ARTIFACT_EXTRACTION else None
        
        print(f"[*] Transcript Processor initialized")
        print(f"   Site URL: {self.site_url}")
        print(f"   Folder Path: {self.transcript_folder_path}")
        print(f"   Normalization: {'Enabled' if ENABLE_TRANSCRIPT_NORMALIZATION else 'Disabled'}")
        print(f"   Artifact Extraction: {'Enabled' if ENABLE_ARTIFACT_EXTRACTION else 'Disabled'}")
    
    def find_folder_by_path(self, folder_path: str) -> Optional[str]:
        """
        Find folder ID by path in SharePoint.
        
        Args:
            folder_path: Folder path like "Neutara Labs/Transcripts"
        
        Returns:
            Folder item ID or None
        """
        drive_id = self.get_drive_id()
        if not drive_id:
            return None
        
        try:
            # Split path into components
            path_parts = [p.strip() for p in folder_path.split('/') if p.strip()]
            
            # Start from root
            current_item_id = None
            
            for folder_name in path_parts:
                # List items in current folder
                if current_item_id:
                    graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{current_item_id}/children"
                else:
                    graph_url = f"{self.graph_base_url}/drives/{drive_id}/root/children"
                
                headers = sharepoint_auth.get_headers()
                response = requests.get(graph_url, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    print(f"[ERROR] Failed to list items: {response.status_code}")
                    return None
                
                data = response.json()
                items = data.get('value', [])
                
                # Find folder with matching name
                found = False
                for item in items:
                    if 'folder' in item and item.get('name', '').strip() == folder_name:
                        current_item_id = item.get('id')
                        found = True
                        break
                
                if not found:
                    print(f"[ERROR] Folder not found: {folder_name} in path {folder_path}")
                    return None
            
            return current_item_id
            
        except Exception as e:
            print(f"[ERROR] Error finding folder: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def extract_metadata_from_filename(self, filename: str) -> Dict[str, Any]:
        """
        Extract metadata from transcript filename.
        
        Example: "CloudFuze Manage Demo - Phillips Exeter Academy-20251202_110233-Meeting Recording.docx"
        
        Returns:
            Dictionary with extracted metadata
        """
        metadata = {
            "meeting_title": None,
            "meeting_date": None,
            "meeting_time": None,
            "content_type": "meeting_transcript"
        }
        
        try:
            # Remove extension
            name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename
            
            # Try to extract date pattern: YYYYMMDD (may have underscore or dash before time)
            # Pattern: YYYYMMDD or YYYYMMDD_HHMMSS or YYYYMMDD-HHMMSS
            date_pattern = r'(\d{8})[_-]?(\d{6})?'
            date_match = re.search(date_pattern, name_without_ext)
            if date_match:
                date_str = date_match.group(1)
                time_str = date_match.group(2) if date_match.lastindex >= 2 else None
                
                try:
                    # Parse date: YYYYMMDD
                    date_obj = datetime.strptime(date_str, '%Y%m%d')
                    metadata["meeting_date"] = date_obj.strftime('%Y-%m-%d')
                except:
                    pass
                
                # Parse time if available: HHMMSS
                if time_str:
                    try:
                        time_obj = datetime.strptime(time_str, '%H%M%S')
                        metadata["meeting_time"] = time_obj.strftime('%H:%M:%S')
                    except:
                        pass
            
            # Extract title (everything before the date)
            if date_match:
                title = name_without_ext[:date_match.start()].strip()
                # Clean up title (remove trailing dashes, spaces)
                title = re.sub(r'[-_\s]+$', '', title)
                metadata["meeting_title"] = title if title else None
            
            # Determine content type
            name_lower = filename.lower()
            if 'call' in name_lower or 'recording' in name_lower:
                metadata["content_type"] = "call_transcript"
            elif 'meeting' in name_lower:
                metadata["content_type"] = "meeting_transcript"
            
        except Exception as e:
            print(f"[WARNING] Error extracting metadata from filename {filename}: {e}")
        
        return metadata
    
    def extract_participants_from_text(self, text: str) -> List[str]:
        """
        Extract participant names from transcript text.
        
        Looks for patterns like:
        - "Lawrence Lewis   0:04"
        - "Heffner, Scott   0:27"
        
        Returns:
            List of unique participant names
        """
        participants = set()
        
        try:
            # Pattern: Name followed by whitespace and timestamp
            # Matches: "Name   0:04" or "Name, Last   0:27"
            pattern = r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?)\s+\d+:\d+'
            
            for line in text.split('\n'):
                match = re.match(pattern, line.strip())
                if match:
                    name = match.group(1).strip()
                    # Clean up name (remove extra spaces, normalize)
                    name = re.sub(r'\s+', ' ', name)
                    participants.add(name)
        
        except Exception as e:
            print(f"[WARNING] Error extracting participants: {e}")
        
        return sorted(list(participants))
    
    def extract_qa_pairs(self, text: str) -> List[Dict[str, str]]:
        """
        Extract Q/A pairs from transcript text.
        
        Looks for question patterns and extracts the following answer.
        
        Returns:
            List of dictionaries with 'question' and 'answer' keys
        """
        qa_pairs = []
        
        try:
            lines = text.split('\n')
            current_question = None
            current_answer = []
            current_speaker = None
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line:
                    continue
                
                # Check if line is a speaker with timestamp
                speaker_match = re.match(r'^([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*(?:,\s*[A-Z][a-zA-Z]+)?)\s+\d+:\d+', line)
                if speaker_match:
                    current_speaker = speaker_match.group(1).strip()
                    # Extract text after timestamp
                    text_part = line[len(speaker_match.group(0)):].strip()
                    if text_part:
                        line = text_part
                    else:
                        continue
                
                # Check if line contains a question
                question_indicators = ['?', 'how', 'what', 'why', 'when', 'where', 'who', 'which', 'can you', 'could you', 'would you']
                is_question = '?' in line or any(indicator in line.lower() for indicator in question_indicators)
                
                if is_question and len(line) > 10:  # Minimum question length
                    # Save previous Q/A pair if exists
                    if current_question and current_answer:
                        qa_pairs.append({
                            "question": current_question,
                            "answer": " ".join(current_answer).strip()
                        })
                    
                    # Start new question
                    current_question = line
                    current_answer = []
                
                elif current_question:
                    # This is part of the answer
                    if line and not re.match(r'^\d+:\d+', line):  # Skip timestamp-only lines
                        current_answer.append(line)
                
                # If we have a long answer, save it and reset
                if current_answer and len(current_answer) > 10:
                    if current_question:
                        qa_pairs.append({
                            "question": current_question,
                            "answer": " ".join(current_answer).strip()
                        })
                    current_question = None
                    current_answer = []
            
            # Save last Q/A pair
            if current_question and current_answer:
                qa_pairs.append({
                    "question": current_question,
                    "answer": " ".join(current_answer).strip()
                })
        
        except Exception as e:
            print(f"[WARNING] Error extracting Q/A pairs: {e}")
            import traceback
            traceback.print_exc()
        
        return qa_pairs
    
    def process_transcript_file(self, item_id: str, file_name: str, web_url: str) -> List[Document]:
        """
        Process a single transcript file into Documents.
        
        Creates both raw conversation and Q/A pair documents.
        
        Args:
            item_id: SharePoint item ID
            file_name: File name
            web_url: SharePoint web URL
        
        Returns:
            List of Document objects
        """
        documents = []
        
        try:
            print(f"   [*] Processing transcript: {file_name}")
            
            # Download file content
            drive_id = self.get_drive_id()
            if not drive_id:
                return []
            
            graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{item_id}/content"
            headers = sharepoint_auth.get_headers()
            response = requests.get(graph_url, headers=headers, timeout=60, stream=True)
            
            if response.status_code != 200:
                print(f"      [WARNING] Failed to download {file_name}: {response.status_code}")
                return []
            
            # Save to temp file and extract text
            tmp_path = None
            try:
                tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.docx')
                tmp_path = tmp_file.name
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_file.close()
                
                # Extract text
                text_content = extract_text_from_docx(tmp_path)
                
                if not text_content or len(text_content.strip()) < 100:
                    print(f"      [WARNING] No substantial content extracted from {file_name}")
                    return []
                
            except Exception as e:
                print(f"      [WARNING] Error processing {file_name}: {e}")
                return []
            finally:
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        import time
                        time.sleep(0.1)
                        os.unlink(tmp_path)
                    except:
                        pass
            
            # Extract metadata from filename
            filename_metadata = self.extract_metadata_from_filename(file_name)
            
            # Extract participants
            participants = self.extract_participants_from_text(text_content)
            
            # Extract speaker roles
            speaker_roles_dict = self.normalizer.extract_speaker_roles(text_content)
            speaker_roles_str = " | ".join([f"{name} ({role})" for name, role in speaker_roles_dict.items()]) if speaker_roles_dict else None
            
            # Normalize transcript text
            normalized_text = text_content
            if ENABLE_TRANSCRIPT_NORMALIZATION:
                normalized_text = self.normalizer.normalize_transcript_text(text_content)
                print(f"      [OK] Normalized transcript ({len(text_content)} -> {len(normalized_text)} chars)")
            
            # Extract customer name from meeting title or filename
            customer_name = self._extract_customer_name(filename_metadata.get("meeting_title", file_name))
            
            # Extract industry (can be enhanced with LLM or manual mapping)
            industry = self._infer_industry(customer_name, filename_metadata.get("meeting_title", ""))
            
            # Extract topics from content (can be enhanced)
            topics = self._extract_topics(normalized_text)
            
            # Check for pricing content
            contains_pricing = self._contains_pricing(normalized_text)
            
            # Base metadata with Secondary KB fields
            participants_str = ", ".join(participants) if participants else None
            file_ext = file_name.rsplit('.', 1)[-1].lower() if '.' in file_name else 'docx'
            
            base_metadata = {
                "source_type": "transcript",
                "source": "sharepoint_transcripts",
                "file_name": file_name,
                "file_url": web_url,
                "folder_path": self.transcript_folder_path,
                "tag": "sharepoint/transcripts",
                "filetype": file_ext,
                "content_type": filename_metadata.get("content_type", "meeting_transcript"),
                "meeting_date": filename_metadata.get("meeting_date"),
                "meeting_title": filename_metadata.get("meeting_title"),
                "participants": participants_str,
                # Secondary KB metadata
                "kb_tier": TRANSCRIPT_KB_TIER,
                "customer": customer_name,
                "industry": industry,
                "speaker_roles": speaker_roles_str,
                "topic": topics,
                "reliability": "contextual",
                "not_contractual": True,
                "internal_use_only": True,
                "contains_pricing": contains_pricing,
                "customer_identifiable": True
            }
            
            # Extract artifacts if enabled
            artifacts = {}
            if ENABLE_ARTIFACT_EXTRACTION and self.artifact_extractor:
                print(f"      [*] Extracting knowledge artifacts...")
                artifacts = self.artifact_extractor.extract_artifacts(normalized_text, base_metadata)
                print(f"      [OK] Extracted artifacts: {len(artifacts.get('qa_pairs', []))} Q&A, "
                      f"{len(artifacts.get('objections', []))} objections, "
                      f"{len(artifacts.get('features', []))} features, "
                      f"{len(artifacts.get('decision_drivers', []))} decision drivers")
            
            # Document 1: Q&A pairs (highest priority) - ONE DOCUMENT PER Q&A PAIR
            # Use artifact-extracted Q&A if available, otherwise fallback to pattern-based
            qa_pairs_to_use = artifacts.get('qa_pairs', [])
            if not qa_pairs_to_use:
                # Fallback to pattern-based extraction
                qa_pairs_to_use = self.extract_qa_pairs(normalized_text)
                if qa_pairs_to_use:
                    # Convert to artifact format
                    qa_pairs_to_use = [
                        {
                            "question": qa.get('question', ''),
                            "answer": qa.get('answer', ''),
                            "speaker": "Unknown",
                            "topic": "General",
                            "confidence": "medium"
                        }
                        for qa in qa_pairs_to_use
                    ]
            
            # Group artifacts for optimal chunking (180-300 tokens per chunk)
            artifacts_dict = {
                'qa_pairs': qa_pairs_to_use,
                'objections': artifacts.get('objections', []),
                'features': artifacts.get('features', []),
                'decision_drivers': artifacts.get('decision_drivers', [])
            }
            
            # Group artifacts into optimal chunks
            grouped_artifacts = group_artifacts_for_chunking(artifacts_dict, base_metadata)
            
            # Create documents from grouped artifacts
            for group_idx, group in enumerate(grouped_artifacts, 1):
                artifact_type = group["artifact_type"]
                combined_text = group["combined_text"]
                group_artifacts = group["artifacts"]
                
                # Build original content for metadata
                original_contents = []
                for artifact in group_artifacts:
                    if artifact_type == "Q&A":
                        original_contents.append(f"Q: {artifact.get('question', '')}\nA: {artifact.get('answer', '')}")
                    elif artifact_type == "Objection":
                        original_contents.append(f"Objection: {artifact.get('objection', '')}\nResponse: {artifact.get('response', '')}")
                    elif artifact_type == "Feature":
                        original_contents.append(f"Feature: {artifact.get('feature', '')}\nCapability: {artifact.get('capability', '')}")
                    elif artifact_type == "Decision Driver":
                        original_contents.append(f"Priority: {artifact.get('customer_priority', '')}")
                
                original_content = "\n\n---\n\n".join(original_contents)
                
                # Determine document type and priority
                doc_type_map = {
                    "Q&A": ("qa_pairs", "High"),
                    "Objection": ("objection_response", "High"),
                    "Feature": ("feature_capability", "Medium"),
                    "Decision Driver": ("decision_driver", "Medium")
                }
                doc_type, priority = doc_type_map.get(artifact_type, ("transcript_artifact", "Medium"))
                
                # Create document from grouped artifacts
                grouped_doc = Document(
                    page_content=combined_text,  # 👈 Combined retrieval text (180-300 tokens)
                    metadata={
                        **base_metadata,
                        "document_type": doc_type,
                        "artifact_type": artifact_type,
                        "priority": priority,
                        "raw_content": original_content,
                        "group_index": group_idx,
                        "group_total": len(grouped_artifacts),
                        "artifacts_in_group": len(group_artifacts),
                        "estimated_tokens": count_tokens(combined_text)
                    }
                )
                documents.append(grouped_doc)
            
            if grouped_artifacts:
                total_artifacts = sum(len(group["artifacts"]) for group in grouped_artifacts)
                avg_tokens = sum(count_tokens(g['combined_text']) for g in grouped_artifacts) // len(grouped_artifacts) if grouped_artifacts else 0
                print(f"      [OK] Created {len(grouped_artifacts)} grouped documents (from {total_artifacts} artifacts, ~{avg_tokens} tokens avg)")
            
            # All artifacts are now grouped and created above - no need for separate loops
            
            # Document 5: Raw normalized transcript (FALLBACK ONLY - NOT EMBEDDED BY DEFAULT)
            # Only create if no artifacts were extracted (last resort)
            if not documents or len(documents) == 0:
                # No artifacts extracted - create raw transcript as fallback
                raw_doc = Document(
                    page_content=normalized_text[:50000],
                    metadata={
                        **base_metadata,
                        "document_type": "raw_transcript",
                        "artifact_type": "Raw Transcript",
                        "content_length": len(normalized_text),
                        "priority": "Low",
                        "is_fallback": True
                    }
                )
                documents.append(raw_doc)
                print(f"      [OK] Created raw transcript fallback document ({len(normalized_text)} chars)")
            else:
                print(f"      [INFO] Skipped raw transcript (using {len(documents)} artifact documents instead)")
            
        except Exception as e:
            print(f"      [ERROR] Error processing transcript {file_name}: {e}")
            import traceback
            traceback.print_exc()
        
        return documents
    
    def extract_transcripts_from_sharepoint(self) -> List[Document]:
        """
        Extract all transcripts from SharePoint folder.
        
        Returns:
            List of Document objects (both raw and Q/A format)
        """
        print("=" * 60)
        print("SHAREPOINT TRANSCRIPT EXTRACTION")
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
        
        # Find transcript folder
        folder_id = self.find_folder_by_path(self.transcript_folder_path)
        if not folder_id:
            print(f"[ERROR] Could not find folder: {self.transcript_folder_path}")
            return []
        
        print(f"[OK] Found transcript folder: {self.transcript_folder_path}")
        
        # List all items in transcript folder
        graph_url = f"{self.graph_base_url}/drives/{drive_id}/items/{folder_id}/children"
        headers = sharepoint_auth.get_headers()
        response = requests.get(graph_url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"[ERROR] Failed to list transcript folder: {response.status_code}")
            return []
        
        data = response.json()
        items = data.get('value', [])
        
        # Filter for Word documents only
        word_docs = [
            item for item in items
            if 'file' in item and not 'folder' in item
            and item.get('name', '').lower().endswith(('.doc', '.docx'))
        ]
        
        print(f"[OK] Found {len(word_docs)} transcript Word documents")
        
        if not word_docs:
            return []
        
        # Process each transcript
        all_documents = []
        for i, item in enumerate(word_docs, 1):
            file_name = item.get('name', 'Unknown')
            item_id = item.get('id')
            web_url = item.get('webUrl', '')
            
            print(f"\n[{i}/{len(word_docs)}] Processing: {file_name}")
            
            docs = self.process_transcript_file(item_id, file_name, web_url)
            all_documents.extend(docs)
        
        print(f"\n[OK] Transcript extraction complete!")
        print(f"   Total documents created: {len(all_documents)}")
        print(f"   Transcripts processed: {len(word_docs)}")
        
        return all_documents
    
    def _extract_customer_name(self, meeting_title: str) -> Optional[str]:
        """
        Extract customer name from meeting title or filename.
        
        Examples:
        - "CloudFuze Manage Demo - Phillips Exeter Academy" -> "Phillips Exeter Academy"
        - "Demo - Acme Corp" -> "Acme Corp"
        - "CloudFuze _ CloudFuze Manage Demo - Phillips Exeter Academy" -> "Phillips Exeter Academy"
        """
        if not meeting_title:
            return None
        
        # Common patterns: "Demo - Customer Name" or "Customer Name - Demo"
        # Updated to handle "CloudFuze Manage Demo" format
        patterns = [
            r'(?:CloudFuze\s+Manage\s+)?Demo\s*[-–]\s*(.+?)(?:\s*[-–]|$)',  # Handles "Demo - Customer" or "CloudFuze Manage Demo - Customer"
            r'(.+?)\s*[-–]\s*(?:CloudFuze\s+Manage\s+)?Demo',                # Handles "Customer - Demo" or "Customer - CloudFuze Manage Demo"
            r'with\s+(.+?)(?:\s*[-–]|$)',                                    # Handles "with Customer"
            r'[-–]\s*([A-Z][A-Za-z\s]+?)(?:\s*[-–]|$)',                      # Extract after last dash (fallback for complex names)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, meeting_title, re.IGNORECASE)
            if match:
                customer = match.group(1).strip()
                # Remove common suffixes
                customer = re.sub(r'\s*[-–]\s*Meeting.*$', '', customer, flags=re.IGNORECASE)
                customer = re.sub(r'\s*[-–]\s*Recording.*$', '', customer, flags=re.IGNORECASE)
                # Remove "CloudFuze" if it got extracted
                customer = re.sub(r'^CloudFuze\s+Manage\s*', '', customer, flags=re.IGNORECASE)
                customer = re.sub(r'^CloudFuze\s*', '', customer, flags=re.IGNORECASE)
                # Remove leading/trailing underscores and spaces
                customer = customer.strip(' _')
                if customer and len(customer) > 3:
                    return customer
        
        return None
    
    def _infer_industry(self, customer_name: str, meeting_title: str) -> Optional[str]:
        """
        Infer industry from customer name or meeting context.
        
        Simple keyword-based inference (can be enhanced with LLM or manual mapping).
        """
        if not customer_name and not meeting_title:
            return None
        
        text = f"{customer_name} {meeting_title}".lower()
        
        # Industry keywords
        industry_keywords = {
            "Education": ["academy", "school", "university", "college", "education", "student", "faculty"],
            "Healthcare": ["hospital", "health", "medical", "clinic", "patient", "healthcare"],
            "Finance": ["bank", "financial", "finance", "investment", "trading"],
            "Technology": ["tech", "software", "it", "technology"],
            "Manufacturing": ["manufacturing", "factory", "production"],
            "Retail": ["retail", "store", "shop", "commerce"],
        }
        
        for industry, keywords in industry_keywords.items():
            if any(keyword in text for keyword in keywords):
                return industry
        
        return None
    
    def _extract_topics(self, text: str) -> Optional[str]:
        """
        Extract main topics discussed in transcript using LLM (with keyword fallback).
        
        Uses NLP to dynamically identify topics, falls back to keyword matching if LLM fails.
        """
        if not text:
            return None
        
        # Try LLM-based extraction first if artifact extraction is enabled
        if ENABLE_ARTIFACT_EXTRACTION and self.artifact_extractor:
            try:
                topics = self.artifact_extractor.extract_topics(text)
                if topics:
                    topics_str = " | ".join(topics)
                    print(f"      [OK] Extracted {len(topics)} topics using LLM: {topics_str}")
                    return topics_str
            except Exception as e:
                print(f"      [WARNING] LLM topic extraction failed: {e}, using keyword fallback")
        
        # Fallback: Keyword-based extraction
        text_lower = text.lower()
        topics = []
        
        # Topic keywords (fallback method)
        topic_keywords = {
            "Shadow IT": ["shadow it", "unauthorized", "unapproved", "third party"],
            "Pricing": ["price", "cost", "pricing", "budget", "dollar", "$", "subscription"],
            "Integrations": ["integration", "api", "connect", "integrate", "endpoint"],
            "Automation": ["automate", "workflow", "automation", "trigger"],
            "License Management": ["license", "licensing", "seats", "subscription"],
            "Security": ["security", "compliance", "audit", "secure"],
            "Features": ["feature", "capability", "function", "tool"],
        }
        
        for topic, keywords in topic_keywords.items():
            if any(keyword in text_lower for keyword in keywords):
                topics.append(topic)
        
        if topics:
            topics_str = " | ".join(topics)
            print(f"      [OK] Extracted {len(topics)} topics using keyword matching: {topics_str}")
            return topics_str
        
        return None
    
    def _contains_pricing(self, text: str) -> bool:
        """Check if transcript contains pricing discussions."""
        if not text:
            return False
        
        text_lower = text.lower()
        pricing_keywords = [
            "price", "pricing", "cost", "dollar", "$", "subscription",
            "per user", "per month", "annual", "renewal", "contract"
        ]
        
        return any(keyword in text_lower for keyword in pricing_keywords)


def extract_transcripts_from_sharepoint() -> List[Document]:
    """Main function for transcript extraction."""
    processor = TranscriptProcessor()
    return processor.extract_transcripts_from_sharepoint()


if __name__ == "__main__":
    docs = extract_transcripts_from_sharepoint()
    print(f"\n📄 Total documents: {len(docs)}")
    
    for doc in docs[:5]:
        print(f"\n   - {doc.metadata.get('file_name')}: {doc.metadata.get('document_type')} ({len(doc.page_content)} chars)")

