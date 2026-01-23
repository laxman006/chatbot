# -*- coding: utf-8 -*-
"""
Multi-Board Jira Test Script
Tests connection and data extraction from PRI and QAB boards
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA
from bs4 import BeautifulSoup
from datetime import datetime
import json

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://cf2020.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

# Boards to test
PROJECT_KEYS = ["PRI", "QAB"]


def clean_html(text):
    """Clean HTML tags from text."""
    if not text:
        return ""
    soup = BeautifulSoup(str(text), "html.parser")
    return soup.get_text(separator="\n", strip=True)


def extract_custom_field(issue, field_id, field_name):
    """Extract custom field value safely."""
    try:
        if hasattr(issue.fields, field_id):
            field_value = getattr(issue.fields, field_id)
            if field_value:
                # Handle different field types
                if isinstance(field_value, str):
                    return clean_html(field_value)
                elif isinstance(field_value, list):
                    # Handle multi-select fields (like Combination)
                    values = []
                    for item in field_value:
                        if hasattr(item, 'value'):
                            values.append(str(item.value))
                        elif isinstance(item, dict):
                            values.append(str(item.get('value', item)))
                        else:
                            values.append(str(item))
                    return ', '.join(values) if values else None
                elif isinstance(field_value, dict):
                    return str(field_value.get('value', field_value))
                elif hasattr(field_value, 'value'):
                    return str(field_value.value)
                else:
                    return str(field_value)
    except Exception as e:
        print(f"[WARN] Could not extract {field_name} ({field_id}): {e}")
    return None


def test_board(jira, project_key):
    """Test a single board."""
    print(f"\n{'='*80}")
    print(f"TESTING {project_key} BOARD")
    print(f"{'='*80}")
    
    # Build JQL query
    # Note: QAB board uses "Resolved-" (with dash) instead of "Resolved"
    jql = f"project = {project_key} AND (status = Closed OR status = Resolved OR status = 'Resolved-') ORDER BY updated DESC"
    print(f"[*] JQL Query: {jql}")
    
    try:
        # First, get total count
        print(f"[*] Getting total count of resolved/closed tickets...")
        count_results = jira.search_issues(jql, maxResults=0)
        total_count = count_results.total
        print(f"[OK] Total {project_key} tickets (Resolved/Closed): {total_count}")
        
        # Fetch sample tickets (10)
        print(f"[*] Fetching 10 sample tickets for validation...")
        issues = jira.search_issues(
            jql,
            maxResults=10,
            expand='changelog,renderedFields,comments'
        )
        
        if not issues:
            print(f"[WARNING] No tickets found for {project_key}")
            return {
                "project_key": project_key,
                "total_count": 0,
                "sample_count": 0,
                "tickets": [],
                "field_availability": {},
                "status": "no_tickets"
            }
        
        print(f"[OK] Retrieved {len(issues)} sample tickets")
        
        # Test field extraction
        field_counts = {
            "description": 0,
            "root_cause": 0,
            "combination": 0,
            "fix_description": 0,
            "comments": 0
        }
        
        tickets_data = []
        
        for idx, issue in enumerate(issues, 1):
            # Extract fields
            description = ""
            if hasattr(issue.fields, 'description') and issue.fields.description:
                description = clean_html(str(issue.fields.description))
                if description:
                    field_counts["description"] += 1
            
            root_cause = extract_custom_field(issue, 'customfield_10059', 'Root Cause')
            if root_cause:
                field_counts["root_cause"] += 1
            
            combination = extract_custom_field(issue, 'customfield_10236', 'Combination')
            if combination:
                field_counts["combination"] += 1
            
            fix_description = extract_custom_field(issue, 'customfield_10402', 'Fix Description')
            if fix_description:
                field_counts["fix_description"] += 1
            
            # Comments
            comment_count = 0
            if hasattr(issue.fields, 'comment') and issue.fields.comment:
                comment_count = len(issue.fields.comment.comments)
                if comment_count > 0:
                    field_counts["comments"] += 1
            
            ticket_data = {
                "ticket_id": issue.key,
                "summary": issue.fields.summary[:100] + "..." if len(issue.fields.summary) > 100 else issue.fields.summary,
                "status": str(issue.fields.status),
                "has_description": bool(description),
                "has_root_cause": bool(root_cause),
                "has_combination": bool(combination),
                "has_fix_description": bool(fix_description),
                "comment_count": comment_count
            }
            tickets_data.append(ticket_data)
            
            # Print ticket summary
            print(f"\n  [{idx}] {issue.key}: {ticket_data['summary']}")
            print(f"      Status: {ticket_data['status']}")
            print(f"      Description: {'✓' if ticket_data['has_description'] else '✗'}")
            print(f"      Root Cause: {'✓' if ticket_data['has_root_cause'] else '✗'}")
            print(f"      Combination: {'✓' if ticket_data['has_combination'] else '✗'}")
            print(f"      Fix Description: {'✓' if ticket_data['has_fix_description'] else '✗'}")
            print(f"      Comments: {ticket_data['comment_count']}")
        
        # Field availability summary
        print(f"\n{'-'*80}")
        print(f"FIELD AVAILABILITY SUMMARY ({project_key})")
        print(f"{'-'*80}")
        print(f"  Description:      {field_counts['description']}/{len(issues)} ({field_counts['description']/len(issues)*100:.1f}%)")
        print(f"  Root Cause:       {field_counts['root_cause']}/{len(issues)} ({field_counts['root_cause']/len(issues)*100:.1f}%)")
        print(f"  Combination:      {field_counts['combination']}/{len(issues)} ({field_counts['combination']/len(issues)*100:.1f}%)")
        print(f"  Fix Description:  {field_counts['fix_description']}/{len(issues)} ({field_counts['fix_description']/len(issues)*100:.1f}%)")
        print(f"  Comments:         {field_counts['comments']}/{len(issues)} ({field_counts['comments']/len(issues)*100:.1f}%)")
        
        return {
            "project_key": project_key,
            "total_count": total_count,
            "sample_count": len(issues),
            "tickets": tickets_data,
            "field_availability": field_counts,
            "status": "success"
        }
        
    except Exception as e:
        print(f"[ERROR] Failed to test {project_key} board: {e}")
        import traceback
        traceback.print_exc()
        return {
            "project_key": project_key,
            "total_count": 0,
            "sample_count": 0,
            "tickets": [],
            "field_availability": {},
            "status": "error",
            "error": str(e)
        }


def test_multi_board():
    """Test multiple Jira boards."""
    print("=" * 80)
    print("MULTI-BOARD JIRA INTEGRATION TEST")
    print("=" * 80)
    print(f"Testing boards: {', '.join(PROJECT_KEYS)}")
    print(f"Server: {JIRA_SERVER}")
    print(f"Email: {JIRA_EMAIL}")
    print("-" * 80)
    
    # Check credentials
    if not JIRA_API_TOKEN:
        print("[ERROR] JIRA_API_TOKEN not set in environment")
        print("Please add it to your .env file")
        return False
    
    try:
        # Connect to Jira
        print("\n[*] Connecting to Jira...")
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        print(f"[OK] Connected to Jira as: {jira.current_user()}")
        
        # Test each board
        results = {}
        for project_key in PROJECT_KEYS:
            results[project_key] = test_board(jira, project_key)
        
        # Overall summary
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        
        total_tickets = sum(r['total_count'] for r in results.values())
        print(f"\nTotal Tickets Across All Boards: {total_tickets}")
        
        for project_key, result in results.items():
            status_icon = "✓" if result['status'] == 'success' else "✗"
            print(f"\n{status_icon} {project_key} Board:")
            print(f"   Total Tickets: {result['total_count']}")
            print(f"   Sample Tested: {result['sample_count']}")
            if result['status'] == 'success' and result['sample_count'] > 0:
                field_avail = result['field_availability']
                sample_count = result['sample_count']
                print(f"   Field Availability:")
                print(f"     - Description: {field_avail.get('description', 0)}/{sample_count}")
                print(f"     - Root Cause: {field_avail.get('root_cause', 0)}/{sample_count}")
                print(f"     - Combination: {field_avail.get('combination', 0)}/{sample_count}")
                print(f"     - Fix Description: {field_avail.get('fix_description', 0)}/{sample_count}")
            elif result['status'] == 'error':
                print(f"   Error: {result.get('error', 'Unknown error')}")
        
        # Recommendations
        print(f"\n{'='*80}")
        print("RECOMMENDATIONS")
        print(f"{'='*80}")
        
        if total_tickets > 0:
            print(f"\n✓ Ready to proceed with implementation!")
            print(f"\nRecommended Configuration:")
            print(f"  JIRA_PROJECT_KEYS=PRI,QAB")
            print(f"  JIRA_MAX_ISSUES={total_tickets + 500}  # Total tickets + buffer")
            print(f"  JIRA_DATE_FILTER=  # Empty for all tickets")
            
            # Multi-board JQL
            jql_parts = " OR ".join([f"project = {k}" for k in PROJECT_KEYS])
            print(f"\nMulti-Board JQL Query:")
            print(f"  ({jql_parts}) AND (status = Resolved OR status = Closed) ORDER BY updated DESC")
        else:
            print(f"\n⚠ No tickets found. Please verify:")
            print(f"  1. Project keys are correct (PRI, QAB)")
            print(f"  2. You have access to these projects")
            print(f"  3. Tickets exist with Resolved/Closed status")
        
        # Save results
        output_file = "multi_board_test_results.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Detailed results saved to: {output_file}")
        
        print(f"\n{'='*80}")
        print("TEST COMPLETE")
        print(f"{'='*80}")
        
        return all(r['status'] == 'success' for r in results.values())
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_multi_board()
    sys.exit(0 if success else 1)
