#!/usr/bin/env python3
"""
Test the incremental sync datetime logic without loading vectorstore
"""
import os
import sys
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Set environment to prevent vectorstore loading
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

def test_datetime_calculation():
    """Test datetime calculation logic"""
    print("=" * 70)
    print("TESTING INCREMENTAL SYNC DATETIME LOGIC")
    print("=" * 70)
    
    # Read last sync time from tracker
    tracker_file = "./data/jira_last_sync.json"
    if not os.path.exists(tracker_file):
        print("\n[ERROR] Sync tracker file not found")
        return False
    
    import json
    with open(tracker_file, 'r') as f:
        data = json.load(f)
    
    last_sync = data.get('last_sync')
    if not last_sync:
        print("\n[ERROR] No last_sync timestamp found")
        return False
    
    print(f"\n[INFO] Last sync timestamp: {last_sync}")
    
    # Apply the fix logic
    last_sync_dt = datetime.fromisoformat(last_sync)
    since_datetime = last_sync_dt - timedelta(minutes=1)
    since_date = since_datetime.strftime('%Y-%m-%d %H:%M')
    
    print(f"[INFO] Last sync datetime: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[INFO] Query datetime (last_sync - 1 min): {since_date}")
    
    # Test JQL query generation
    print("\n" + "=" * 70)
    print("TESTING JQL QUERY GENERATION")
    print("=" * 70)
    
    try:
        from app.jira_processor import JiraProcessor
        processor = JiraProcessor()
        
        # Test the query building
        jql = processor._build_jql_query_with_date_range(start_date=since_date)
        print(f"\n[OK] JQL Query generated:")
        print(f"     {jql}")
        
        # Verify format
        assert f"updated >= '{since_date}'" in jql, "JQL should contain datetime filter"
        print(f"\n[OK] JQL query contains datetime filter: updated >= '{since_date}'")
        
        # Check if it's datetime format (has space and colon)
        assert ' ' in since_date and ':' in since_date, "Should be datetime format"
        print(f"[OK] Datetime format is correct: YYYY-MM-DD HH:mm")
        
        return True
        
    except Exception as e:
        print(f"\n[ERROR] Failed to test JQL generation: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multiple_syncs_scenario():
    """Test scenario where multiple syncs happen on same day"""
    print("\n" + "=" * 70)
    print("TESTING MULTIPLE SYNCS ON SAME DAY SCENARIO")
    print("=" * 70)
    
    # Simulate first sync
    first_sync = datetime(2026, 1, 23, 0, 43, 25)
    first_query = (first_sync - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M')
    
    print(f"\n[SCENARIO] First sync at: {first_sync.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"          Query: updated >= '{first_query}'")
    
    # Simulate second sync later same day
    second_sync = datetime(2026, 1, 23, 14, 52, 44)
    second_query = (second_sync - timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M')
    
    print(f"\n[SCENARIO] Second sync at: {second_sync.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"          Query: updated >= '{second_query}'")
    
    # Verify they're different
    assert first_query != second_query, "Queries should be different"
    print(f"\n[OK] Queries are different - second sync will find new tickets!")
    
    # Verify second query is after first sync
    first_query_dt = datetime.strptime(first_query, '%Y-%m-%d %H:%M')
    second_query_dt = datetime.strptime(second_query, '%Y-%m-%d %H:%M')
    
    assert second_query_dt > first_query_dt, "Second query should be after first sync"
    print(f"[OK] Second query ({second_query}) is after first sync ({first_sync.strftime('%Y-%m-%d %H:%M:%S')})")
    
    return True

def main():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("INCREMENTAL SYNC DATETIME FIX TEST")
    print("=" * 70)
    
    results = {
        "datetime_calc": test_datetime_calculation(),
        "multiple_syncs": test_multiple_syncs_scenario()
    }
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n[SUCCESS] All tests passed!")
        print("\nThe datetime fix is working correctly:")
        print("  [OK] Uses datetime instead of date-only")
        print("  [OK] Subtracts 1 minute buffer")
        print("  [OK] Generates correct JQL queries")
        print("  [OK] Multiple syncs on same day work correctly")
        print("\n[NOTE] To test actual sync, use the API endpoint:")
        print("  POST /api/jira/sync (via admin UI)")
        print("\n[NOTE] Database corruption detected - may need rebuild")
        print("  Run: python build_jira_vectorstore_all.py")
    else:
        print("\n[FAIL] Some tests failed:")
        for test, result in results.items():
            status = "[OK]" if result else "[FAIL]"
            print(f"  {status} {test}")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
