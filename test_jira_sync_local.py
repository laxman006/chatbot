# -*- coding: utf-8 -*-
"""
Test Jira sync locally - Test the sync endpoints and functionality
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from app.jira_vectorstore import load_jira_vectorstore, add_jira_tickets_incrementally
from app.jira_sync_tracker import get_sync_stats, get_last_sync_time

def test_load_vectorstore():
    """Test loading the vectorstore."""
    print("=" * 70)
    print("TEST 1: Loading Jira Vectorstore")
    print("=" * 70)
    
    try:
        vectorstore = load_jira_vectorstore()
        if vectorstore:
            count = vectorstore._collection.count()
            print(f"[OK] Vectorstore loaded successfully")
            print(f"[OK] Document count: {count:,}")
            return True, vectorstore, count
        else:
            print("[ERROR] Vectorstore is None")
            return False, None, 0
    except Exception as e:
        print(f"[ERROR] Failed to load vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return False, None, 0

def test_sync_status():
    """Test getting sync status."""
    print("\n" + "=" * 70)
    print("TEST 2: Getting Sync Status")
    print("=" * 70)
    
    try:
        stats = get_sync_stats()
        last_sync = get_last_sync_time()
        
        if stats:
            print(f"[OK] Sync stats loaded")
            print(f"   Last sync: {stats.get('last_sync_readable', 'Never')}")
            print(f"   Last status: {stats.get('last_status', 'unknown')}")
            print(f"   Sync history entries: {len(stats.get('sync_history', []))}")
        else:
            print("[WARNING] No sync stats found")
        
        if last_sync:
            print(f"   Last sync timestamp: {last_sync}")
        else:
            print("[WARNING] No last sync timestamp")
        
        return True
    except Exception as e:
        print(f"[ERROR] Failed to get sync status: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_incremental_sync():
    """Test running incremental sync."""
    print("\n" + "=" * 70)
    print("TEST 3: Running Incremental Sync")
    print("=" * 70)
    
    try:
        # Get pre-sync count
        vectorstore = load_jira_vectorstore()
        if not vectorstore:
            print("[ERROR] Cannot test sync - vectorstore not loaded")
            return False
        
        pre_count = vectorstore._collection.count()
        print(f"[INFO] Pre-sync document count: {pre_count:,}")
        
        # Run sync
        print("\n[*] Starting incremental sync...")
        result = add_jira_tickets_incrementally()
        
        if result:
            post_count = result._collection.count()
            new_tickets = post_count - pre_count
            
            print(f"\n[OK] Sync completed successfully!")
            print(f"   Pre-sync count: {pre_count:,}")
            print(f"   Post-sync count: {post_count:,}")
            print(f"   New tickets added: {new_tickets:,}")
            
            # Get updated stats
            stats = get_sync_stats()
            print(f"   Last sync: {stats.get('last_sync_readable', 'Never')}")
            print(f"   Last status: {stats.get('last_status', 'unknown')}")
            
            return True
        else:
            print("\n[INFO] Sync returned None (no updates)")
            stats = get_sync_stats()
            print(f"   Last sync: {stats.get('last_sync_readable', 'Never')}")
            print(f"   Last status: {stats.get('last_status', 'unknown')}")
            return True  # This is still success - just no updates
            
    except Exception as e:
        print(f"\n[ERROR] Sync failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("JIRA SYNC LOCAL TEST SUITE")
    print("=" * 70)
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'vectorstore': False,
        'sync_status': False,
        'incremental_sync': False
    }
    
    # Test 1: Load vectorstore
    success, vectorstore, count = test_load_vectorstore()
    results['vectorstore'] = success
    
    if not success:
        print("\n[ERROR] Cannot continue - vectorstore failed to load")
        return
    
    # Test 2: Get sync status
    results['sync_status'] = test_sync_status()
    
    # Test 3: Run incremental sync
    results['incremental_sync'] = test_incremental_sync()
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    print(f"\n   Tests passed: {passed_tests}/{total_tests}")
    print(f"\n   Detailed results:")
    for test_name, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        print(f"      {test_name}: {status}")
    
    if passed_tests == total_tests:
        print("\n[SUCCESS] All tests passed!")
    else:
        print(f"\n[WARNING] {total_tests - passed_tests} test(s) failed")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[WARNING] Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
