# -*- coding: utf-8 -*-
"""
Jira Sync Tracker - Track last sync time for incremental updates
"""
import json
import os
from datetime import datetime
from pathlib import Path

SYNC_TRACKER_FILE = "./data/jira_last_sync.json"

def ensure_data_dir():
    """Ensure data directory exists."""
    Path("./data").mkdir(parents=True, exist_ok=True)

def get_last_sync_time() -> str:
    """
    Get the last sync timestamp.
    
    Returns:
        str: ISO format timestamp or None if never synced
    """
    ensure_data_dir()
    if os.path.exists(SYNC_TRACKER_FILE):
        try:
            with open(SYNC_TRACKER_FILE, 'r') as f:
                data = json.load(f)
                return data.get('last_sync')
        except Exception as e:
            print(f"[WARNING] Could not read sync tracker: {e}")
            return None
    return None

def update_last_sync_time(timestamp: str = None, status: str = "success", documents_added: int = 0, error_message: str = None):
    """
    Update the last sync timestamp with status tracking.
    
    Args:
        timestamp: ISO format timestamp (defaults to now)
        status: Sync status ("success", "failed", "no_updates")
        documents_added: Number of documents added in this sync
        error_message: Error message if sync failed
    """
    ensure_data_dir()
    if timestamp is None:
        timestamp = datetime.now().isoformat()
    
    try:
        # Load existing data
        existing_data = {}
        if os.path.exists(SYNC_TRACKER_FILE):
            with open(SYNC_TRACKER_FILE, 'r') as f:
                existing_data = json.load(f)
        
        # Update with new sync time (only if successful)
        if status == "success":
            existing_data['last_sync'] = timestamp
            existing_data['last_sync_readable'] = datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        
        # Track last attempt regardless of success
        existing_data['last_attempt'] = timestamp
        existing_data['last_attempt_readable'] = datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M:%S')
        existing_data['last_status'] = status
        
        # Add sync history with detailed info
        if 'sync_history' not in existing_data:
            existing_data['sync_history'] = []
        
        history_entry = {
            'timestamp': timestamp,
            'readable': datetime.fromisoformat(timestamp).strftime('%Y-%m-%d %H:%M:%S'),
            'status': status,
            'documents_added': documents_added
        }
        
        if error_message:
            history_entry['error'] = error_message
        
        existing_data['sync_history'].append(history_entry)
        
        # Keep only last 20 sync records (increased for better monitoring)
        existing_data['sync_history'] = existing_data['sync_history'][-20:]
        
        # Track consecutive failures for alerting
        if status == "failed":
            existing_data['consecutive_failures'] = existing_data.get('consecutive_failures', 0) + 1
            existing_data['last_error'] = error_message
        else:
            existing_data['consecutive_failures'] = 0
            if 'last_error' in existing_data:
                del existing_data['last_error']
        
        # Write back
        with open(SYNC_TRACKER_FILE, 'w') as f:
            json.dump(existing_data, f, indent=2)
        
        if status == "success":
            print(f"[OK] Updated last sync time: {existing_data['last_sync_readable']}")
        elif status == "failed":
            print(f"[ERROR] Sync failed: {error_message}")
        else:
            print(f"[INFO] Sync status: {status}")
    except Exception as e:
        print(f"[ERROR] Could not update sync tracker: {e}")

def get_sync_stats() -> dict:
    """Get sync statistics."""
    ensure_data_dir()
    if os.path.exists(SYNC_TRACKER_FILE):
        try:
            with open(SYNC_TRACKER_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Could not read sync stats: {e}")
            return {}
    return {}

def has_sync_alerts() -> bool:
    """
    Check if there are any sync alerts (failures).
    
    Returns:
        bool: True if there are consecutive failures or recent errors
    """
    stats = get_sync_stats()
    consecutive_failures = stats.get('consecutive_failures', 0)
    return consecutive_failures >= 2  # Alert after 2 consecutive failures

def get_sync_alerts() -> list:
    """
    Get list of sync alerts/warnings.
    
    Returns:
        list: List of alert dictionaries
    """
    stats = get_sync_stats()
    alerts = []
    
    consecutive_failures = stats.get('consecutive_failures', 0)
    last_error = stats.get('last_error')
    last_attempt = stats.get('last_attempt_readable')
    
    if consecutive_failures >= 2:
        alerts.append({
            'type': 'error',
            'message': f'Jira sync has failed {consecutive_failures} times in a row',
            'details': last_error or 'Unknown error',
            'last_attempt': last_attempt
        })
    
    # Check if sync hasn't run in over 48 hours
    if stats.get('last_sync'):
        try:
            last_sync = datetime.fromisoformat(stats['last_sync'])
            hours_since = (datetime.now() - last_sync).total_seconds() / 3600
            if hours_since > 48:
                alerts.append({
                    'type': 'warning',
                    'message': f'No successful sync in {int(hours_since)} hours',
                    'details': f'Last successful sync: {stats.get("last_sync_readable")}',
                    'last_attempt': last_attempt
                })
        except:
            pass
    
    return alerts
