"""
Safe test for Jira automatic fetch - won't corrupt vectorstore.
Only performs read operations and simulations.
"""
import sys
import os
sys.path.insert(0, '.')

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Prevent rebuilding
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

from datetime import datetime
from app.jira_vectorstore import load_jira_vectorstore
from app.jira_sync_tracker import get_sync_stats
from app.jira_processor import JiraProcessor

def test_1_sync_tracking():
    """Test 1: Verify sync tracking works (READ-ONLY)."""
    print("\n" + "=" * 70)
    print("TEST 1: Sync Tracking (READ-ONLY)")
    print("=" * 70)
    
    try:
        stats = get_sync_stats()
        
        print(f"[OK] Last successful sync: {stats.get('last_sync_readable', 'Never')}")
        print(f"[OK] Last attempt: {stats.get('last_attempt_readable', 'Never')}")
        print(f"[OK] Last status: {stats.get('last_status', 'unknown')}")
        print(f"[OK] Consecutive failures: {stats.get('consecutive_failures', 0)}")
        
        history = stats.get('sync_history', [])
        print(f"[OK] Sync history entries: {len(history)}")
        
        if history:
            print("\n    Recent sync history:")
            for entry in history[-5:]:  # Last 5 entries
                print(f"      - {entry.get('readable')}: {entry.get('status')} ({entry.get('documents_added', 0)} docs)")
        
        if stats.get('last_sync'):
            print("\n[PASS] Sync tracking is working correctly")
            return True
        else:
            print("\n[WARN] No sync history found (need to run initial build)")
            return False
    except Exception as e:
        print(f"\n[FAIL] Error checking sync tracking: {e}")
        return False


def test_2_vectorstore_health():
    """Test 2: Check vectorstore health (READ-ONLY)."""
    print("\n" + "=" * 70)
    print("TEST 2: Vectorstore Health Check (READ-ONLY)")
    print("=" * 70)
    
    try:
        vectorstore = load_jira_vectorstore()
        
        if not vectorstore:
            print("[FAIL] Vectorstore not loaded")
            return False
        
        total_docs = vectorstore._collection.count()
        print(f"[OK] Vectorstore loaded successfully")
        print(f"[OK] Total document chunks: {total_docs}")
        
        # Sample a few documents to verify structure
        sample = vectorstore.get(limit=5, include=["metadatas"])
        
        if sample and 'metadatas' in sample:
            metadatas = sample['metadatas']
            print(f"[OK] Successfully retrieved {len(metadatas)} sample documents")
            
            # Check for required fields
            for i, meta in enumerate(metadatas[:3], 1):
                ticket_key = meta.get('ticket_key', 'N/A')
                section = meta.get('section', 'N/A')
                print(f"     Sample {i}: {ticket_key} ({section})")
        
        print(f"\n[PASS] Vectorstore is healthy with {total_docs} documents")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Error checking vectorstore: {e}")
        return False


