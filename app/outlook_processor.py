# -*- coding: utf-8 -*-
"""
Outlook Email Thread Processor Module

Fetches email conversation threads from Outlook using Microsoft Graph API
and converts them into LangChain Documents for knowledge base integration.
"""

import os
import requests
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.sharepoint_auth import sharepoint_auth
from config import (
    OUTLOOK_FOLDER_NAME,
    OUTLOOK_MAX_EMAILS,
    OUTLOOK_DATE_FILTER,
    OUTLOOK_USER_EMAIL
)


class OutlookProcessor:
    """Processes Outlook emails and groups them into conversation threads."""
    
    def __init__(self):
        self.auth = sharepoint_auth
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.user_email = OUTLOOK_USER_EMAIL or self._get_authenticated_user_email()
    
    def _get_authenticated_user_email(self) -> str:
        """Get the email of the authenticated user (for application permissions, this needs to be specified)."""
        # With application permissions, we need to explicitly specify the user
        # This should be set in environment variables
        raise ValueError("OUTLOOK_USER_EMAIL must be set in environment variables when using application permissions")
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make authenticated request to Microsoft Graph API."""
        headers = self.auth.get_headers()
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Graph API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"[ERROR] Response: {e.response.text}")
            raise
    
    def get_folder_id(self, folder_name: str) -> Optional[str]:
        """Get folder ID by folder name."""
        print(f"[*] Looking for folder: {folder_name}")
        
        # Get all mail folders for the user
        url = f"{self.base_url}/users/{self.user_email}/mailFolders"
        
        try:
            data = self._make_request(url)
            folders = data.get("value", [])
            
            # Search for folder by display name (case-insensitive)
            folder_name_lower = folder_name.lower()
            for folder in folders:
                if folder.get("displayName", "").lower() == folder_name_lower:
                    folder_id = folder.get("id")
                    print(f"[OK] Found folder '{folder_name}' with ID: {folder_id}")
                    return folder_id
            
            # If not found in root, search in child folders
            for folder in folders:
                folder_id = self._search_child_folders(folder.get("id"), folder_name_lower)
                if folder_id:
                    return folder_id
            
            print(f"[WARNING] Folder '{folder_name}' not found")
            return None
            
        except Exception as e:
            print(f"[ERROR] Failed to get folder ID: {e}")
            return None
    
    def _search_child_folders(self, parent_folder_id: str, folder_name: str) -> Optional[str]:
        """Recursively search child folders."""
        url = f"{self.base_url}/users/{self.user_email}/mailFolders/{parent_folder_id}/childFolders"
        
        try:
            data = self._make_request(url)
            folders = data.get("value", [])
            
            for folder in folders:
                if folder.get("displayName", "").lower() == folder_name:
                    folder_id = folder.get("id")
                    print(f"[OK] Found folder in child folders with ID: {folder_id}")
                    return folder_id
                
                # Recursively search deeper
                child_folder_id = self._search_child_folders(folder.get("id"), folder_name)
                if child_folder_id:
                    return child_folder_id
            
            return None
        except Exception as e:
            print(f"[WARNING] Error searching child folders: {e}")
            return None
    
    def get_emails_from_folder(self, folder_name: str, max_emails: int = 500) -> List[Dict[str, Any]]:
        """Fetch emails from a specific folder."""
        print(f"[*] Fetching emails from folder: {folder_name}")
        
        # Get folder ID
        folder_id = self.get_folder_id(folder_name)
        if not folder_id:
            print(f"[ERROR] Cannot fetch emails - folder not found")
            return []
        
        # Build API URL
        url = f"{self.base_url}/users/{self.user_email}/mailFolders/{folder_id}/messages"
        
        # Build query parameters
        params = {
            "$top": min(max_emails, 999),  # Graph API max is 999 per request
            "$select": "subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview,body,conversationId,hasAttachments,importance",
            "$orderby": "receivedDateTime desc"
        }
        
        # Add date filter if specified
        if OUTLOOK_DATE_FILTER:
            filter_query = self._build_date_filter(OUTLOOK_DATE_FILTER)
            if filter_query:
                params["$filter"] = filter_query
        
        all_emails = []
        
        try:
            while url and len(all_emails) < max_emails:
                print(f"[*] Fetching batch (current total: {len(all_emails)})...")
                data = self._make_request(url, params if url == f"{self.base_url}/users/{self.user_email}/mailFolders/{folder_id}/messages" else None)
                
                emails = data.get("value", [])
                all_emails.extend(emails)
                
                # Check for next page
                url = data.get("@odata.nextLink")
                
                # Stop if we've reached max
                if len(all_emails) >= max_emails:
                    all_emails = all_emails[:max_emails]
                    break
            
            print(f"[OK] Fetched {len(all_emails)} emails from folder '{folder_name}'")
            return all_emails
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch emails: {e}")
            return []
    
    def _build_date_filter(self, date_filter: str) -> Optional[str]:
        """Build OData filter for date range."""
        now = datetime.now()
        
        if date_filter == "last_month":
            start_date = now - timedelta(days=30)
        elif date_filter == "last_3_months":
            start_date = now - timedelta(days=90)
        elif date_filter == "last_6_months":
            start_date = now - timedelta(days=180)
        elif date_filter == "last_year":
            start_date = now - timedelta(days=365)
        else:
            return None
        
        # Format: receivedDateTime ge 2024-01-01T00:00:00Z
        return f"receivedDateTime ge {start_date.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    
    def group_emails_by_conversation(self, emails: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group emails by conversation ID."""
        print(f"[*] Grouping {len(emails)} emails into conversation threads...")
        
        conversations = defaultdict(list)
        
        for email in emails:
            conversation_id = email.get("conversationId")
            if conversation_id:
                conversations[conversation_id].append(email)
        
        # Sort emails within each conversation by date
        for conv_id, conv_emails in conversations.items():
            conversations[conv_id] = sorted(
                conv_emails,
                key=lambda x: x.get("receivedDateTime", "")
            )
        
        print(f"[OK] Grouped into {len(conversations)} conversation threads")
        return dict(conversations)
    
    def format_thread_as_document(self, thread: List[Dict[str, Any]], folder_name: str) -> Document:
        """Convert an email thread into a single LangChain Document."""
        if not thread:
            return None
        
        # Get thread metadata
        first_email = thread[0]
        last_email = thread[-1]
        conversation_id = first_email.get("conversationId", "unknown")
        subject = first_email.get("subject", "No Subject")
        
        # Collect all participants
        participants = set()
        for email in thread:
            # From address
            from_addr = email.get("from", {}).get("emailAddress", {}).get("address")
            if from_addr:
                participants.add(from_addr)
            
            # To addresses
            for recipient in email.get("toRecipients", []):
                addr = recipient.get("emailAddress", {}).get("address")
                if addr:
                    participants.add(addr)
            
            # CC addresses
            for recipient in email.get("ccRecipients", []):
                addr = recipient.get("emailAddress", {}).get("address")
                if addr:
                    participants.add(addr)
        
        # Format date range
        first_date = first_email.get("receivedDateTime", "")
        last_date = last_email.get("receivedDateTime", "")
        
        # Build thread content - FOCUS ON EMAIL CONTENT ONLY
        # Subject at top for context
        content_parts = [
            f"Thread Subject: {subject}",
            "\n"
        ]
        
        # Add each email's content (minimal metadata)
        for idx, email in enumerate(thread, 1):
            date = email.get("receivedDateTime", "")
            
            # Get email body
            body = email.get("body", {}).get("content", "")
            
            # If body is empty, use bodyPreview
            if not body.strip():
                body = email.get("bodyPreview", "")
            
            # Clean HTML if present
            if email.get("body", {}).get("contentType") == "html":
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(body, "html.parser")
                body = soup.get_text(separator="\n", strip=True)
            
            # Only show date and content - keep it clean
            content_parts.append(
                f"\n[Email {idx} - {date[:10]}]\n"
                f"{body}\n"
            )
        
        # Combine content
        full_content = "\n".join(content_parts)
        
        # Create Document with metadata
        # Use primitive types (str, int, float, bool) for vectorstore compatibility
        # Convert list to comma-separated string
        doc = Document(
            page_content=full_content,
            metadata={
                "source_type": "outlook",
                "source": "outlook_email",
                "tag": f"email/{folder_name.lower().replace(' ', '_')}",
                "conversation_id": conversation_id,
                "conversation_topic": subject,
                "participants": ", ".join(sorted(participants)),  # Convert list to string
                "date_range": f"{first_date[:10]} to {last_date[:10]}",
                "email_count": len(thread),
                "folder_name": folder_name,
                "first_email_date": first_date,
                "last_email_date": last_date
            }
        )
        
        return doc
    
    def chunk_thread_documents(self, documents: List[Document]) -> List[Document]:
        """Chunk large thread documents for better retrieval."""
        print(f"[*] Chunking {len(documents)} thread documents...")
        
        # Use text splitter for large threads
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=2000,  # Larger chunks for email threads to preserve context
            chunk_overlap=400,  # Good overlap to maintain thread continuity
            separators=["\n--- Email ", "\n\n", "\n", ". ", " ", ""]
        )
        
        chunked_docs = []
        
        for doc in documents:
            # If document is small enough, keep as is
            if len(doc.page_content) <= 2000:
                chunked_docs.append(doc)
            else:
                # Split large threads
                chunks = splitter.split_documents([doc])
                # Preserve metadata in all chunks
                for chunk in chunks:
                    chunk.metadata.update(doc.metadata)
                chunked_docs.extend(chunks)
        
        print(f"[OK] Created {len(chunked_docs)} chunks from {len(documents)} threads")
        return chunked_docs


