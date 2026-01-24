# -*- coding: utf-8 -*-
"""
Test to verify what tickets are being fetched vs what's being added
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
from app.jira_vectorstore import get_last_sync_time
from app.jira_processor import JiraProcessor

def main():
    print("=" * 80)
    print("Verifying Sync Logic")
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
    print(f"Fetching tickets updated since: {since_date}")
    print()
    
    # Fetch tickets
    processor = JiraProcessor()
    tickets = processor.fetch_tickets_since(since_date, max_issues=100)
    
    print(f"\n[RESULT] Found {len(tickets)} tickets")
    
    if tickets:
        print("\nFirst 10 tickets:")
        for i, ticket in enumerate(tickets[:10], 1):
            key = ticket.get('key', 'N/A')
            updated = ticket.get('updated', 'N/A')
            summary = ticket.get('summary', 'N/A')[:60]
            print(f"  {i}. {key} - Updated: {updated}")
            print(f"     {summary}...")
    
    # Check if these tickets are in the vectorstore
    print("\n" + "=" * 80)
    print("Checking if tickets are already in vectorstore...")
    print("=" * 80)
    
    try:
        from app.jira_vectorstore import load_jira_vectorstore
        vectorstore = load_jira_vectorstore()
        
        if not vectorstore:
            print("[ERROR] Could not load vectorstore")
            return
        
        # Get existing ticket keys
        all_docs = vectorstore.get()
        existing_keys = set()
        if all_docs and 'metadatas' in all_docs:
            for metadata in all_docs['metadatas']:
                if metadata and 'ticket_key' in metadata:
                    existing_keys.add(metadata['ticket_key'])
        
        print(f"\n[INFO] Found {len(existing_keys)} tickets in vectorstore")
        
        # Check which fetched tickets are duplicates
        new_tickets = []
        duplicate_tickets = []
        
        for ticket in tickets:
            key = ticket.get('key', '')
            if key in existing_keys:
                duplicate_tickets.append(key)
            else:
                new_tickets.append(key)
        
        print(f"\n[RESULT]")
        print(f"  New tickets (not in DB): {len(new_tickets)}")
        print(f"  Duplicate tickets (already in DB): {len(duplicate_tickets)}")
        
        if new_tickets:
            print(f"\n  New ticket keys: {', '.join(new_tickets[:20])}")
            if len(new_tickets) > 20:
                print(f"  ... and {len(new_tickets) - 20} more")
        
        if duplicate_tickets:
            print(f"\n  Duplicate ticket keys (first 10): {', '.join(duplicate_tickets[:10])}")
            if len(duplicate_tickets) > 10:
                print(f"  ... and {len(duplicate_tickets) - 10} more")
        
    except Exception as e:
        print(f"[ERROR] Failed to check vectorstore: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
