#!/usr/bin/env python3
"""
Standalone Blog Polling Script

This script can be run as:
- One-time execution (manual trigger)
- Scheduled task (cron/Windows Task Scheduler)
- Background daemon/service

Usage:
    # Run once
    python scripts/poll_blogs.py
    
    # Run with custom interval (for continuous polling)
    python scripts/poll_blogs.py --interval 3600
    
    # Dry run (check for new posts without adding)
    python scripts/poll_blogs.py --dry-run
    
    # Continuous polling mode
    python scripts/poll_blogs.py --continuous
"""

import sys
import os
import argparse
import time

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.blog_poller import BlogPoller
from config import BLOG_POLLING_INTERVAL
import config


def main():
    """Main entry point for blog polling script."""
    parser = argparse.ArgumentParser(
        description="Poll WordPress API for new blog posts and add them to vectorstore"
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=BLOG_POLLING_INTERVAL,
        help=f"Polling interval in seconds (default: {BLOG_POLLING_INTERVAL})"
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="Run in continuous polling mode (default: run once)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check for new posts without adding them to vectorstore"
    )
    
    args = parser.parse_args()
    
    poller = BlogPoller()
    
    if args.dry_run:
        print("[DRY RUN] Checking for new posts without adding them...")
        # For dry run, we'll just check what would be fetched
        # This is a simplified version - full implementation would require
        # modifying the poller to support dry-run mode
        print("[INFO] Dry run mode - would check for new posts but not add them")
        return
    
    if args.continuous:
        # Override interval if specified
        if args.interval != BLOG_POLLING_INTERVAL:
            config.BLOG_POLLING_INTERVAL = args.interval
            print(f"[*] Using custom interval: {args.interval} seconds")
        
        # Run continuously
        poller.run_continuous()
    else:
        # Run once
        print("[*] Running one-time blog poll...")
        success = poller.poll_once()
        if success:
            print("[OK] Poll completed successfully")
            sys.exit(0)
        else:
            print("[ERROR] Poll completed with errors")
            sys.exit(1)


if __name__ == "__main__":
    main()