def process_outlook_content() -> List[Document]:
    """
    Main function to process Outlook emails and return LangChain Documents.
    Called by vectorstore.py during knowledge base building.
    
    If OUTLOOK_FILTER_EMAIL is set, only emails involving that address will be processed.
    """
    print("=" * 60)
    print("PROCESSING OUTLOOK EMAIL THREADS")
    print("=" * 60)
    
    try:
        # Check if filtering is enabled (supports comma-separated list)
        filter_email_str = os.getenv("OUTLOOK_FILTER_EMAIL")
        filter_emails = []
        if filter_email_str:
            # Support multiple emails separated by comma
            filter_emails = [e.strip() for e in filter_email_str.split(',')]
            print(f"[*] FILTER ENABLED: Only emails involving:")
            for fe in filter_emails:
                print(f"    - {fe}")
        
        processor = OutlookProcessor()
        
        # Fetch emails from specified folder
        emails = processor.get_emails_from_folder(
            folder_name=OUTLOOK_FOLDER_NAME,
            max_emails=OUTLOOK_MAX_EMAILS
        )
        
        if not emails:
            print("[WARNING] No emails fetched - check folder name and permissions")
            return []
        
        # Filter emails if OUTLOOK_FILTER_EMAIL is set
        if filter_emails:
            print(f"[*] Filtering {len(emails)} emails for {len(filter_emails)} address(es)...")
            original_count = len(emails)
            
            filtered_emails = []
            for email in emails:
                # Check From
                from_addr = email.get('from', {}).get('emailAddress', {}).get('address', '').lower()
                
                # Check To recipients
                to_addrs = [r.get('emailAddress', {}).get('address', '').lower() 
                           for r in email.get('toRecipients', [])]
                
                # Check CC recipients
                cc_addrs = [r.get('emailAddress', {}).get('address', '').lower() 
                           for r in email.get('ccRecipients', [])]
                
                # Check if ANY filter email is involved
                match_found = False
                for filter_email in filter_emails:
                    filter_lower = filter_email.lower()
                    if (filter_lower in from_addr or 
                        filter_lower in to_addrs or 
                        filter_lower in cc_addrs):
                        match_found = True
                        break
                
                if match_found:
                    filtered_emails.append(email)
            
            emails = filtered_emails
            print(f"[OK] Filtered to {len(emails)} emails (from {original_count})")
            print(f"     Filter rate: {len(emails)/original_count*100:.1f}%")
        
        # Group emails into conversation threads
        conversations = processor.group_emails_by_conversation(emails)
        
        # Convert each thread to a document
        documents = []
        for conv_id, thread in conversations.items():
            doc = processor.format_thread_as_document(thread, OUTLOOK_FOLDER_NAME)
            if doc:
                documents.append(doc)
        
        print(f"[OK] Created {len(documents)} thread documents")
        
        # Chunk large threads
        chunked_documents = processor.chunk_thread_documents(documents)
        
        print("=" * 60)
        print(f"[OK] Outlook processing complete: {len(chunked_documents)} final chunks")
        if filter_emails:
            print("    (Filtered for emails involving: " + ", ".join(filter_emails) + ")")
        print("=" * 60)
        
        return chunked_documents
        
    except Exception as e:
        print(f"[ERROR] Outlook processing failed: {e}")
        import traceback
        traceback.print_exc()
        return []

