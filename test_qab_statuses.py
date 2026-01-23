# -*- coding: utf-8 -*-
"""
Check actual status names in QAB board
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
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

if __name__ == "__main__":
    print("=" * 80)
    print("QAB BOARD STATUS DISCOVERY")
    print("=" * 80)
    
    try:
        # Connect to Jira
        print("\n[*] Connecting to Jira...")
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        print(f"[OK] Connected as: {jira.current_user()}")
        
        # Get all tickets from QAB (limit 50)
        print("\n[*] Fetching QAB tickets (all statuses)...")
        jql = "project = QAB ORDER BY updated DESC"
        issues = jira.search_issues(jql, maxResults=50)
        
        print(f"[OK] Found {len(issues)} tickets\n")
        
        # Collect all unique statuses
        statuses = {}
        for issue in issues:
            status = str(issue.fields.status)
            statuses[status] = statuses.get(status, 0) + 1
        
        print("=" * 80)
        print("STATUS DISTRIBUTION IN QAB BOARD")
        print("=" * 80)
        
        for status, count in sorted(statuses.items(), key=lambda x: x[1], reverse=True):
            print(f"  {status}: {count} tickets")
        
        # Show sample tickets for each status
        print("\n" + "=" * 80)
        print("SAMPLE TICKETS BY STATUS")
        print("=" * 80)
        
        for status in statuses.keys():
            print(f"\nStatus: {status}")
            jql_status = f"project = QAB AND status = '{status}' ORDER BY updated DESC"
            try:
                sample_issues = jira.search_issues(jql_status, maxResults=3)
                for issue in sample_issues:
                    print(f"  {issue.key}: {issue.fields.summary[:60]}...")
            except Exception as e:
                print(f"  Error fetching samples: {e}")
        
        # Try the "Resloved-" status specifically
        print("\n" + "=" * 80)
        print("TESTING 'Resloved-' STATUS")
        print("=" * 80)
        
        jql_resloved = "project = QAB AND status = 'Resloved-' ORDER BY updated DESC"
        print(f"\n[*] JQL: {jql_resloved}")
        try:
            resloved_issues = jira.search_issues(jql_resloved, maxResults=10)
            print(f"[OK] Found {len(resloved_issues)} tickets with status 'Resloved-'")
            
            if resloved_issues:
                print("\nSample tickets:")
                for issue in resloved_issues[:5]:
                    print(f"  {issue.key}: {issue.fields.summary[:60]}...")
                    print(f"    Status: {issue.fields.status}")
        except Exception as e:
            print(f"[ERROR] {e}")
        
        print("\n" + "=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
