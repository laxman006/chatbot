# test_jira_diagnostic.py
"""
Diagnostic script to find out what tickets and statuses exist in your Jira.
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://cf2020.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "laxman.kadari@cloudfuze.com")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

def main():
    jira = JIRA(
        server=JIRA_SERVER,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
    )
    
    print("=" * 60)
    print("JIRA DIAGNOSTIC - Finding Available Tickets")
    print("=" * 60)
    
    # Test 1: Get ANY tickets with comments from CFITS project
    print("\n1. Testing: Tickets with comments from CFITS project...")
    try:
        issues = jira.search_issues("project = CFITS AND commentCount > 0 ORDER BY updated DESC", maxResults=5)
        print(f"   Found: {len(issues)} tickets with comments")
        if issues:
            for issue in issues:
                print(f"   - {issue.key}: {issue.fields.summary[:50]}... Status: {issue.fields.status}")
        else:
            print("   [WARN] No tickets with comments found")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 2: Get tickets from a specific project (Jira requires project filter)
    print("\n2. Testing: Recent tickets from CFITS project (any status)...")
    try:
        issues = jira.search_issues("project = CFITS ORDER BY updated DESC", maxResults=10)
        print(f"   Found: {len(issues)} recent tickets")
        
        # Check statuses
        statuses = set()
        for issue in issues:
            statuses.add(str(issue.fields.status))
            has_comments = hasattr(issue.fields, 'comment') and issue.fields.comment and len(issue.fields.comment.comments) > 0
            comment_count = len(issue.fields.comment.comments) if has_comments else 0
            print(f"   - {issue.key}: Status = '{issue.fields.status}' | Comments: {comment_count}")
        
        print(f"\n   Unique statuses found: {sorted(statuses)}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 3: Try different status names
    print("\n3. Testing common status names...")
    common_statuses = ["Resolved", "Done", "Closed", "Fixed", "Completed"]
    
    for status in common_statuses:
        try:
            issues = jira.search_issues(f"project = CFITS AND status = '{status}' AND commentCount > 0 ORDER BY updated DESC", maxResults=3)
            if issues:
                print(f"   [OK] '{status}': Found {len(issues)} tickets with comments")
            else:
                print(f"   [NO] '{status}': No tickets found")
        except Exception as e:
            print(f"   [ERR] '{status}': Error - {e}")
    
    # Test 4: Check a specific project
    print("\n4. Testing specific project (CFITS)...")
    try:
        issues = jira.search_issues("project = CFITS AND commentCount > 0 ORDER BY updated DESC", maxResults=5)
        print(f"   Found: {len(issues)} tickets in CFITS with comments")
        for issue in issues:
            print(f"   - {issue.key}: {issue.fields.summary[:50]}... Status: {issue.fields.status}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # Test 5: Check tickets with resolution
    print("\n5. Testing: Tickets with resolution (resolved field)...")
    try:
        issues = jira.search_issues("resolution IS NOT EMPTY AND commentCount > 0 ORDER BY updated DESC", maxResults=5)
        print(f"   Found: {len(issues)} resolved tickets with comments")
        for issue in issues:
            print(f"   - {issue.key}: Status = '{issue.fields.status}' | Resolution: {issue.fields.resolution if hasattr(issue.fields, 'resolution') else 'N/A'}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)

if __name__ == "__main__":
    main()
