# -*- coding: utf-8 -*-
"""
Unified trace processing and filtering utilities for accurate team analytics.

This module ensures consistent trace filtering across all analytics endpoints
by providing centralized functions for:
- Date validation and timezone handling
- Email-to-team mapping
- Trace assignment and validation
- Comprehensive logging and diagnostics
"""

from datetime import datetime, timezone
from typing import Dict, List, Tuple, Optional, Any
from collections import Counter
import logging
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)


class TraceFilteringStats:
    """Track statistics about trace filtering for diagnostics."""
    
    def __init__(self):
        self.total_fetched = 0
        self.traces_filtered = 0
        self.traces_out_of_date_range = 0
        self.traces_without_date = 0
        self.traces_without_email = 0
        self.traces_with_email = 0
        self.traces_unassigned = 0
        self.unassigned_emails = set()
        self.invalid_emails = set()
        self.assigned_per_team: Dict[str, int] = {}
        self.metadata_keys_with_email = Counter()
        self.metadata_keys_missing_email = Counter()
        self.trace_keys_with_email = Counter()
        self.trace_keys_missing_email = Counter()
        self.sample_with_email = []
        self.sample_missing_email = []
        self.sample_limit = 5

    def record_trace_sample(self, trace: Dict[str, Any], metadata: Dict[str, Any], has_email: bool):
        """Record a small sample for diagnostics."""
        sample = {
            "trace_id": trace.get("id"),
            "user_id": trace.get("userId"),
            "metadata_keys": sorted(list(metadata.keys()))[:10],
            "metadata_user_name": metadata.get("user_name"),
            "metadata_user_email": metadata.get("user_email"),
            "input_type": type(trace.get("input", None)).__name__,
        }
        target_list = self.sample_with_email if has_email else self.sample_missing_email
        if len(target_list) < self.sample_limit:
            target_list.append(sample)

    def common_metadata_keys(self) -> List[str]:
        """Get metadata keys common to both traced and missing-email traces."""
        return sorted(set(self.metadata_keys_with_email) & set(self.metadata_keys_missing_email))

    def common_trace_keys(self) -> List[str]:
        """Get top-level trace keys common to both trace groups."""
        return sorted(set(self.trace_keys_with_email) & set(self.trace_keys_missing_email))
    
    def log_summary(self, page: int, batch_size: int):
        """Log page processing summary."""
        print(f"[INFO] Page {page} summary:")
        print(f"  - Fetched: {self.total_fetched}")
        print(f"  - Filtered: {self.traces_filtered}")
        print(f"  - Out of date range: {self.traces_out_of_date_range}")
        print(f"  - Missing date field: {self.traces_without_date}")
        print(f"  - Missing email: {self.traces_without_email}")
        print(f"  - Unassigned: {self.traces_unassigned}")
        if self.unassigned_emails:
            print(f"  - Unassigned emails (sample): {list(self.unassigned_emails)[:5]}")
    
    def log_final_summary(self):
        """Log final summary."""
        print(f"\n[INFO] ==== TRACE FILTERING FINAL SUMMARY ====")
        print(f"Total fetched: {self.total_fetched}")
        print(f"Successfully filtered: {self.traces_filtered}")
        print(f"Filtered out (date range): {self.traces_out_of_date_range}")
        print(f"Skipped (no date): {self.traces_without_date}")
        print(f"Skipped (no email): {self.traces_without_email}")
        print(f"Unassigned emails: {self.traces_unassigned}")
        print(f"  - Unique unassigned emails: {len(self.unassigned_emails)}")
        if self.unassigned_emails:
            print(f"  - All unassigned emails: {sorted(self.unassigned_emails)}")
        if self.assigned_per_team:
            print(f"\nTraces by team:")
            for team, count in sorted(self.assigned_per_team.items(), key=lambda x: x[1], reverse=True):
                print(f"  - {team}: {count}")
        print(f"========================================\n")


