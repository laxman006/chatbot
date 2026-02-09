# -*- coding: utf-8 -*-
"""
Jira Tickets & Comments Processor Module

Fetches Jira tickets (customer queries) with comments (developer solutions)
and converts them into LangChain Documents for knowledge base integration.
"""

import json
import os
import re
import warnings
import time
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# Suppress Jira API deprecation warnings (search_issues still works)
warnings.filterwarnings('ignore', message='.*search.*API is deprecated.*')

# Optional Jira import - allows backend to start without jira package
try:
    from jira import JIRA
    from jira.exceptions import JIRAError
    JIRA_AVAILABLE = True
except ImportError:
    JIRA_AVAILABLE = False
    JIRA = None
    JIRAError = Exception

from langchain_core.documents import Document
from config import (
    JIRA_SERVER,
    JIRA_EMAIL,
    JIRA_API_TOKEN,
    JIRA_PROJECT_KEYS,
    JIRA_MAX_ISSUES,
    JIRA_JQL_QUERY,
    JIRA_DATE_FILTER,
    SAVE_JIRA_CHUNKS_JSON,
    JIRA_CHUNKS_JSON_DIR,
)


class JiraProcessor:
    """Processes Jira tickets and comments for chatbot knowledge base."""
    
    def __init__(self):
        self.server = JIRA_SERVER
        self.email = JIRA_EMAIL
        self.api_token = JIRA_API_TOKEN
        # Clean project keys - remove empty strings and filter out invalid project names
        if JIRA_PROJECT_KEYS:
            # Split by comma and clean each key
            raw_keys = JIRA_PROJECT_KEYS.split(',')
            self.project_keys = [key.strip() for key in raw_keys if key.strip() and not key.strip().startswith('#')]
        else:
            self.project_keys = []
        self.max_issues = JIRA_MAX_ISSUES
        # Clean JQL query - remove if it's empty or starts with comment
        self.jql_query = JIRA_JQL_QUERY if JIRA_JQL_QUERY and not JIRA_JQL_QUERY.startswith("#") else ""
        # Default to empty (no date filter) - only use date filter if explicitly set
        self.date_filter = JIRA_DATE_FILTER if JIRA_DATE_FILTER and not JIRA_DATE_FILTER.startswith("#") else ""
        
        # NOTE: Stage 1 chunking removed - using field-aware chunking instead
        # EnhancedVectorstoreBuilder will handle semantic chunking for Description section only
        
        # Initialize Jira client
        self.jira = None
        self._connect()
        
        print(f"[*] Jira Processor initialized")
        print(f"   Server: {self.server}")
        print(f"   Email: {self.email}")
        print(f"   Max Issues: {self.max_issues}")
        if self.project_keys:
            print(f"   Projects: {', '.join(self.project_keys)}")
    
    def _connect(self):
        """Connect to Jira."""
        if not JIRA_AVAILABLE:
            raise ImportError("Jira package is not installed. Install with: pip install jira")
        
        try:
            if not self.api_token:
                raise ValueError("JIRA_API_TOKEN is required")
            
            # Force use of API v3 (v2 is deprecated and removed from Jira Cloud)
            self.jira = JIRA(
                server=self.server,
                basic_auth=(self.email, self.api_token),
                options={'server': self.server, 'rest_api_version': '3'}
            )
            current_user = self.jira.current_user()
            print(f"[OK] Connected to Jira as: {current_user}")
        except Exception as e:
            print(f"[ERROR] Failed to connect to Jira: {e}")
            raise
    
    def _clean_html(self, text: str) -> str:
        """Clean HTML tags from text."""
        if not text:
            return ""
        soup = BeautifulSoup(text, "html.parser")
        return soup.get_text(separator="\n", strip=True)

    def _adf_to_plain_text(self, obj: Any) -> str:
        """
        Convert Atlassian Document Format (ADF) to plain text.
        Handles type 'doc' with content array; walks paragraph, heading, table, list, etc.
        """
        if obj is None:
            return ""
        if isinstance(obj, str):
            return obj.strip()
        if not isinstance(obj, dict):
            return str(obj).strip()
        node_type = obj.get("type") or ""
        content = obj.get("content")
        if not content and node_type != "doc":
            return ""
        if node_type == "doc":
            parts = []
            for child in (content or []):
                parts.append(self._adf_to_plain_text(child))
            return "\n".join(p for p in parts if p).strip()
        if node_type in ("paragraph", "heading", "blockquote"):
            parts = []
            for item in (content or []):
                parts.append(self._adf_node_inline_text(item))
            return " ".join(p for p in parts if p).strip()
        if node_type == "table":
            rows = []
            for row in (content or []):
                if isinstance(row, dict) and row.get("type") == "tableRow":
                    cells = []
                    for cell in row.get("content") or []:
                        if isinstance(cell, dict) and cell.get("type") == "tableCell":
                            cell_parts = []
                            for block in cell.get("content") or []:
                                cell_parts.append(self._adf_to_plain_text(block))
                            cells.append(" ".join(p for p in cell_parts if p))
                    rows.append(" | ".join(cells))
            return "\n".join(rows).strip()
        if node_type in ("bulletList", "orderedList"):
            items = []
            for item in (content or []):
                if isinstance(item, dict) and item.get("type") == "listItem":
                    for block in item.get("content") or []:
                        items.append(self._adf_to_plain_text(block))
            return "\n".join(p for p in items if p).strip()
        if node_type in ("mediaSingle", "media"):
            return "[image]"
        if node_type == "codeBlock":
            return "\n".join(
                self._adf_node_inline_text(item) for item in (content or [])
                if isinstance(item, dict)
            ).strip()
        return ""

    def _adf_node_inline_text(self, node: Any) -> str:
        """Extract text from ADF inline nodes (text, mention, hardBreak, etc.)."""
        if node is None:
            return ""
        if isinstance(node, str):
            return node
        if not isinstance(node, dict):
            return str(node)
        node_type = node.get("type") or ""
        if node_type == "text":
            return (node.get("text") or "").strip()
        if node_type == "mention":
            return (node.get("attrs", {}).get("text") or node.get("text") or "").strip()
        if node_type == "hardBreak":
            return "\n"
        if node_type == "inlineCard":
            return (node.get("attrs", {}).get("url") or "").strip()
        content = node.get("content")
        if content:
            return " ".join(self._adf_node_inline_text(c) for c in content).strip()
        return ""

    def _text_from_field(self, value: Any) -> str:
        """
        Get plain text from description/comment body: ADF dict or HTML string.
        Use in _extract_ticket_data for description and comment.body.
        """
        if value is None:
            return ""
        if isinstance(value, dict) and (value.get("type") == "doc" or "content" in value):
            return self._adf_to_plain_text(value)
        if isinstance(value, str):
            return self._clean_html(value)
        return self._clean_html(str(value))

    def _fetch_issue_keys_page(self, jql: str, start_at: int = 0, max_results: int = 100) -> List[str]:
        """
        Fetch up to max_results issue keys for one request using /rest/api/3/search/jql.
        Jira caps at 100 results per search when fields/expand are used, so we use this
        per date-window (each window returns up to 100 keys). Returns list of issue keys.
        """
        url = f"{self.server}/rest/api/3/search/jql"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        params = {
            'jql': jql,
            'startAt': start_at,
            'maxResults': max_results,
            'fields': 'key',
        }
        for attempt in range(3):
            try:
                response = requests.get(
                    url, headers=headers, params=params,
                    auth=(self.email, self.api_token), timeout=60
                )
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 2 * (2 ** attempt)))
                    print(f"[WARNING] Rate limited. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                    continue
                if response.status_code != 200:
                    if attempt < 2:
                        time.sleep(2 * (2 ** attempt))
                        continue
                    response.raise_for_status()
                data = response.json()
                raw = data.get('issues') or data.get('values') or []
                keys = [i.get('key') for i in raw if i.get('key')]
                time.sleep(0.3)
                return keys
            except requests.exceptions.RequestException as e:
                if attempt < 2:
                    time.sleep(2 * (2 ** attempt))
                    continue
                print(f"[ERROR] Failed to fetch issue keys: {e}")
                return []
        return []

    def _collect_issue_keys_via_date_windows(
        self, base_jql: str, max_keys: int, window_start_date: str = None
    ) -> List[str]:
        """
        Collect issue keys by querying in date windows (each window returns up to 100 keys).
        /rest/api/3/search is 410 Gone; search/jql caps at 100 per query, so we split by
        created date to get 100 keys per window and aggregate.
        window_start_date: optional YYYY-MM-DD to start windows (default: 5 years ago).
        """
        if " ORDER BY " in base_jql:
            base_without_order = base_jql.split(" ORDER BY ")[0].strip()
            order_part = " ORDER BY " + base_jql.split(" ORDER BY ", 1)[1]
        else:
            base_without_order = base_jql
            order_part = " ORDER BY created ASC"
        all_keys = []
        window_months = 6
        now = datetime.now()
        if window_start_date:
            try:
                start_dt = datetime.strptime(window_start_date[:10], "%Y-%m-%d")
            except ValueError:
                start_dt = now - timedelta(days=365 * 5)
        else:
            start_dt = now - timedelta(days=365 * 5)  # 5 years back
        page_size = 100
        while len(all_keys) < max_keys:
            start_at_str = start_dt.strftime("%Y-%m-%d")
            end_dt = start_dt + timedelta(days=30 * window_months)
            if end_dt > now:
                end_dt = now
            end_at_str = end_dt.strftime("%Y-%m-%d")
            window_jql = f"{base_without_order} AND created >= '{start_at_str}' AND created < '{end_at_str}'{order_part}"
            keys = self._fetch_issue_keys_page(window_jql, 0, page_size)
            if keys:
                all_keys.extend(keys)
                print(f"   Keys collected: {len(all_keys)}... (window {start_at_str} to {end_at_str}: {len(keys)} keys)")
            start_dt = end_dt
            if start_dt >= now:
                break
            if len(all_keys) >= max_keys:
                break
            time.sleep(0.5)
        return all_keys[:max_keys]

    def _fetch_full_issue_by_key(self, key: str):
        """
        Fetch a single full issue by key (GET /rest/api/3/issue/{key}) with comments.
        Returns an issue-like object compatible with _extract_ticket_data.
        """
        url = f"{self.server}/rest/api/3/issue/{key}"
        headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
        params = {'expand': 'renderedFields', 'fields': '*all'}
        for attempt in range(2):
            try:
                response = requests.get(
                    url, headers=headers, params=params,
                    auth=(self.email, self.api_token), timeout=45
                )
                if response.status_code == 429:
                    time.sleep(int(response.headers.get('Retry-After', 2)))
                    continue
                if response.status_code != 200:
                    if attempt < 1:
                        time.sleep(1)
                        continue
                    return None
                data = response.json()
                # Comments are not in expand by default; fetch separately
                comments_url = f"{self.server}/rest/api/3/issue/{key}/comment"
                comment_obj = type('obj', (object,), {'comments': []})()
                try:
                    cr = requests.get(
                        comments_url, headers=headers,
                        auth=(self.email, self.api_token), timeout=20
                    )
                    if cr.status_code == 200:
                        for c in cr.json().get('comments', []):
                            comment_obj.comments.append(type('obj', (object,), c)())
                except Exception:
                    pass
                # Build issue object
                fields = data.get('fields', {})
                fields['comment'] = comment_obj
                issue = type('obj', (object,), {
                    'key': data.get('key'),
                    'id': data.get('id'),
                    'fields': type('obj', (object,), fields)()
                })()
                for k, v in fields.items():
                    setattr(issue.fields, k, v)
                if isinstance(issue.fields.project, dict):
                    pd = issue.fields.project
                    issue.fields.project = type('obj', (object,), pd)()
                    for k, v in pd.items():
                        setattr(issue.fields.project, k, v)
                return issue
            except requests.exceptions.RequestException as e:
                if attempt < 1:
                    time.sleep(1)
                    continue
                print(f"[WARNING] Could not fetch issue {key}: {e}")
                return None
        return None

    def _fetch_issues_rest_api(self, jql: str, start_at: int = 0, max_results: int = 100) -> List:
        """
        Fetch issues using REST API directly (bypasses jira-python library).
        Uses the new /rest/api/3/search/jql endpoint.
        NOTE: When fields/expand are used, Jira caps total results at 100 per search.
        For 3000+ tickets use fetch_tickets() which uses two-phase: keys then full issue.
        Includes rate limiting protection with retry logic.
        """
        url = f"{self.server}/rest/api/3/search/jql"
        
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }
        
        params = {
            'jql': jql,
            'startAt': start_at,
            'maxResults': max_results,
            'fields': '*all',
            'expand': 'changelog,renderedFields'
        }
        
        max_retries = 3
        base_delay = 2
        
        for attempt in range(max_retries):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    auth=(self.email, self.api_token),
                    timeout=60
                )
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', base_delay * (2 ** attempt)))
                    print(f"[WARNING] Rate limited. Waiting {retry_after} seconds before retry {attempt + 1}/{max_retries}...")
                    time.sleep(retry_after)
                    continue
                
                # Handle other HTTP errors
                if response.status_code != 200:
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        print(f"[WARNING] API returned {response.status_code}. Retrying in {delay} seconds...")
                        time.sleep(delay)
                        continue
                    else:
                        response.raise_for_status()
                
                data = response.json()
                
                # Convert to JIRA issue objects for compatibility
                issues = []
                for idx, issue_dict in enumerate(data.get('issues', [])):
                    # Create a simple object that mimics JIRA issue
                    issue = type('obj', (object,), {
                        'key': issue_dict['key'],
                        'id': issue_dict['id'],
                        'fields': type('obj', (object,), issue_dict['fields'])()
                    })()
                    
                    # Add fields as attributes
                    for field_name, field_value in issue_dict['fields'].items():
                        setattr(issue.fields, field_name, field_value)
                    
                    # Convert project dict to object for compatibility
                    if hasattr(issue.fields, 'project') and isinstance(issue.fields.project, dict):
                        project_dict = issue.fields.project
                        issue.fields.project = type('obj', (object,), project_dict)()
                        for k, v in project_dict.items():
                            setattr(issue.fields.project, k, v)
                    
                    # Fetch comments separately (not included in search)
                    comments_url = f"{self.server}/rest/api/3/issue/{issue.key}/comment"
                    comment_retries = 2
                    comment_fetched = False
                    
                    for comment_attempt in range(comment_retries):
                        try:
                            comments_response = requests.get(
                                comments_url,
                                headers=headers,
                                auth=(self.email, self.api_token),
                                timeout=30
                            )
                            
                            # Handle rate limiting for comments
                            if comments_response.status_code == 429:
                                retry_after = int(comments_response.headers.get('Retry-After', base_delay * (comment_attempt + 1)))
                                print(f"[WARNING] Rate limited fetching comments for {issue.key}. Waiting {retry_after}s...")
                                time.sleep(retry_after)
                                continue
                            
                            if comments_response.status_code == 200:
                                comments_data = comments_response.json()
                                # Add comments to the issue
                                comment_obj = type('obj', (object,), {
                                    'comments': []
                                })()
                                for comment_dict in comments_data.get('comments', []):
                                    c = type('obj', (object,), comment_dict)()
                                    comment_obj.comments.append(c)
                                issue.fields.comment = comment_obj
                                comment_fetched = True
                                break
                            elif comments_response.status_code >= 500 and comment_attempt < comment_retries - 1:
                                # Retry on server errors
                                delay = base_delay * (comment_attempt + 1)
                                print(f"[WARNING] Server error fetching comments for {issue.key}. Retrying in {delay}s...")
                                time.sleep(delay)
                                continue
                            else:
                                # Other errors - skip comments for this ticket
                                issue.fields.comment = None
                                break
                                
                        except requests.exceptions.RequestException as e:
                            if comment_attempt < comment_retries - 1:
                                delay = base_delay * (comment_attempt + 1)
                                print(f"[WARNING] Error fetching comments for {issue.key}: {e}. Retrying in {delay}s...")
                                time.sleep(delay)
                                continue
                            else:
                                print(f"[WARNING] Could not fetch comments for {issue.key} after {comment_retries} attempts: {e}")
                                issue.fields.comment = None
                                break
                    
                    # Add small delay between comment fetches to avoid rate limits
                    if idx < len(data.get('issues', [])) - 1:  # Don't delay after last ticket
                        time.sleep(0.2)  # 200ms delay between comment API calls
                    
                    issues.append(issue)
                
                # Add delay after successful API call to avoid rate limits
                time.sleep(0.5)  # 500ms delay between page requests
                
                return issues
                
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    print(f"[WARNING] Request failed: {e}. Retrying in {delay} seconds...")
                    time.sleep(delay)
                    continue
                else:
                    print(f"[ERROR] REST API request failed after {max_retries} attempts: {e}")
                    return []
        
        print(f"[ERROR] Failed to fetch issues after {max_retries} retries")
        return []
    
    def _build_date_filter(self, filter_type: str) -> str:
        """Build JQL date filter."""
        if not filter_type:
            return ""
        
        now = datetime.now()
        
        if filter_type == "last_month":
            date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            return f"updated >= '{date}'"
        elif filter_type == "last_3_months":
            date = (now - timedelta(days=90)).strftime("%Y-%m-%d")
            return f"updated >= '{date}'"
        elif filter_type == "last_5_months":
            date = (now - timedelta(days=150)).strftime("%Y-%m-%d")
            return f"updated >= '{date}'"
        elif filter_type == "last_6_months":
            date = (now - timedelta(days=180)).strftime("%Y-%m-%d")
            return f"updated >= '{date}'"
        elif filter_type == "last_year":
            date = (now - timedelta(days=365)).strftime("%Y-%m-%d")
            return f"updated >= '{date}'"
        else:
            return ""
    
    def _build_jql_query(self) -> str:
        """Build JQL query based on configuration."""
        if self.jql_query:
            # Use custom JQL query
            return self.jql_query
        
        # Build query from project keys and filters
        jql_parts = []
        
        # Project filter (supports multiple projects: PRI, QAB, etc.)
        if self.project_keys:
            project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
            jql_parts.append(f"({project_filter})")
        
        # Status filter - get resolved/closed tickets (solved issues)
        # Support different status name variations across boards:
        # - "Resolved" (standard - PRI board)
        # - "Resolved-" (QAB board - with dash)
        # - "Closed"
        status_filter = "(status = Resolved OR status = 'Resolved-' OR status = Closed)"
        jql_parts.append(status_filter)
        
        # Note: We'll filter for comments in Python since commentCount may not be available
        
        # Date filter
        if self.date_filter:
            date_filter = self._build_date_filter(self.date_filter)
            if date_filter:
                jql_parts.append(date_filter)
        
        # Stable ordering for correct pagination (updated DESC causes page drift in Jira Search API)
        jql = " AND ".join(jql_parts) + " ORDER BY created ASC"
        
        return jql
    
    def _build_jql_query_with_date_range(self, start_date: str = None, end_date: str = None) -> str:
        """
        Build JQL query with custom date range (for incremental updates).
        
        Args:
            start_date: Start date/datetime in YYYY-MM-DD or YYYY-MM-DD HH:mm format
            end_date: End date/datetime in YYYY-MM-DD or YYYY-MM-DD HH:mm format (None = till now)
        
        Returns:
            JQL query string
        """
        jql_parts = []
        
        # Project filter (supports multiple projects: PRI, QAB, etc.)
        if self.project_keys:
            project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
            jql_parts.append(f"({project_filter})")
        
        # Status filter - resolved/closed tickets
        # Support different status name variations across boards
        status_filter = "(status = Resolved OR status = 'Resolved-' OR status = Closed)"
        jql_parts.append(status_filter)
        
        # Date filter
        if start_date:
            jql_parts.append(f"updated >= '{start_date}'")
        
        if end_date:
            jql_parts.append(f"updated <= '{end_date}'")
        
        # Stable ordering for correct pagination (updated DESC causes page drift in Jira Search API)
        jql = " AND ".join(jql_parts) + " ORDER BY created ASC"
        
        return jql
    
    def fetch_tickets_since(self, since_date: str, max_issues: int = None) -> List[Dict[str, Any]]:
        """
        Fetch tickets updated since a specific date/datetime (for incremental updates).
        
        Args:
            since_date: Date/datetime string in YYYY-MM-DD or YYYY-MM-DD HH:mm format
            max_issues: Maximum issues to fetch (None = use self.max_issues)
        
        Returns:
            List of ticket data dictionaries
        """
        print(f"[*] Fetching tickets updated since {since_date}...")
        
        jql = self._build_jql_query_with_date_range(start_date=since_date)
        print(f"[*] JQL Query: {jql}")
        
        max_fetch = max_issues if max_issues else self.max_issues
        all_tickets = []
        
        try:
            # Phase 1: Collect issue keys via date windows (search/jql caps at 100 per query)
            window_start = since_date[:10] if since_date else None
            all_keys = self._collect_issue_keys_via_date_windows(jql, max_fetch, window_start_date=window_start)
            keys_to_fetch = all_keys[:max_fetch]
            # Phase 2: Fetch full issue per key
            for idx, key in enumerate(keys_to_fetch):
                if len(all_tickets) >= max_fetch:
                    break
                issue = self._fetch_full_issue_by_key(key)
                if issue:
                    ticket_data = self._extract_ticket_data(issue)
                    if ticket_data:
                        all_tickets.append(ticket_data)
                if (idx + 1) % 100 == 0 or idx + 1 == len(keys_to_fetch):
                    print(f"   Fetched {len(all_tickets)}/{max_fetch} tickets...")
                time.sleep(0.15)
            print(f"[OK] Total fetched: {len(all_tickets)} tickets since {since_date}")
            return all_tickets
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch tickets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def fetch_tickets(self) -> List[Dict[str, Any]]:
        """Fetch tickets from Jira.
        Uses two-phase fetch: (1) paginate keys via search/jql without fields/expand
        so Jira returns more than 100 results; (2) fetch full issue per key.
        """
        print(f"[*] Fetching tickets from Jira (two-phase: keys then full issues)...")
        
        jql = self._build_jql_query()
        print(f"[*] JQL Query: {jql}")
        
        all_tickets = []
        
        try:
            # Phase 1: Collect issue keys via date windows (search/jql caps at 100 per query;
            # /rest/api/3/search is 410 Gone, so we use search/jql per 6-month window)
            all_keys = self._collect_issue_keys_via_date_windows(jql, self.max_issues)
            keys_to_fetch = all_keys[:self.max_issues]
            print(f"[*] Fetching full details for {len(keys_to_fetch)} issues...")
            
            # Phase 2: Fetch full issue for each key and extract ticket data
            for idx, key in enumerate(keys_to_fetch):
                if len(all_tickets) >= self.max_issues:
                    break
                issue = self._fetch_full_issue_by_key(key)
                if issue:
                    ticket_data = self._extract_ticket_data(issue)
                    if ticket_data:
                        all_tickets.append(ticket_data)
                if (idx + 1) % 100 == 0 or idx + 1 == len(keys_to_fetch):
                    print(f"   Fetched {len(all_tickets)}/{self.max_issues} tickets (processed {idx + 1} issues)...")
                time.sleep(0.15)  # Rate limit: ~6–7 issues/sec
            
            # If no tickets found, try fallback query (any tickets, filter by comments in Python)
            if len(all_tickets) == 0:
                print("[WARNING] No resolved tickets with comments found. Trying fallback: any tickets...")
                fallback_jql_parts = []
                
                if self.project_keys:
                    project_filter = " OR ".join([f"project = {key}" for key in self.project_keys])
                    fallback_jql_parts.append(f"({project_filter})")
                else:
                    # Need at least one project - use CFITS as default
                    fallback_jql_parts.append("project = CFITS")
                
                if self.date_filter:
                    date_filter = self._build_date_filter(self.date_filter)
                    if date_filter:
                        fallback_jql_parts.append(date_filter)
                
                fallback_jql = " AND ".join(fallback_jql_parts) + " ORDER BY created ASC"
                print(f"[*] Fallback JQL Query: {fallback_jql}")
                
                issues = self._fetch_issues_rest_api(
                    fallback_jql,
                    start_at=0,
                    max_results=min(200, self.max_issues * 3)
                )
                
                for issue in issues:
                    ticket_data = self._extract_ticket_data(issue)
                    if ticket_data:
                        all_tickets.append(ticket_data)
                        if len(all_tickets) >= self.max_issues:
                            break
                
                print(f"[OK] Fallback query found {len(all_tickets)} tickets with comments")
            
            print(f"[OK] Total fetched: {len(all_tickets)} tickets")
            return all_tickets
            
        except JIRAError as e:
            print(f"[ERROR] Jira API error: {e}")
            print(f"[INFO] Try running test_jira_diagnostic.py to find correct status names")
            return []
        except Exception as e:
            print(f"[ERROR] Failed to fetch tickets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _extract_ticket_data(self, issue) -> Optional[Dict[str, Any]]:
        """Extract ticket data from Jira issue."""
        try:
            # Get description (customer query); may be ADF dict or HTML string
            description = ""
            if hasattr(issue.fields, 'description') and issue.fields.description:
                description = self._text_from_field(issue.fields.description)
            
            # Get comments (developer solutions) - fetch explicitly if not in expand
            comments = []
            
            try:
                # Try to get comments from fields first
                if hasattr(issue.fields, 'comment') and issue.fields.comment:
                    for comment in issue.fields.comment.comments:
                        raw_body = getattr(comment, 'body', None)
                        comment_body = self._text_from_field(raw_body)
                        if comment_body.strip():
                            comments.append({
                                "author": str(comment.author),
                                "body": comment_body,
                                "created": str(comment.created),
                                "updated": str(comment.updated) if hasattr(comment, 'updated') else None
                            })
                
                # If no comments found, fetch them explicitly
                if not comments:
                    issue_with_comments = self.jira.issue(issue.key, expand='comments')
                    if hasattr(issue_with_comments.fields, 'comment') and issue_with_comments.fields.comment:
                        for comment in issue_with_comments.fields.comment.comments:
                            raw_body = getattr(comment, 'body', None)
                            comment_body = self._text_from_field(raw_body)
                            if comment_body.strip():
                                comments.append({
                                    "author": str(comment.author),
                                    "body": comment_body,
                                    "created": str(comment.created),
                                    "updated": str(comment.updated) if hasattr(comment, 'updated') else None
                                })
            except Exception as e:
                print(f"[WARNING] Could not fetch comments for {issue.key}: {e}")
            
            # Extract custom fields: Root Cause, Combination, and Fix Description
            root_cause = self._extract_custom_field(issue, 'customfield_10059', 'Root Cause')
            combination = self._extract_custom_field(issue, 'customfield_10236', 'Combination')
            fix_description = self._extract_custom_field(issue, 'customfield_10402', 'Fix Description')
            
            # Return tickets with description (comments optional but preferred)
            if not description.strip():
                return None
            
            return {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": description,
                "status": str(issue.fields.status),
                "issue_type": str(issue.fields.issuetype),
                "priority": str(issue.fields.priority) if hasattr(issue.fields, 'priority') else "N/A",
                "assignee": str(issue.fields.assignee) if issue.fields.assignee else "Unassigned",
                "reporter": str(issue.fields.reporter) if issue.fields.reporter else "Unknown",
                "created": str(issue.fields.created),
                "updated": str(issue.fields.updated),
                "resolved": str(issue.fields.resolutiondate) if hasattr(issue.fields, 'resolutiondate') and issue.fields.resolutiondate else None,
                "url": f"{self.server}/browse/{issue.key}",
                "project_key": issue.fields.project.key if hasattr(issue.fields.project, 'key') else (issue.fields.project.get('key', 'UNKNOWN') if isinstance(issue.fields.project, dict) else 'UNKNOWN'),
                "root_cause": root_cause,
                "combination": combination,
                "fix_description": fix_description,
                "comments": comments,
            }
        except Exception as e:
            print(f"[WARNING] Failed to extract data from {issue.key}: {e}")
            return None
    
    def _extract_custom_field(self, issue, field_id: str, field_name: str) -> Optional[str]:
        """Extract custom field value safely."""
        try:
            if hasattr(issue.fields, field_id):
                field_value = getattr(issue.fields, field_id)
                if field_value:
                    # Handle different field types
                    if isinstance(field_value, str):
                        return self._clean_html(field_value)
                    elif isinstance(field_value, list):
                        # Handle multi-select fields (like Combination)
                        values = []
                        for item in field_value:
                            if hasattr(item, 'value'):
                                values.append(str(item.value))
                            elif isinstance(item, dict):
                                values.append(str(item.get('value', item)))
                            else:
                                values.append(str(item))
                        return ', '.join(values) if values else None
                    elif isinstance(field_value, dict):
                        # ADF (Atlassian Document Format) for Rich Text custom fields
                        if field_value.get("type") == "doc" or "content" in field_value:
                            return self._adf_to_plain_text(field_value)
                        return str(field_value.get('value', field_value))
                    elif hasattr(field_value, 'value'):
                        # JIRA CustomFieldOption objects
                        return str(field_value.value)
                    else:
                        return str(field_value)
        except Exception as e:
            print(f"[WARNING] Could not extract {field_name} ({field_id}) for {issue.key}: {e}")
        return None
    
    def format_ticket_documents(self, ticket_data: Dict[str, Any]) -> List[Document]:
        """
        Create field-aware chunks from Jira ticket.
        Each section becomes a separate chunk with proper metadata.
        
        Chunking Strategy:
        - Summary: Single chunk (no splitting)
        - Description: Single chunk (or semantically chunked by pipeline if enabled)
        - Root Cause: Single chunk (NEVER split - critical section)
        - Fix Description: Single chunk (NEVER split)
        - Comments: One chunk per comment (no splitting)
        """
        documents = []
        ticket_key = ticket_data['key']
        base_metadata = {
            "doc_id": ticket_key,
            "source_type": "jira",
            "source": "jira_ticket",
            "tag": f"jira/{ticket_data['project_key'].lower()}",
            "ticket_key": ticket_key,
            "ticket_summary": ticket_data['summary'],
            "status": ticket_data['status'],
            "issue_type": ticket_data['issue_type'],
            "priority": ticket_data['priority'],
            "reporter": ticket_data['reporter'],
            "assignee": ticket_data['assignee'],
            "project_key": ticket_data['project_key'],
            "created": ticket_data['created'],
            "updated": ticket_data['updated'],
            "resolved": ticket_data['resolved'] or "",
            "combination": ticket_data.get('combination', ''),
            "root_cause": ticket_data.get('root_cause', ''),
            "fix_description": ticket_data.get('fix_description', ''),
            "comments_count": len(ticket_data['comments']),
            "url": ticket_data['url']
        }
        
        # === 1. SUMMARY CHUNK (No chunking - single chunk) ===
        summary_content = f"""# Jira Ticket: {ticket_key}
Summary: {ticket_data['summary']}
Status: {ticket_data['status']}
Priority: {ticket_data['priority']}
Created: {ticket_data['created']}
Updated: {ticket_data['updated']}
Resolved: {ticket_data.get('resolved', 'N/A')}
Reporter: {ticket_data['reporter']}
Assignee: {ticket_data['assignee']}"""
        
        if ticket_data.get('combination'):
            summary_content += f"\nCombination: {ticket_data['combination']}"
        
        summary_doc = Document(
            page_content=summary_content,
            metadata={
                **base_metadata,
                "section": "summary",
                "section_priority": "high",
                "ticket_chunk_type": "summary",
            }
        )
        documents.append(summary_doc)
        
        # === 2. DESCRIPTION CHUNK (Semantic chunking - 400-500 tokens) ===
        if ticket_data.get('description'):
            description_content = f"""## Description
Reporter: {ticket_data['reporter']}

{ticket_data['description']}"""
            
            description_doc = Document(
                page_content=description_content,
                metadata={
                    **base_metadata,
                    "section": "description",
                    "section_priority": "high",
                    "ticket_chunk_type": "problem",
                }
            )
            documents.append(description_doc)
        
        # === 3. ROOT CAUSE CHUNK (Single chunk - NEVER split) ===
        if ticket_data.get('root_cause'):
            root_cause_content = f"""## Root Cause

{ticket_data['root_cause']}"""
            
            root_cause_doc = Document(
                page_content=root_cause_content,
                metadata={
                    **base_metadata,
                    "section": "root_cause",
                    "section_priority": "critical",  # Highest priority
                    "root_cause": ticket_data['root_cause'],  # Keep full text in metadata
                    "ticket_chunk_type": "problem",
                }
            )
            documents.append(root_cause_doc)
        
        # === 3.5. FIX DESCRIPTION CHUNK (Single chunk - NEVER split) ===
        if ticket_data.get('fix_description'):
            fix_description_content = f"""## Fix Description

{ticket_data['fix_description']}"""
            
            fix_description_doc = Document(
                page_content=fix_description_content,
                metadata={
                    **base_metadata,
                    "section": "fix_description",
                    "section_priority": "critical",  # Highest priority
                    "fix_description": ticket_data['fix_description'],  # Keep full text in metadata
                    "ticket_chunk_type": "resolution",
                }
            )
            documents.append(fix_description_doc)
        
        # === 4. COMMENTS CHUNKS (One chunk per comment) ===
        for idx, comment in enumerate(ticket_data['comments'], 1):
            comment_content = f"""## Developer Solution {idx}

Author: {comment['author']}
Date: {comment['created'][:10]}

{comment['body']}"""
            
            comment_doc = Document(
                page_content=comment_content,
                metadata={
                    **base_metadata,
                    "section": "comment",
                    "section_priority": "medium",
                    "comment_index": idx,
                    "comment_author": comment['author'],
                    "comment_date": comment['created'],
                    "ticket_chunk_type": "resolution",
                }
            )
            documents.append(comment_doc)
        
        return documents

    def _save_chunks_json(self, all_documents: List[Document]) -> None:
        """
        Save how each ticket was chunked for Weaviate to JSON (section, ticket_chunk_type, content per chunk).
        Writes to data/jira_ingestion/jira_chunks_latest.json and a timestamped copy for audit.
        """
        if not SAVE_JIRA_CHUNKS_JSON or not all_documents:
            return
        out_dir = Path(JIRA_CHUNKS_JSON_DIR)
        out_dir.mkdir(parents=True, exist_ok=True)
        # Group by doc_id (ticket_key)
        by_doc: Dict[str, List[Document]] = {}
        for doc in all_documents:
            doc_id = (doc.metadata.get("doc_id") or "").strip() or "unknown"
            if doc_id not in by_doc:
                by_doc[doc_id] = []
            by_doc[doc_id].append(doc)
        tickets_payload = []
        for doc_id, docs in by_doc.items():
            ticket_key = doc_id
            chunks_list = []
            for doc in docs:
                meta = doc.metadata
                chunk_entry = {
                    "section": meta.get("section", ""),
                    "ticket_chunk_type": meta.get("ticket_chunk_type", ""),
                    "content": doc.page_content or "",
                }
                if meta.get("section") == "comment" and meta.get("comment_index") is not None:
                    chunk_entry["comment_index"] = meta["comment_index"]
                chunks_list.append(chunk_entry)
            tickets_payload.append({
                "ticket_key": ticket_key,
                "doc_id": doc_id,
                "chunks": chunks_list,
                "chunk_count": len(chunks_list),
            })
        now = datetime.utcnow()
        timestamp_str = now.strftime("%Y-%m-%dT%H%M%SZ")
        payload = {
            "ingestion_timestamp": timestamp_str,
            "source": "jira",
            "collection": "JiraTickets",
            "tickets": tickets_payload,
            "total_tickets": len(tickets_payload),
            "total_chunks": len(all_documents),
        }
        latest_path = out_dir / "jira_chunks_latest.json"
        ts_path = out_dir / f"jira_chunks_{now.strftime('%Y%m%d_%H%M%S')}.json"
        try:
            with open(latest_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            with open(ts_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
            print(f"[OK] Saved chunk structure to {latest_path} and {ts_path}")
        except Exception as e:
            print(f"[WARNING] Could not save Jira chunks JSON: {e}")
    
    def process_jira_content(self) -> List[Document]:
        """
        Process Jira tickets with field-aware chunking.
        Returns field-aware chunks directly (no Stage 1 chunking).
        EnhancedVectorstoreBuilder will handle semantic chunking for Description section only.
        """
        print("[*] Processing Jira tickets with field-aware chunking...")
        
        # Fetch tickets
        tickets = self.fetch_tickets()
        
        if not tickets:
            print("[WARNING] No tickets found")
            return []
        
        # Create field-aware documents
        all_documents = []
        for ticket in tickets:
            field_docs = self.format_ticket_documents(ticket)
            all_documents.extend(field_docs)
        
        print(f"[OK] Created {len(all_documents)} field-aware chunks from {len(tickets)} tickets")
        print(f"     Sections: Summary={sum(1 for d in all_documents if d.metadata.get('section') == 'summary')}, "
              f"Description={sum(1 for d in all_documents if d.metadata.get('section') == 'description')}, "
              f"Root Cause={sum(1 for d in all_documents if d.metadata.get('section') == 'root_cause')}, "
              f"Fix Description={sum(1 for d in all_documents if d.metadata.get('section') == 'fix_description')}, "
              f"Comments={sum(1 for d in all_documents if d.metadata.get('section') == 'comment')}")
        
        # Save chunk structure to JSON (how each ticket was chunked for Weaviate) for audit/debug
        self._save_chunks_json(all_documents)
        
        # Return documents directly - EnhancedVectorstoreBuilder will handle semantic chunking
        # for Description section only (if needed)
        return all_documents


def process_jira_content() -> List[Document]:
    """Main entry point for processing Jira content."""
    processor = JiraProcessor()
    return processor.process_jira_content()
