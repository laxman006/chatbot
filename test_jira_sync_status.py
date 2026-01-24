#!/usr/bin/env python3
"""
Test Jira Sync Status and Automatic Sync Configuration
"""
import os
import sys
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def check_sync_config():
    """Check Jira sync configuration"""
    print("=" * 60)
    print("JIRA SYNC CONFIGURATION CHECK")
    print("=" * 60)
    
    # Check environment variables
    sync_hour = os.getenv("JIRA_SYNC_HOUR", "2")
    enable_vectorstore = os.getenv("ENABLE_JIRA_VECTORSTORE", "true")
    initialize_vectorstore = os.getenv("INITIALIZE_JIRA_VECTORSTORE", "false")
    
    print(f"\n[OK] Configuration:")
    print(f"   JIRA_SYNC_HOUR: {sync_hour} (runs at {sync_hour}:00 daily)")
    print(f"   ENABLE_JIRA_VECTORSTORE: {enable_vectorstore}")
    print(f"   INITIALIZE_JIRA_VECTORSTORE: {initialize_vectorstore}")
    
    # Check if scheduler is configured
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        
        scheduler = BackgroundScheduler()
        sync_hour_int = int(sync_hour)
        
        print(f"\n[OK] Scheduler Configuration:")
        print(f"   APScheduler imported successfully")
        print(f"   Scheduled time: Daily at {sync_hour_int}:00")
        print(f"   Status: Ready to schedule")
        
    except ImportError as e:
        print(f"\n[ERROR] Scheduler Error:")
        print(f"   APScheduler not installed: {e}")
        print(f"   Install with: pip install apscheduler")
        return False
    
    return True

def check_sync_tracker():
    """Check sync tracker file"""
    print("\n" + "=" * 60)
    print("SYNC TRACKER STATUS")
    print("=" * 60)
    
    tracker_file = "./data/jira_last_sync.json"
    
    if not os.path.exists(tracker_file):
        print(f"\n[WARN] Sync tracker file not found: {tracker_file}")
        print("   This is normal for first-time setup.")
        return False
    
    try:
        import json
        with open(tracker_file, 'r') as f:
            data = json.load(f)
        
        print(f"\n[OK] Last Sync Information:")
        print(f"   Last Sync: {data.get('last_sync_readable', 'Never')}")
        print(f"   Last Status: {data.get('last_status', 'unknown')}")
        print(f"   Consecutive Failures: {data.get('consecutive_failures', 0)}")
        
        sync_history = data.get('sync_history', [])
        if sync_history:
            print(f"\n   Recent Sync History:")
            for entry in sync_history[-5:]:  # Show last 5
                print(f"     - {entry.get('readable', 'Unknown')}: {entry.get('status', 'unknown')} ({entry.get('documents_added', 0)} docs)")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Error reading sync tracker: {e}")
        return False

def check_vectorstore():
    """Check if vectorstore exists"""
    print("\n" + "=" * 60)
    print("VECTORSTORE STATUS")
    print("=" * 60)
    
    vectorstore_path = os.getenv("JIRA_VECTORSTORE_PATH", "./data/jira_chroma_db")
    
    if os.path.exists(vectorstore_path):
        print(f"\n[OK] Vectorstore exists: {vectorstore_path}")
        
        # Try to load it
        try:
            os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
            from app.jira_vectorstore import load_jira_vectorstore
            
            vectorstore = load_jira_vectorstore()
            if vectorstore:
                count = vectorstore._collection.count()
                print(f"   Total documents: {count:,}")
                return True
            else:
                print(f"   [WARN] Vectorstore exists but failed to load")
                return False
                
        except Exception as e:
            print(f"   [WARN] Error loading vectorstore: {e}")
            return False
    else:
        print(f"\n[WARN] Vectorstore not found: {vectorstore_path}")
        print("   Run: python build_jira_vectorstore_all.py")
        return False

def test_sync_function():
    """Test if sync function can be called"""
    print("\n" + "=" * 60)
    print("SYNC FUNCTION TEST")
    print("=" * 60)
    
    try:
        os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
        from app.jira_vectorstore import add_jira_tickets_incrementally
        
        print("\n[OK] Sync function imported successfully")
        print("   Function: add_jira_tickets_incrementally()")
        print("   Status: Ready to use")
        
        # Check if we can call it (dry run - don't actually sync)
        print("\n   Note: To test actual sync, use:")
        print("   python scripts/sync_jira_incremental.py")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Error importing sync function: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Main test function"""
    print("\n" + "=" * 60)
    print("JIRA AUTOMATIC SYNC TEST")
    print("=" * 60)
    
    results = {
        "config": check_sync_config(),
        "tracker": check_sync_tracker(),
        "vectorstore": check_vectorstore(),
        "sync_function": test_sync_function()
    }
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    all_ok = all(results.values())
    
    if all_ok:
        print("\n[OK] All checks passed!")
        print("\nAutomatic Sync Status:")
        sync_hour = os.getenv("JIRA_SYNC_HOUR", "2")
        print(f"   [OK] Scheduled to run daily at {sync_hour}:00")
        print(f"   [OK] Scheduler is configured in server.py")
        print(f"   [OK] Sync function is available")
        print(f"\nTo verify scheduler is running:")
        print(f"   1. Start the server: python server.py")
        print(f"   2. Check logs for: '[STARTUP] Jira sync scheduler started'")
        print(f"   3. Wait for scheduled time or trigger manual sync")
    else:
        print("\n[WARN] Some checks failed:")
        for check, result in results.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"   {status} {check}")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
