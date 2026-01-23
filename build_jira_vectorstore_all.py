# -*- coding: utf-8 -*-
"""
Script to build Jira Vectorstore with recent resolved/closed tickets
This script fetches the 3000 most recent tickets from configured boards and builds a fresh vectorstore
"""

import os
import sys

# Add current directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment variables before importing config
os.environ['JIRA_MAX_ISSUES'] = '3000'  # Fetch 3000 most recent tickets
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'true'
os.environ['JIRA_DATE_FILTER'] = ''  # No date filter - get recent tickets (ordered by updated DESC)

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app.jira_vectorstore import build_jira_vectorstore
from datetime import datetime

if __name__ == "__main__":
    print("=" * 70)
    print("BUILDING JIRA VECTORSTORE WITH RECENT TICKETS")
    print("=" * 70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"JIRA_MAX_ISSUES: {os.getenv('JIRA_MAX_ISSUES', '3000')}")
    print(f"JIRA_DATE_FILTER: (empty - most recent tickets)")
    print()
    print("💡 TIP: Tickets are cached after fetching.")
    print("   - Re-run this script to retry from cache (instant!)")
    print("   - Delete ./data/jira_tickets_cache.json to force re-fetch")
    print("=" * 70)
    print()
    
    # Check for --no-cache flag to force re-fetch
    use_cache = "--no-cache" not in sys.argv
    
    try:
        vectorstore = build_jira_vectorstore(use_cache=use_cache)
        
        if vectorstore:
            total_docs = vectorstore._collection.count()
            print("\n" + "=" * 70)
            print("✅ JIRA VECTORSTORE BUILT SUCCESSFULLY!")
            print("=" * 70)
            print(f"Total documents in vectorstore: {total_docs}")
            print(f"Vectorstore path: ./data/jira_chroma_db")
            print("=" * 70)
            
            # Create sync tracker with initial timestamp
            try:
                from app.jira_sync_tracker import update_last_sync_time
                update_last_sync_time()
                print("[OK] Initial sync timestamp recorded")
            except ImportError:
                print("[INFO] Sync tracker not yet created - will be added in next phase")
            
        else:
            print("\n" + "=" * 70)
            print("❌ FAILED TO BUILD JIRA VECTORSTORE")
            print("=" * 70)
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
