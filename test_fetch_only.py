# -*- coding: utf-8 -*-
"""
Simple test to check what tickets are being fetched (without loading vectorstore)
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
import json

def get_last_sync_time():
    """Get last sync time from JSON file."""
    sync_file = "data/jira_last_sync.json"
    try:
        with open(sync_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get('last_sync')
    except Exception as e:
        print(f"[ERROR] Could not read sync file: {e}")
        return None

def main():
    print("=" * 80)
    print("Checking What Tickets Would Be Fetched")
    print("=" * 80)
    print()
    
    # Get last sync time
    last_sync = get_last_sync_time()
    if not last_sync:
        print("[ERROR] No last sync time found")
        return
    
    last_sync_dt = datetime.fromisoformat(last_sync)
    since_datetime = last_sync_dt - timedelta(minutes=1)
    since_date = since_datetime.strftime('%Y-%m-%d %H:%M')
    
    print(f"Last sync: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Would fetch tickets updated since: {since_date}")
    print()
    
    # Fetch tickets (this doesn't require loading vectorstore)
    from app.jira_processor import JiraProcessor
    processor = JiraProcessor()
    tickets = processor.fetch_tickets_since(since_date, max_issues=100)
    
    print(f"\n[RESULT] Found {len(tickets)} tickets that would be synced")
    
    if tickets:
        print("\nFirst 20 tickets:")
        for i, ticket in enumerate(tickets[:20], 1):
            key = ticket.get('key', 'N/A')
            updated = ticket.get('updated', 'N/A')
            summary = ticket.get('summary', 'N/A')[:60]
            print(f"  {i}. {key} - Updated: {updated}")
            print(f"     {summary}...")
        
        if len(tickets) > 20:
            print(f"\n  ... and {len(tickets) - 20} more tickets")
        
        print(f"\n[SUMMARY]")
        print(f"  Total tickets fetched: {len(tickets)}")
        print(f"  These tickets SHOULD be added to the vectorstore")
        print(f"  If sync shows 0 documents added, there's a problem with:")
        print(f"    1. Duplicate filtering (tickets already in DB)")
        print(f"    2. ChromaDB corruption (can't add new documents)")
        print(f"    3. Document processing errors")
    else:
        print("\n[INFO] No tickets found - sync correctly shows 0 documents")

if __name__ == "__main__":
    main()
