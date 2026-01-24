# -*- coding: utf-8 -*-
"""
Jira Tickets & Comments Processor Module

Fetches Jira tickets (customer queries) with comments (developer solutions)
and converts them into LangChain Documents for knowledge base integration.
"""

import os
import re
import warnings
import time
import requests
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
    JIRA_DATE_FILTER
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
    
    def _fetch_issues_rest_api(self, jql: str, start_at: int = 0, max_results: int = 100) -> List:
        """
        Fetch issues using REST API directly (bypasses jira-python library).
        Uses the new /rest/api/3/search/jql endpoint.
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
        
        # Order by most recently updated
        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        
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
        
        # Order by most recently updated
        jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
        
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
        start_at = 0
        max_results_per_page = 100
        
        try:
            while len(all_tickets) < max_fetch:
                page_size = min(max_results_per_page, max_fetch - len(all_tickets))
                issues = self._fetch_issues_rest_api(jql, start_at, page_size)
                
                if not issues:
                    break
                
                for issue in issues:
                    ticket_data = self._extract_ticket_data(issue)
                    if ticket_data:
                        all_tickets.append(ticket_data)
                        if len(all_tickets) >= max_fetch:
                            break
                
                print(f"   Fetched {len(all_tickets)}/{max_fetch} tickets...")
                
                if len(issues) < max_results_per_page:
                    break
                
                start_at += len(issues)
            
            print(f"[OK] Total fetched: {len(all_tickets)} tickets since {since_date}")
            return all_tickets
            
        except Exception as e:
            print(f"[ERROR] Failed to fetch tickets: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def fetch_tickets(self) -> List[Dict[str, Any]]:
        """Fetch tickets from Jira."""
        print(f"[*] Fetching tickets from Jira...")
        
        jql = self._build_jql_query()
        print(f"[*] JQL Query: {jql}")
        
        all_tickets = []
        start_at = 0
        max_results_per_page = 100
        
        try:
            # Use REST API directly (Jira v3 /search/jql endpoint)
            # This bypasses jira-python library which hasn't updated to new endpoint
            checked_count = 0
            
            while len(all_tickets) < self.max_issues:
                page_size = min(100, self.max_issues - len(all_tickets))
                issues = self._fetch_issues_rest_api(jql, start_at, page_size)
                
                if not issues:
                    break
                
                checked_count += len(issues)
                for issue in issues:
                    ticket_data = self._extract_ticket_data(issue)
                    if ticket_data:
                        all_tickets.append(ticket_data)
                        if len(all_tickets) >= self.max_issues:
                            break
                
                print(f"   Fetched {len(all_tickets)}/{self.max_issues} tickets (checked {checked_count} total)...")
                
                # Break if we got fewer than page size (last page)
                if len(issues) < page_size:
                    break
                
                start_at += len(issues)
                
                # Add delay between pages to avoid rate limits
                if len(all_tickets) < self.max_issues:
                    time.sleep(1)  # 1 second delay between pages
                
                if len(all_tickets) >= self.max_issues:
                    break
            
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
                
                fallback_jql = " AND ".join(fallback_jql_parts) + " ORDER BY updated DESC"
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
            # Get description (customer query)
            description = ""
            if hasattr(issue.fields, 'description') and issue.fields.description:
                description = self._clean_html(str(issue.fields.description))
            
            # Get comments (developer solutions) - fetch explicitly if not in expand
            comments = []
            ai_suggestions = None
            
            try:
                # Try to get comments from fields first
                if hasattr(issue.fields, 'comment') and issue.fields.comment:
                    for comment in issue.fields.comment.comments:
                        comment_body = self._clean_html(str(comment.body))
                        if comment_body.strip():
                            # Check if this comment contains AI suggestions
                            is_ai_suggestion = self._is_ai_suggestion_comment(comment_body)
                            
                            if is_ai_suggestion:
                                # Extract AI suggestions from comment
                                ai_suggestions = self._extract_suggestions_from_comment(comment_body)
                                print(f"[OK] Found AI suggestions in comment for {issue.key}")
                            else:
                                # Regular comment
                                comments.append({
                                    "author": str(comment.author),
                                    "body": comment_body,
                                    "created": str(comment.created),
                                    "updated": str(comment.updated) if hasattr(comment, 'updated') else None
                                })
                
                # If no comments found, fetch them explicitly
                if not comments and not ai_suggestions:
                    issue_with_comments = self.jira.issue(issue.key, expand='comments')
                    if hasattr(issue_with_comments.fields, 'comment') and issue_with_comments.fields.comment:
                        for comment in issue_with_comments.fields.comment.comments:
                            comment_body = self._clean_html(str(comment.body))
                            if comment_body.strip():
                                # Check if this comment contains AI suggestions
                                is_ai_suggestion = self._is_ai_suggestion_comment(comment_body)
                                
                                if is_ai_suggestion:
                                    # Extract AI suggestions from comment
                                    ai_suggestions = self._extract_suggestions_from_comment(comment_body)
                                    print(f"[OK] Found AI suggestions in comment for {issue.key}")
                                else:
                                    # Regular comment
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
            
            # Return tickets with description (comments or ai_suggestions are optional but preferred)
            # For now, we'll accept tickets with just description to see what we can extract
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
                "root_cause": root_cause,  # Root Cause
                "combination": combination,  # Combination field
                "fix_description": fix_description,  # Fix Description
                "comments": comments,
                "ai_suggestions": ai_suggestions  # Add AI suggestions
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
                        # Some custom fields return dicts
                        return str(field_value.get('value', field_value))
                    elif hasattr(field_value, 'value'):
                        # JIRA CustomFieldOption objects
                        return str(field_value.value)
                    else:
                        return str(field_value)
        except Exception as e:
            print(f"[WARNING] Could not extract {field_name} ({field_id}) for {issue.key}: {e}")
        return None
    
    def _is_ai_suggestion_comment(self, comment_body: str) -> bool:
        """Check if a comment contains AI-generated suggestions."""
        comment_lower = comment_body.lower()
        # Look for AI suggestion markers
        ai_markers = [
            'uses ai',
            'verify results',
            'ai-generated',
            'rovo',
            'ai suggestion',
            '↑ uses ai'
        ]
        return any(marker in comment_lower for marker in ai_markers)
    
    def _extract_suggestions_from_comment(self, comment_body: str) -> Optional[Dict[str, Any]]:
        """Extract structured AI suggestions from comment text."""
        # Clean the comment body
        text = comment_body.strip()
        
        # Look for solution section
        solution_steps = []
        
        # Pattern 1: Numbered list (1. 2. 3. etc.)
        numbered_pattern = r'(\d+)\.\s+([^\n]+)'
        numbered_matches = re.findall(numbered_pattern, text)
        
        if numbered_matches:
            for num, step in numbered_matches:
                step_clean = step.strip()
                # Filter out very short or non-meaningful steps
                if len(step_clean) > 15 and not step_clean.lower().startswith(('step', 'solution')):
                    solution_steps.append(step_clean)
        
        # Pattern 2: If no numbered list, look for "Solution:" section
        if not solution_steps:
            solution_match = re.search(r'solution:?\s*\n(.*?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
            if solution_match:
                solution_text = solution_match.group(1)
                # Try to extract steps from solution text
                lines = solution_text.split('\n')
                for line in lines:
                    line = line.strip()
                    # Look for lines that start with dash or number
                    if re.match(r'^[-*•]\s+', line) or re.match(r'^\d+[.)]\s+', line):
                        step = re.sub(r'^[-*•\d.)]\s+', '', line)
                        if len(step) > 15:
                            solution_steps.append(step)
        
        # Pattern 3: Extract summary text before solution
        summary = None
        summary_match = re.search(r'^([^S]*?)(?=Solution:)', text, re.IGNORECASE | re.DOTALL)
        if summary_match:
            summary_text = summary_match.group(1).strip()
            # Clean up summary
            summary_lines = [line.strip() for line in summary_text.split('\n') if line.strip()]
            if summary_lines:
                summary = ' '.join(summary_lines[:3])  # First 3 lines as summary
        
        if solution_steps:
            return {
                "summary": summary,
                "solution_steps": solution_steps,
                "step_count": len(solution_steps),
                "source": "ai_suggestion_comment"
            }
        
        return None
    
    def format_ticket_documents(self, ticket_data: Dict[str, Any]) -> List[Document]:
        """
        Create field-aware chunks from Jira ticket.
        Each section becomes a separate chunk with proper metadata.
        
        Chunking Strategy:
        - Summary: Single chunk (no splitting)
        - Description: Will be semantically chunked (400-500 tokens) by EnhancedVectorstoreBuilder
        - Root Cause: Single chunk (NEVER split - critical section)
        - Comments: One chunk per comment (no splitting)
        - AI Suggestions: Single chunk (no splitting)
        """
        documents = []
        ticket_key = ticket_data['key']
        base_metadata = {
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
            "has_ai_suggestions": bool(ticket_data.get('ai_suggestions')),
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
                "section_priority": "high"
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
                    "section_priority": "high"
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
                    "root_cause": ticket_data['root_cause']  # Keep full text in metadata
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
                    "fix_description": ticket_data['fix_description']  # Keep full text in metadata
                }
            )
            documents.append(fix_description_doc)
        
        # === 4. AI SUGGESTIONS CHUNK (Optional - Single chunk per suggestion) ===
        # NOTE: AI suggestions are optional - if not present, this section is skipped
        if ticket_data.get('ai_suggestions'):
            suggestions = ticket_data['ai_suggestions']
            ai_content_parts = [
                "## AI-Generated Solution (Rovo)",
                "",
                "**Note:** This is an AI-generated solution. Verify results.",
                ""
            ]
            
            if suggestions.get('summary'):
                ai_content_parts.append(f"**Summary:** {suggestions['summary']}")
                ai_content_parts.append("")
            
            if suggestions.get('solution_steps'):
                ai_content_parts.append("**Solution Steps:**")
                ai_content_parts.append("")
                for idx, step in enumerate(suggestions['solution_steps'], 1):
                    ai_content_parts.append(f"{idx}. {step}")
            
            ai_doc = Document(
                page_content="\n".join(ai_content_parts),
                metadata={
                    **base_metadata,
                    "section": "ai_suggestions",
                    "section_priority": "critical",
                    "ai_solution_steps": suggestions.get('step_count', 0)
                }
            )
            documents.append(ai_doc)
        
        # === 5. COMMENTS CHUNKS (One chunk per comment) ===
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
                    "comment_date": comment['created']
                }
            )
            documents.append(comment_doc)
        
        return documents
    
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
              f"Comments={sum(1 for d in all_documents if d.metadata.get('section') == 'comment')}, "
              f"AI Suggestions={sum(1 for d in all_documents if d.metadata.get('section') == 'ai_suggestions')}")
        
        # Return documents directly - EnhancedVectorstoreBuilder will handle semantic chunking
        # for Description section only (if needed)
        return all_documents


def process_jira_content() -> List[Document]:
    """Main entry point for processing Jira content."""
    processor = JiraProcessor()
    return processor.process_jira_content()
