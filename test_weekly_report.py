#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for weekly team leaderboard report generation.

This script directly calls the report generation function to test
the weekly report automation without needing HTTP authentication.
"""

import asyncio
import sys
import os
import logging

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

# Configure logging to see detailed output
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

from app.weekly_reports_scheduler import scheduled_weekly_reports

def main():
    """Run the weekly report generation test."""
    print("=" * 70)
    print("TESTING WEEKLY TEAM LEADERBOARD REPORT GENERATION")
    print("=" * 70)
    print()
    print("This will:")
    print("  1. Calculate last week's date range (Monday to Sunday)")
    print("  2. Fetch team statistics (with and without Neutara Labs exclusion)")
    print("  3. Generate HTML email templates")
    print("  4. Generate PDF reports with charts")
    print("  5. Send emails to all admin users")
    print()
    print("Recipients:")
    print("  - laxman.kadari@cloudfuze.com")
    print("  - chaitanya.malle@cloudfuze.com")
    print("  - nirosh.reddy@cloudfuze.com")
    print()
    print("-" * 70)
    print()
    
    try:
        # Run the report generation
        asyncio.run(scheduled_weekly_reports())
        
        print()
        print("=" * 70)
        print("✅ REPORT GENERATION COMPLETED!")
        print("=" * 70)
        print()
        print("Next steps:")
        print("  1. Check the logs above for any errors")
        print("  2. Check your email inbox for the reports")
        print("  3. Verify PDF attachments are downloadable")
        print()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        print()
        print("=" * 70)
        print("❌ ERROR OCCURRED")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        print("Full traceback:")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
