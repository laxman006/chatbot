# -*- coding: utf-8 -*-
"""
Test script for Jira incremental sync fix.

This script tests:
1. Pre-sync state (document count, ticket keys)
2. Sync execution with detailed logging
3. Post-sync verification (document count, new documents)
4. Duplicate detection
5. Updated ticket handling
"""
import os
import sys
from datetime import datetime
from collections import defaultdict, Counter

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app.jira_vectorstore import (
    load_jira_vectorstore,
    add_jira_tickets_incrementally
)
from app.jira_sync_tracker import (
    get_sync_stats,
    get_last_sync_time
)
from app.jira_processor import JiraProcessor


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print a formatted header."""
    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}{text}{Colors.RESET}")
    print("=" * 80)


def print_success(text):
    """Print success message."""
    print(f"{Colors.GREEN}✅ {text}{Colors.RESET}")


def print_warning(text):
    """Print warning message."""
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.RESET}")


def print_error(text):
    """Print error message."""
    print(f"{Colors.RED}❌ {text}{Colors.RESET}")


def print_info(text):
    """Print info message."""
    print(f"{Colors.BLUE}ℹ️  {text}{Colors.RESET}")


def get_vectorstore_stats(vectorstore):
    """Get detailed statistics from vectorstore."""
    if not vectorstore:
        return None
    
    try:
        all_docs = vectorstore.get(include=["metadatas", "ids"])
        
        if not all_docs or 'metadatas' not in all_docs:
            return None
        
        stats = {
            'total_docs': len(all_docs.get('ids', [])),
            'ticket_keys': set(),
            'by_section': Counter(),
            'by_project': Counter(),
            'document_ids': set(),
            'tickets_by_key': defaultdict(list)
        }
        
        metadatas = all_docs.get('metadatas', [])
        ids = all_docs.get('ids', [])
        
        for idx, metadata in enumerate(metadatas):
            if not metadata:
                continue
            
            ticket_key = metadata.get('ticket_key')
            section = metadata.get('section', 'unknown')
            project = metadata.get('project_key', 'unknown')
            doc_id = ids[idx] if idx < len(ids) else None
            
            if ticket_key:
                stats['ticket_keys'].add(ticket_key)
                stats['tickets_by_key'][ticket_key].append({
                    'section': section,
                    'doc_id': doc_id,
                    'project': project
                })
            
            stats['by_section'][section] += 1
            stats['by_project'][project] += 1
            
            if doc_id:
                stats['document_ids'].add(doc_id)
        
        return stats
        
    except Exception as e:
        print_error(f"Error getting vectorstore stats: {e}")
        import traceback
        traceback.print_exc()
        return None


def test_pre_sync_state():
    """Test 1: Check pre-sync state."""
    print_header("TEST 1: Pre-Sync State Check")
    
    # Check sync tracker
    print_info("Checking sync tracker...")
    sync_stats = get_sync_stats()
    last_sync = get_last_sync_time()
    
    if sync_stats:
        print(f"   Last sync: {sync_stats.get('last_sync_readable', 'Never')}")
        print(f"   Last status: {sync_stats.get('last_status', 'Unknown')}")
        print(f"   Sync history entries: {len(sync_stats.get('sync_history', []))}")
        print(f"   Consecutive failures: {sync_stats.get('consecutive_failures', 0)}")
    else:
        print_warning("No sync tracker found - this might be the first sync")
    
    if last_sync:
        last_sync_dt = datetime.fromisoformat(last_sync)
        print(f"   Last sync timestamp: {last_sync_dt.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        print_warning("No previous sync found - incremental sync requires initial build")
        return False
    
    # Check vectorstore
    print_info("Loading vectorstore...")
    vectorstore = load_jira_vectorstore()
    
    if not vectorstore:
        print_error("Vectorstore not found! Run build_jira_vectorstore() first.")
        return False
    
    print_success("Vectorstore loaded successfully")
    
    # Get pre-sync stats
    print_info("Analyzing pre-sync state...")
    pre_stats = get_vectorstore_stats(vectorstore)
    
    if pre_stats:
        print(f"\n   Total documents: {pre_stats['total_docs']:,}")
        print(f"   Unique tickets: {len(pre_stats['ticket_keys']):,}")
        print(f"   Unique document IDs: {len(pre_stats['document_ids']):,}")
        print(f"\n   Documents by section:")
        for section, count in sorted(pre_stats['by_section'].items()):
            print(f"      {section}: {count:,}")
        print(f"\n   Documents by project:")
        for project, count in sorted(pre_stats['by_project'].items()):
            print(f"      {project}: {count:,}")
        
        # Check for duplicate document IDs
        if len(pre_stats['document_ids']) < pre_stats['total_docs']:
            duplicates = pre_stats['total_docs'] - len(pre_stats['document_ids'])
            print_warning(f"Found {duplicates} duplicate document IDs!")
        else:
            print_success("No duplicate document IDs found")
        
        return {
            'vectorstore': vectorstore,
            'pre_stats': pre_stats,
            'last_sync': last_sync
        }
    else:
        print_error("Could not get vectorstore statistics")
        return False


def test_sync_execution(pre_state):
    """Test 2: Execute sync and monitor progress."""
    print_header("TEST 2: Sync Execution")
    
    if not pre_state:
        print_error("Pre-sync state check failed - cannot proceed")
        return False
    
    pre_stats = pre_state['pre_stats']
    print(f"Pre-sync document count: {pre_stats['total_docs']:,}")
    print(f"Pre-sync unique tickets: {len(pre_stats['ticket_keys']):,}")
    
    print_info("Starting incremental sync...")
    print("   (This may take a few minutes depending on number of updates)")
    print()
    
    try:
        # Run sync
        result = add_jira_tickets_incrementally()
        
        if result:
            post_stats = get_vectorstore_stats(result)
            if post_stats:
                print_success("Sync completed successfully!")
                return {
                    'success': True,
                    'vectorstore': result,
                    'pre_stats': pre_stats,
                    'post_stats': post_stats
                }
            else:
                print_warning("Sync completed but could not get post-sync stats")
                return {
                    'success': True,
                    'vectorstore': result,
                    'pre_stats': pre_stats,
                    'post_stats': None
                }
        else:
            print_warning("Sync returned None - no updates found or sync failed")
            # Check sync stats to see what happened
            sync_stats = get_sync_stats()
            if sync_stats:
                last_status = sync_stats.get('last_status')
                if last_status == 'no_updates':
                    print_info("No new tickets found (this is normal if nothing changed)")
                elif last_status == 'failed':
                    print_error("Sync failed - check error logs")
                else:
                    print_info(f"Sync status: {last_status}")
            
            return {
                'success': False,
                'vectorstore': pre_state['vectorstore'],
                'pre_stats': pre_stats,
                'post_stats': pre_stats  # No change
            }
            
    except Exception as e:
        print_error(f"Sync execution failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_post_sync_verification(sync_result):
    """Test 3: Verify sync results."""
    print_header("TEST 3: Post-Sync Verification")
    
    if not sync_result or not sync_result.get('success'):
        print_warning("Sync did not complete successfully - skipping verification")
        return False
    
    pre_stats = sync_result['pre_stats']
    post_stats = sync_result['post_stats']
    
    if not post_stats:
        print_error("Could not get post-sync statistics")
        return False
    
    # Compare counts
    doc_diff = post_stats['total_docs'] - pre_stats['total_docs']
    ticket_diff = len(post_stats['ticket_keys']) - len(pre_stats['ticket_keys'])
    
    print(f"\n   Pre-sync documents:  {pre_stats['total_docs']:,}")
    print(f"   Post-sync documents: {post_stats['total_docs']:,}")
    print(f"   Difference:          {doc_diff:+,}")
    
    print(f"\n   Pre-sync tickets:    {len(pre_stats['ticket_keys']):,}")
    print(f"   Post-sync tickets:   {len(post_stats['ticket_keys']):,}")
    print(f"   Difference:          {ticket_diff:+,}")
    
    # Check sync tracker
    sync_stats = get_sync_stats()
    if sync_stats:
        last_entry = sync_stats.get('sync_history', [])[-1] if sync_stats.get('sync_history') else None
        if last_entry:
            reported_docs = last_entry.get('documents_added', 0)
            print(f"\n   Reported documents added: {reported_docs}")
            
            if reported_docs != doc_diff:
                print_warning(f"Document count mismatch! Reported {reported_docs} but actual difference is {doc_diff}")
            else:
                print_success("Document count matches sync tracker")
    
    # Check for new tickets
    new_tickets = post_stats['ticket_keys'] - pre_stats['ticket_keys']
    if new_tickets:
        print(f"\n   New tickets added: {len(new_tickets)}")
        print(f"   Sample new tickets: {', '.join(list(new_tickets)[:5])}")
    else:
        print_info("No new tickets (only updates to existing tickets)")
    
    # Check for duplicate IDs
    if len(post_stats['document_ids']) < post_stats['total_docs']:
        duplicates = post_stats['total_docs'] - len(post_stats['document_ids'])
        print_error(f"Found {duplicates} duplicate document IDs after sync!")
        return False
    else:
        print_success("No duplicate document IDs found")
    
    # Check section distribution
    print(f"\n   Documents by section (post-sync):")
    for section, count in sorted(post_stats['by_section'].items()):
        pre_count = pre_stats['by_section'].get(section, 0)
        diff = count - pre_count
        print(f"      {section}: {count:,} ({diff:+,})")
    
    return True


def test_updated_tickets_handling(sync_result):
    """Test 4: Verify updated tickets were handled correctly."""
    print_header("TEST 4: Updated Tickets Handling")
    
    if not sync_result or not sync_result.get('success'):
        print_warning("Sync did not complete - skipping updated tickets test")
        return False
    
    pre_stats = sync_result['pre_stats']
    post_stats = sync_result['post_stats']
    
    if not post_stats:
        print_error("Could not get post-sync statistics")
        return False
    
    # Find tickets that existed before and after
    common_tickets = pre_stats['ticket_keys'] & post_stats['ticket_keys']
    
    print(f"   Tickets in both pre and post sync: {len(common_tickets):,}")
    
    # Check if updated tickets have consistent IDs
    print_info("Checking document ID consistency for updated tickets...")
    
    issues_found = []
    for ticket_key in list(common_tickets)[:10]:  # Check first 10
        pre_docs = pre_stats['tickets_by_key'][ticket_key]
        post_docs = post_stats['tickets_by_key'][ticket_key]
        
        # Check if sections match
        pre_sections = {doc['section'] for doc in pre_docs}
        post_sections = {doc['section'] for doc in post_docs}
        
        if pre_sections != post_sections:
            print_warning(f"Ticket {ticket_key}: Section mismatch")
            print(f"   Pre: {sorted(pre_sections)}")
            print(f"   Post: {sorted(post_sections)}")
            issues_found.append(ticket_key)
    
    if not issues_found:
        print_success("Updated tickets have consistent structure")
    else:
        print_warning(f"Found {len(issues_found)} tickets with structural differences")
    
    return len(issues_found) == 0


def main():
    """Run all tests."""
    print_header("JIRA SYNC FIX TEST SUITE")
    print(f"Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = {
        'pre_sync': False,
        'sync_execution': False,
        'post_sync': False,
        'updated_tickets': False
    }
    
    # Test 1: Pre-sync state
    pre_state = test_pre_sync_state()
    if pre_state:
        results['pre_sync'] = True
    else:
        print_error("Pre-sync check failed - cannot continue")
        return
    
    # Test 2: Sync execution
    sync_result = test_sync_execution(pre_state)
    if sync_result:
        results['sync_execution'] = True
    else:
        print_error("Sync execution failed")
        return
    
    # Test 3: Post-sync verification
    if test_post_sync_verification(sync_result):
        results['post_sync'] = True
    
    # Test 4: Updated tickets handling
    if test_updated_tickets_handling(sync_result):
        results['updated_tickets'] = True
    
    # Final summary
    print_header("TEST SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    
    print(f"\n   Tests passed: {passed_tests}/{total_tests}")
    print(f"\n   Detailed results:")
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"      {test_name}: {status}")
    
    if passed_tests == total_tests:
        print_success("\n🎉 All tests passed! Sync fix is working correctly.")
    else:
        print_warning(f"\n⚠️  {total_tests - passed_tests} test(s) failed. Review the output above.")
    
    print(f"\nTest completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