def test_3_duplicate_check():
    """Test 3: Verify no duplicates exist (READ-ONLY)."""
    print("\n" + "=" * 70)
    print("TEST 3: Duplicate Prevention Check (READ-ONLY)")
    print("=" * 70)
    
    try:
        vectorstore = load_jira_vectorstore()
        
        if not vectorstore:
            print("[FAIL] Vectorstore not loaded")
            return False
        
        # Get all documents
        print("[*] Fetching all documents for duplicate check...")
        all_docs = vectorstore.get(include=["metadatas"])
        
        if not all_docs or 'metadatas' not in all_docs:
            print("[FAIL] Could not retrieve documents")
            return False
        
        metadatas = all_docs['metadatas']
        total_chunks = len(metadatas)
        
        # Count unique tickets by (ticket_key, section)
        ticket_sections = {}
        ticket_keys = set()
        
        for meta in metadatas:
            if meta:
                ticket_key = meta.get('ticket_key')
                section = meta.get('section', 'unknown')
                
                if ticket_key:
                    ticket_keys.add(ticket_key)
                    section_key = (ticket_key, section)
                    ticket_sections[section_key] = ticket_sections.get(section_key, 0) + 1
        
        # Find duplicates
        duplicates = {k: v for k, v in ticket_sections.items() if v > 1}
        
        print(f"[OK] Total document chunks: {total_chunks}")
        print(f"[OK] Unique ticket keys: {len(ticket_keys)}")
        print(f"[OK] Unique ticket sections: {len(ticket_sections)}")
        
        if duplicates:
            print(f"\n[WARN] Found {len(duplicates)} duplicate ticket sections:")
            for (ticket, section), count in list(duplicates.items())[:5]:
                print(f"     - {ticket} ({section}): {count} copies")
            print(f"\n[FAIL] Duplicates detected (expected 0)")
            return False
        else:
            print(f"\n[PASS] No duplicates found - all tickets are unique")
            return True
        
    except Exception as e:
        print(f"\n[FAIL] Error checking duplicates: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_4_fetch_simulation():
    """Test 4: Simulate fetching new tickets (NO DATABASE WRITE)."""
    print("\n" + "=" * 70)
    print("TEST 4: Fetch New Tickets Simulation (NO WRITE)")
    print("=" * 70)
    
    try:
        stats = get_sync_stats()
        last_sync = stats.get('last_sync')
        
        if not last_sync:
            print("[WARN] No last sync time - skipping fetch simulation")
            return False
        
        # Convert to YYYY-MM-DD
        last_sync_dt = datetime.fromisoformat(last_sync)
        since_date = last_sync_dt.strftime('%Y-%m-%d')
        
        print(f"[*] Last sync: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"[*] Simulating fetch for tickets updated since: {since_date}")
        
        processor = JiraProcessor()
        print("[*] Connecting to Jira...")
        new_tickets = processor.fetch_tickets_since(since_date, max_issues=100)
        
        if not new_tickets:
            print(f"\n[OK] No new tickets found since {since_date}")
            print("[PASS] Fetch mechanism works - vectorstore is up to date")
            return True
        
        print(f"[OK] Found {len(new_tickets)} tickets updated since last sync")
        
        # Check which are truly new vs updated
        vectorstore = load_jira_vectorstore()
        all_docs = vectorstore.get(include=["metadatas"])
        existing_keys = set()
        
        if all_docs and 'metadatas' in all_docs:
            for meta in all_docs['metadatas']:
                if meta and 'ticket_key' in meta:
                    existing_keys.add(meta['ticket_key'])
        
        new_keys = [t['key'] for t in new_tickets if t['key'] not in existing_keys]
        updated_keys = [t['key'] for t in new_tickets if t['key'] in existing_keys]
        
        print(f"\n[OK] Analysis:")
        print(f"     - New tickets (not in DB): {len(new_keys)}")
        print(f"     - Updated tickets (already in DB): {len(updated_keys)}")
        
        if new_keys:
            print(f"\n    New tickets to be added:")
            for key in new_keys[:5]:
                ticket = next(t for t in new_tickets if t['key'] == key)
                summary = ticket.get('fields', {}).get('summary', 'N/A')
                print(f"      - {key}: {summary[:60]}")
        
        if updated_keys:
            print(f"\n    Updated tickets to be refreshed:")
            for key in updated_keys[:5]:
                ticket = next(t for t in new_tickets if t['key'] == key)
                summary = ticket.get('fields', {}).get('summary', 'N/A')
                print(f"      - {key}: {summary[:60]}")
        
        print(f"\n[PASS] Fetch simulation successful")
        print(f"[INFO] Incremental sync would add/update {len(new_tickets)} tickets")
        return True
        
    except Exception as e:
        print(f"\n[FAIL] Error in fetch simulation: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all safe tests."""
    print("=" * 70)
    print("JIRA AUTOMATIC FETCH - SAFE TEST (READ-ONLY)")
    print("=" * 70)
    print(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("[SAFE] No database modifications will be made")
    print("=" * 70)
    
    results = []
    
    # Run all tests
    results.append(("Sync Tracking", test_1_sync_tracking()))
    results.append(("Vectorstore Health", test_2_vectorstore_health()))
    results.append(("Duplicate Prevention", test_3_duplicate_check()))
    results.append(("Fetch Simulation", test_4_fetch_simulation()))
    
    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status} {test_name}")
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    print(f"\nTotal: {passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n" + "=" * 70)
        print("[SUCCESS] ALL TESTS PASSED!")
        print("=" * 70)
        print("\n[INFO] Automatic fetch system is working correctly")
        print("[INFO] No database corruption detected")
        print("[INFO] System ready for production use")
    else:
        print(f"\n[WARNING] {total_count - passed_count} test(s) failed")
    
    print("\n" + "=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Test interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] Test suite failed: {e}")
        import traceback
        traceback.print_exc()
