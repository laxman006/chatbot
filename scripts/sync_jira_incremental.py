# -*- coding: utf-8 -*-
"""
Incremental Jira sync - Add only new/updated tickets
"""
import os
import sys

# Add parent directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app.jira_vectorstore import add_jira_tickets_incrementally
from app.jira_sync_tracker import get_sync_stats

if __name__ == "__main__":
    print("=" * 70)
    print("INCREMENTAL JIRA SYNC")
    print("=" * 70)
    
    # Show sync stats
    stats = get_sync_stats()
    if stats:
        print(f"Last Sync: {stats.get('last_sync_readable', 'Never')}")
        print(f"Sync History: {len(stats.get('sync_history', []))} previous syncs")
    else:
        print("No previous sync found")
    
    print("=" * 70)
    print()
    
    try:
        result = add_jira_tickets_incrementally()
        
        if result:
            total_docs = result._collection.count()
            print("\n" + "=" * 70)
            print("✅ INCREMENTAL SYNC COMPLETED!")
            print("=" * 70)
            print(f"Total documents in vectorstore: {total_docs}")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("⚠️ NO UPDATES NEEDED")
            print("=" * 70)
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
