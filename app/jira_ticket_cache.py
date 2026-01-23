# -*- coding: utf-8 -*-
"""
Jira Ticket Caching Module

Saves and loads fetched Jira tickets to avoid re-fetching on retry.
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime


CACHE_FILE = "./data/jira_tickets_cache.json"


def ensure_data_dir():
    """Ensure data directory exists."""
    Path("./data").mkdir(parents=True, exist_ok=True)


def save_tickets_to_cache(tickets: List[Dict[str, Any]], metadata: Optional[Dict[str, Any]] = None):
    """
    Save fetched tickets to cache file.
    
    Args:
        tickets: List of ticket data dictionaries
        metadata: Optional metadata (fetch time, count, etc.)
    """
    ensure_data_dir()
    
    cache_data = {
        "metadata": metadata or {
            "fetch_time": datetime.now().isoformat(),
            "ticket_count": len(tickets)
        },
        "tickets": tickets
    }
    
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)
        
        print(f"[CACHE] ✅ Saved {len(tickets)} tickets to cache: {CACHE_FILE}")
        return True
    except Exception as e:
        print(f"[CACHE] ⚠️  Failed to save cache: {e}")
        return False


def load_tickets_from_cache() -> Optional[List[Dict[str, Any]]]:
    """
    Load tickets from cache file.
    
    Returns:
        List of ticket dictionaries or None if cache doesn't exist/is invalid
    """
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        tickets = cache_data.get('tickets', [])
        metadata = cache_data.get('metadata', {})
        
        if tickets:
            fetch_time = metadata.get('fetch_time', 'unknown')
            ticket_count = metadata.get('ticket_count', len(tickets))
            
            print(f"[CACHE] ✅ Loaded {ticket_count} tickets from cache")
            print(f"[CACHE] Cache created: {fetch_time}")
            return tickets
        else:
            print(f"[CACHE] ⚠️  Cache file exists but contains no tickets")
            return None
            
    except Exception as e:
        print(f"[CACHE] ⚠️  Failed to load cache: {e}")
        return None


def clear_cache():
    """Delete the cache file."""
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            print(f"[CACHE] ✅ Deleted cache file: {CACHE_FILE}")
            return True
        except Exception as e:
            print(f"[CACHE] ⚠️  Failed to delete cache: {e}")
            return False
    else:
        print(f"[CACHE] ℹ️  No cache file to delete")
        return True


def get_cache_info() -> Optional[Dict[str, Any]]:
    """
    Get information about cached tickets without loading them.
    
    Returns:
        Dictionary with cache metadata or None if cache doesn't exist
    """
    if not os.path.exists(CACHE_FILE):
        return None
    
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
        
        metadata = cache_data.get('metadata', {})
        ticket_count = len(cache_data.get('tickets', []))
        
        # Add file info
        file_stat = os.stat(CACHE_FILE)
        metadata['file_size_mb'] = round(file_stat.st_size / (1024 * 1024), 2)
        metadata['ticket_count'] = ticket_count
        
        return metadata
        
    except Exception as e:
        print(f"[CACHE] ⚠️  Failed to get cache info: {e}")
        return None
