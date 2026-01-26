# -*- coding: utf-8 -*-
"""Quick script to check if there are new Jira tickets since last sync"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from app.jira_processor import JiraProcessor
from app.jira_sync_tracker import get_last_sync_time

if __name__ == "__main__":
    print("=" * 70)
    print("CHECKING FOR NEW JIRA TICKETS")
    print("=" * 70)
    
    # Get last sync time
    last_sync = get_last_sync_time()
    
    if not last_sync:
        print("[ERROR] No previous sync found")
        sys.exit(1)
    
    print(f"\nLast sync: {last_sync}")
    
    # Convert to datetime format for query
    last_sync_dt = datetime.fromisoformat(last_sync)
    since_datetime = last_sync_dt - timedelta(minutes=1)
    since_date = since_datetime.strftime('%Y-%m-%d %H:%M')
    
    print(f"Checking for tickets updated since: {since_date}")
    print()
    
    # Fetch tickets
    processor = JiraProcessor()
    tickets = processor.fetch_tickets_since(since_date, max_issues=100)
    
    if not tickets:
        print("\n[OK] No new tickets found - everything is up to date!")
    else:
        print(f"\n[INFO] Found {len(tickets)} ticket(s) updated since last sync:")
        print()
        for i, ticket in enumerate(tickets[:10], 1):
            print(f"  {i}. {ticket['key']}: {ticket['summary'][:60]}")
            print(f"     Updated: {ticket.get('updated', 'N/A')}")
            print()
        
        if len(tickets) > 10:
            print(f"  ... and {len(tickets) - 10} more tickets")
        
        print(f"\n[TIP] Run a sync to add these tickets to the vectorstore")
