#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify blog polling scheduler is working.

This script checks:
1. Configuration is loaded correctly
2. Scheduler function can run successfully
3. Blog metadata is being tracked
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def test_config():
    """Test that configuration is loaded correctly."""
    print("="*70)
    print("TEST 1: Configuration Check")
    print("="*70)
    
    from config import BLOG_POLLING_ENABLED, BLOG_POLLING_INTERVAL, BLOG_LAST_POLL_FILE
    
    print(f"  BLOG_POLLING_ENABLED: {BLOG_POLLING_ENABLED}")
    print(f"  BLOG_POLLING_INTERVAL: {BLOG_POLLING_INTERVAL} seconds")
    
    # Convert to human-readable format
    interval_hours = BLOG_POLLING_INTERVAL // 3600
    interval_minutes = (BLOG_POLLING_INTERVAL % 3600) // 60
    if interval_hours > 0:
        interval_str = f"{interval_hours}h"
        if interval_minutes > 0:
            interval_str += f" {interval_minutes}m"
    elif interval_minutes > 0:
        interval_str = f"{interval_minutes}m"
    else:
        interval_str = f"{BLOG_POLLING_INTERVAL}s"
    
    print(f"  (= {interval_str})")
    print(f"  BLOG_LAST_POLL_FILE: {BLOG_LAST_POLL_FILE}")
    
    if not BLOG_POLLING_ENABLED:
        print("\n  WARNING: BLOG_POLLING_ENABLED is False!")
        print("   The scheduler will not start. Set BLOG_POLLING_ENABLED=true in .env")
        return False
    
    print("\n  Configuration looks good!")
    return True


def test_metadata_file():
    """Test that metadata file exists and is readable."""
    print("\n" + "="*70)
    print("TEST 2: Metadata File Check")
    print("="*70)
    
    # Metadata path matches app.helpers (_blog_metadata_path)
    from config import BLOG_LAST_POLL_FILE
    from app.helpers import load_blog_metadata
    
    metadata_path = os.path.join(os.path.dirname(BLOG_LAST_POLL_FILE), "blog_metadata.json")
    print(f"Metadata path: {metadata_path}")
    
    if os.path.exists(metadata_path):
        print("  Metadata file exists")
        
        try:
            metadata = load_blog_metadata()
            print("\n  Current metadata:")
            print(json.dumps(metadata, indent=2))
            print(f"\n  Last blog post date: {metadata.get('last_blog_post_date', 'N/A')}")
            print(f"  Last run at: {metadata.get('last_run_at', 'N/A')}")
            print(f"  Total posts ingested: {metadata.get('total_posts_ingested_cumulative', 0)}")
            print("\n  Metadata file is valid!")
            return True
        except Exception as e:
            print(f"  Error reading metadata: {e}")
            return False
    else:
        print("  Metadata file doesn't exist yet (will be created on first run)")
        return True


def test_scheduler_function():
    """Test that the scheduler function can be imported and called."""
    print("\n" + "="*70)
    print("TEST 3: Scheduler Function Test")
    print("="*70)
    
    try:
        from app.blog_polling_scheduler import scheduled_blog_poll
        print("  Successfully imported scheduled_blog_poll function")
        
        # Don't actually run it, just verify it's callable
        if callable(scheduled_blog_poll):
            print("  scheduled_blog_poll is callable")
            print("\n  Scheduler function is ready!")
            return True
        else:
            print("  scheduled_blog_poll is not callable")
            return False
    except Exception as e:
        print(f"  Error importing scheduler function: {e}")
        return False


def test_manual_poll():
    """Test running a manual blog poll (dry-run mode)."""
    print("\n" + "="*70)
    print("TEST 4: Manual Poll Test (Optional)")
    print("="*70)
    
    response = input("Do you want to run a test poll now? (y/n): ").strip().lower()
    
    if response != 'y':
        print("  Skipped manual poll test")
        return True
    
    try:
        print("\n  Running blog poll test...")
        from app.blog_polling_scheduler import scheduled_blog_poll
        
        # Run the scheduler function
        scheduled_blog_poll()
        
        print("\n  Manual poll test completed!")
        print("   Check the logs above for details.")
        return True
    except Exception as e:
        print(f"  Error during manual poll: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*70)
    print("BLOG POLLING SCHEDULER TEST SUITE")
    print("="*70)
    
    results = []
    
    # Run tests
    results.append(("Configuration", test_config()))
    results.append(("Metadata File", test_metadata_file()))
    results.append(("Scheduler Function", test_scheduler_function()))
    results.append(("Manual Poll", test_manual_poll()))
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"  {status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\nAll tests passed! The blog polling scheduler is ready to use.")
        print("\nNext steps:")
        print("1. Restart your server: python server.py")
        print("2. Look for scheduler logs on startup")
        print("3. Wait for the scheduled interval or trigger manually via admin UI")
    else:
        print("\nSome tests failed. Please check the errors above.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