def validate_and_parse_trace_date(
    trace_created_at: Any, 
    start_time: Optional[datetime] = None, 
    end_time: Optional[datetime] = None
) -> Tuple[Optional[datetime], bool]:
    """
    Validate and parse trace createdAt timestamp with proper timezone handling.
    
    Args:
        trace_created_at: The createdAt value from trace (string or datetime)
        start_time: Optional start time for validation
        end_time: Optional end time for validation
    
    Returns:
        Tuple of (parsed_datetime, is_within_range)
        - parsed_datetime: None if parsing failed
        - is_within_range: False if outside date range, True if within or no range specified
    """
    if not trace_created_at:
        return None, False
    
    try:
        # Parse the createdAt timestamp
        if isinstance(trace_created_at, str):
            # Handle ISO format strings with or without Z
            trace_created_at_clean = trace_created_at.replace('Z', '+00:00')
            
            # If no timezone info, add UTC
            if '+' not in trace_created_at_clean and 'T' in trace_created_at_clean:
                if not trace_created_at_clean.endswith('Z'):
                    trace_created_at_clean += '+00:00'
            
            trace_dt = datetime.fromisoformat(trace_created_at_clean)
        else:
            # Already a datetime object
            trace_dt = trace_created_at
        
        # Ensure timezone awareness (convert naive to UTC)
        if trace_dt.tzinfo is None:
            trace_dt = trace_dt.replace(tzinfo=timezone.utc)
        
        # Validate against date range
        if start_time:
            # Ensure start_time is timezone-aware for comparison
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if trace_dt < start_time:
                logger.debug(f"[DATE_DEBUG] Trace before start_time: {trace_dt} < {start_time}")
                return trace_dt, False
        
        if end_time:
            # Ensure end_time is timezone-aware for comparison
            if end_time.tzinfo is None:
                end_time = end_time.replace(tzinfo=timezone.utc)
            if trace_dt > end_time:
                logger.debug(f"[DATE_DEBUG] Trace after end_time: {trace_dt} > {end_time}")
                return trace_dt, False
        
        return trace_dt, True
    
    except Exception as e:
        logger.warning(f"Error parsing trace date: {e}, value: {trace_created_at}")
        return None, False


def get_trace_email(trace: Dict[str, Any]) -> Optional[str]:
    """
    Safely extract and validate email from trace metadata.
    
    Args:
        trace: Trace dictionary from Langfuse API
    
    Returns:
        Normalized email string or None
    """
    try:
        metadata = trace.get("metadata", {})
        user_email = metadata.get("user_email") or metadata.get("user_id")
        
        if not user_email:
            user_email = trace.get("userId") if isinstance(trace, dict) else None
        if not user_email:
            return None
        
        # Handle list values (convert to string)
        if isinstance(user_email, list):
            user_email = user_email[0] if user_email else None
        
        if not user_email:
            return None
        
        user_email_str = str(user_email).strip().lower()
        
        # Basic email validation
        if "@" not in user_email_str or len(user_email_str) < 5:
            return None
        
        return user_email_str
    
    except Exception as e:
        logger.warning(f"Error extracting email from trace: {e}")
        return None


def is_evaluation_trace(metadata: Dict[str, Any]) -> bool:
    """Return True for evaluation/job traces that should be excluded."""
    if not isinstance(metadata, dict):
        return False
    return any(
        metadata.get(key)
        for key in ("job_execution_id", "score_id", "target_trace_id", "previous_trace_id")
    )


