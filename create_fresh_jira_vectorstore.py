# -*- coding: utf-8 -*-
"""
Create a fresh Jira vectorstore and sync all tickets
This script removes the old corrupted database BEFORE importing modules
"""

import os
import sys
import shutil
from datetime import datetime

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# IMPORTANT: Remove corrupted database BEFORE importing jira_vectorstore
# (because jira_vectorstore.py tries to load it at import time)
from config import JIRA_VECTORSTORE_PATH

def backup_and_remove_old_vectorstore():
    """Backup and remove the old corrupted vectorstore."""
    if os.path.exists(JIRA_VECTORSTORE_PATH):
        # Backup first
        backup_path = f"{JIRA_VECTORSTORE_PATH}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        print(f"[*] Backing up old vectorstore to: {backup_path}")
        try:
            shutil.copytree(JIRA_VECTORSTORE_PATH, backup_path)
            print(f"[OK] Backup created successfully")
        except Exception as e:
            print(f"[WARNING] Could not backup: {e}")
            backup_path = None
        
        # Remove old vectorstore
        print(f"[*] Removing old corrupted vectorstore at: {JIRA_VECTORSTORE_PATH}")
        try:
            shutil.rmtree(JIRA_VECTORSTORE_PATH)
            print(f"[OK] Old vectorstore removed")
            return backup_path
        except Exception as e:
            print(f"[ERROR] Failed to remove old vectorstore: {e}")
            return None
    else:
        print(f"[INFO] No existing vectorstore found - will create new one")
        return None

def main():
    print("=" * 80)
    print("CREATING FRESH JIRA VECTORSTORE")
    print("=" * 80)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Step 1: Remove corrupted database BEFORE importing modules
    print("Step 1: Removing corrupted database...")
    backup_path = backup_and_remove_old_vectorstore()
    if backup_path is None and os.path.exists(JIRA_VECTORSTORE_PATH):
        print("[ERROR] Cannot proceed - failed to remove old vectorstore")
        sys.exit(1)
    print()
    
    # Step 2: Now import modules (they won't try to load corrupted DB)
    print("Step 2: Importing modules...")
    from app.jira_vectorstore import build_jira_vectorstore
    from app.jira_sync_tracker import update_last_sync_time
    print("[OK] Modules imported")
    print()
    
    # Step 3: Build fresh vectorstore
    print("Step 3: Building fresh vectorstore...")
    print("-" * 80)
    
    # Set environment for fresh build
    os.environ['JIRA_MAX_ISSUES'] = '3000'  # Fetch 3000 most recent tickets
    os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'true'
    os.environ['JIRA_DATE_FILTER'] = ''  # No date filter - get recent tickets
    
    try:
        # Build vectorstore (use cache if available for faster rebuild)
        use_cache = "--no-cache" not in sys.argv
        if use_cache:
            print("[INFO] Using cached tickets if available (faster)")
            print("[INFO] Use --no-cache flag to force fresh fetch from Jira")
        else:
            print("[INFO] Fetching fresh tickets from Jira (no cache)")
        
        vectorstore = build_jira_vectorstore(use_cache=use_cache)
        
        if not vectorstore:
            print("\n[ERROR] Failed to build vectorstore")
            sys.exit(1)
        
        # Get document count
        total_docs = vectorstore._collection.count()
        print()
        print("-" * 80)
        print(f"[OK] Vectorstore built with {total_docs} documents")
        print()
        
        # Step 4: Update sync timestamp
        print("Step 4: Updating sync timestamp...")
        update_last_sync_time(status="success", documents_added=total_docs)
        print("[OK] Sync timestamp updated")
        print()
        
        # Success summary
        print("=" * 80)
        print("✅ FRESH JIRA VECTORSTORE CREATED SUCCESSFULLY!")
        print("=" * 80)
        print(f"Total documents: {total_docs}")
        print(f"Vectorstore path: {JIRA_VECTORSTORE_PATH}")
        if backup_path:
            print(f"Old vectorstore backed up to: {backup_path}")
        print()
        print("💡 Next steps:")
        print("   1. Test the vectorstore: python test_jira_chroma_db.py")
        print("   2. Try incremental sync: Trigger sync from admin dashboard")
        if backup_path:
            print(f"   3. If backup needed, restore from: {backup_path}")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Failed to build vectorstore: {e}")
        import traceback
        traceback.print_exc()
        
        # Restore backup if creation failed
        if backup_path and os.path.exists(backup_path):
            print(f"\n[INFO] Restoring backup from: {backup_path}")
            try:
                if os.path.exists(JIRA_VECTORSTORE_PATH):
                    shutil.rmtree(JIRA_VECTORSTORE_PATH)
                shutil.copytree(backup_path, JIRA_VECTORSTORE_PATH)
                print("[OK] Backup restored")
            except Exception as restore_error:
                print(f"[ERROR] Failed to restore backup: {restore_error}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()