def assign_trace_to_team(
    trace: Dict[str, Any],
    email_to_team_map: Dict[str, str],
    get_team_by_email_func,
    stats: TraceFilteringStats,
    user_email_override: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Assign a trace to a team using consistent logic.
    
    Args:
        trace: Trace dictionary from Langfuse API
        email_to_team_map: Fast lookup dict of email -> team
        get_team_by_email_func: Fallback function to get team by email
        stats: Statistics tracker
    
    Returns:
        Tuple of (team_name, user_email) or (None, email) if unassigned
    """
    user_email = user_email_override or get_trace_email(trace)
    
    if not user_email:
        stats.traces_without_email += 1
        return None, None
    
    try:
        # Try fast lookup first
        team_name = email_to_team_map.get(user_email)
        
        # Fallback to function lookup if not in cache
        if not team_name:
            team_name = get_team_by_email_func(user_email)
        
        if team_name and team_name != "Unassigned":
            return team_name, user_email
        else:
            stats.traces_unassigned += 1
            stats.unassigned_emails.add(user_email)
            return None, user_email
    
    except Exception as e:
        logger.warning(f"Error assigning trace to team for {user_email}: {e}")
        stats.invalid_emails.add(user_email)
        return None, user_email


def process_trace_batch(
    traces: List[Dict[str, Any]],
    email_to_team_map: Dict[str, str],
    get_team_by_email_func,
    teams_data: Dict[str, Dict],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    stats: Optional[TraceFilteringStats] = None,
    trace_id_to_email: Optional[Dict[str, str]] = None
) -> int:
    """
    Process a batch of traces and assign to teams.
    
    Args:
        traces: List of trace dictionaries from Langfuse API
        email_to_team_map: Fast lookup dict of email -> team
        get_team_by_email_func: Fallback function to get team by email
        teams_data: Dictionary to accumulate team data
        start_time: Optional start of date range
        end_time: Optional end of date range
        stats: Statistics tracker (created if not provided)
    
    Returns:
        Number of traces successfully filtered and added
    """
    if stats is None:
        stats = TraceFilteringStats()
    if trace_id_to_email is None:
        trace_id_to_email = {}
    
    traces_added = 0
    sales_teams = {"Sales [SMB]", "Sales [ENT]", "Sales [AM]"}  # For diagnostics
    
    for idx, trace in enumerate(traces):
        stats.total_fetched += 1
        
        try:
            trace_id = trace.get("id") if isinstance(trace, dict) else None
            metadata = trace.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            trace_keys = trace.keys() if isinstance(trace, dict) else []
            if is_evaluation_trace(metadata):
                continue

            # Get email early for logging (user traces only)
            user_email = get_trace_email(trace)

            # Cache known email for trace id
            if user_email and trace_id:
                trace_id_to_email[trace_id] = user_email

            if user_email:
                stats.traces_with_email += 1
                stats.metadata_keys_with_email.update(metadata.keys())
                stats.trace_keys_with_email.update(trace_keys)
                stats.record_trace_sample(trace, metadata, has_email=True)
            else:
                stats.metadata_keys_missing_email.update(metadata.keys())
                stats.trace_keys_missing_email.update(trace_keys)
                stats.record_trace_sample(trace, metadata, has_email=False)
            is_sales_user = False
            
            # Validate trace date
            trace_created_at = trace.get("createdAt")
            trace_dt, within_range = validate_and_parse_trace_date(
                trace_created_at, start_time, end_time
            )
            
            if trace_created_at and not trace_dt:
                # Parsing failed
                stats.traces_without_date += 1
                continue
            
            if not within_range:
                # Outside date range
                if trace_dt is None:
                    stats.traces_without_date += 1
                else:
                    stats.traces_out_of_date_range += 1
                    # Log if this is a Sales team member trace
                    if user_email:
                        team = get_team_by_email_func(user_email) if user_email else None
                        if team in sales_teams:
                            logger.debug(f"[SALES_DEBUG] Trace OUT OF RANGE for {user_email} (team: {team}): trace_dt={trace_dt}, start_time={start_time}, end_time={end_time}")
                            is_sales_user = True
                continue
            
            # Get trace question - HANDLE BOTH STRING AND LIST formats
            question_raw = trace.get("input", "")
            
            # Handle list format (some traces have input as list)
            if isinstance(question_raw, list):
                question = " ".join(str(q).strip() for q in question_raw if q)
                if not question and question_raw:
                    logger.debug(f"Trace has empty list input: {question_raw}")
            else:
                question = str(question_raw).strip() if question_raw else ""
            
            if not question:
                continue
            
            # Assign trace to team
            team_name, extracted_email = assign_trace_to_team(
                trace,
                email_to_team_map,
                get_team_by_email_func,
                stats,
                user_email_override=user_email,
            )
            
            if not team_name:
                # Log Sales team members that couldn't be assigned
                if extracted_email and team_name is None:
                    team = get_team_by_email_func(extracted_email) if extracted_email else None
                    if team in sales_teams:
                        logger.debug(f"[SALES_DEBUG] Trace NOT ASSIGNED for {extracted_email} (assigned_to: {team})")
                continue
            
            # Add to team data
            if team_name in teams_data:
                teams_data[team_name]["active_members"].add(extracted_email)
                teams_data[team_name]["total_questions"] += 1
                teams_data[team_name]["questions_list"].append(question)
                
                if team_name not in stats.assigned_per_team:
                    stats.assigned_per_team[team_name] = 0
                stats.assigned_per_team[team_name] += 1
                
                traces_added += 1
                stats.traces_filtered += 1
                
                # Log Sales team traces
                if team_name in sales_teams:
                    logger.info(f"[SALES_DEBUG] ✅ Added trace for {extracted_email} to {team_name}")
        
        except Exception as e:
            logger.warning(f"Error processing trace: {e}")
            continue
    
    return traces_added


def calculate_question_metrics(questions_list: List[str]) -> Dict[str, Any]:
    """
    Calculate metrics for a list of questions.
    
    Args:
        questions_list: List of question strings
    
    Returns:
        Dictionary with unique_count and top_questions
    """
    if not questions_list:
        return {"unique_count": 0, "top_questions": []}
    
    unique_count = len(set(questions_list))
    question_counter = Counter(questions_list)
    top_questions = [
        {"question": q, "count": c} for q, c in question_counter.most_common(5)
    ]
    
    return {
        "unique_count": unique_count,
        "top_questions": top_questions
    }


def save_traces_to_json(
    traces: List[Dict[str, Any]],
    time_filter: str = "unknown",
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    endpoint_name: str = "unknown"
) -> str:
    """
    Save traces to a JSON file with timestamp in filename.
    Files are saved in a dedicated 'langfuse_traces_backup' folder.
    
    Args:
        traces: List of trace dictionaries to save
        time_filter: The time filter used (today, yesterday, etc.)
        start_time: Optional start time of the query
        end_time: Optional end time of the query
        endpoint_name: Name of the endpoint that fetched these traces
    
    Returns:
        Path to the saved JSON file, or empty string if error
    """
    try:
        # Create dedicated traces backup directory if it doesn't exist
        traces_dir = Path("langfuse_traces_backup")
        traces_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        filename = f"traces_{time_filter}_{timestamp_str}.json"
        filepath = traces_dir / filename
        
        # Prepare metadata
        metadata = {
            "fetch_timestamp": now.isoformat(),
            "time_filter": time_filter,
            "endpoint_name": endpoint_name,
            "total_traces": len(traces),
            "date_range": {
                "start_time": start_time.isoformat() if start_time else None,
                "end_time": end_time.isoformat() if end_time else None
            }
        }
        
        # Prepare data structure
        data = {
            "metadata": metadata,
            "traces": traces
        }
        
        # Save to JSON file
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        
        print(f"[TRACE_SAVE] Saved {len(traces)} traces to {filepath}")
        logger.info(f"Saved {len(traces)} traces to {filepath}")
        
        return str(filepath)
    
    except Exception as e:
        error_msg = f"Error saving traces to JSON: {e}"
        print(f"[ERROR] {error_msg}")
        logger.error(error_msg, exc_info=True)
        return ""

