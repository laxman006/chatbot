# -*- coding: utf-8 -*-
"""
Test script to verify data extraction from Migration KB Board (PRI project)
Focus: Closed/Resolved tickets with specific fields
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
                    # Some custom fields return dicts
                    return str(field_value.get('value', field_value))
                elif hasattr(field_value, 'value'):
                    # JIRA CustomFieldOption objects
                    return str(field_value.value)
                else:
                    return str(field_value)
    except Exception as e:
        print(f"[WARN] Could not extract {field_name} ({field_id}): {e}")
    return None

def test_migration_kb_tickets():
    """Test extracting tickets from Migration KB Board."""
    
    print("=" * 80)
    print("TESTING MIGRATION KB BOARD TICKET EXTRACTION")
    print("=" * 80)
    print(f"Project: PRI (Migration KB Board)")
    print(f"Status: Closed OR Resolved")
    print(f"Fields: Ticket ID, Date/Time, Description, Root Cause, Combination")
    print("-" * 80)
    
    try:
        # Connect to Jira
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        print(f"[OK] Connected to Jira as: {jira.current_user()}")
        
        # Build JQL query for PRI project, closed/resolved tickets
        jql = "project = PRI AND (status = Closed OR status = Resolved) ORDER BY updated DESC"
        print(f"\n[*] JQL Query: {jql}")
        
        # Fetch tickets (limit to 10 for testing)
        max_results = 10
        print(f"[*] Fetching up to {max_results} tickets...")
        
        issues = jira.search_issues(
            jql,
            maxResults=max_results,
            expand='changelog,renderedFields,comments'
        )
        
        print(f"[OK] Found {len(issues)} tickets")
        
        if not issues:
            print("[WARNING] No tickets found matching criteria")
            return
        
        # Extract and verify data
        tickets_data = []
        for idx, issue in enumerate(issues, 1):
            print(f"\n{'='*80}")
            print(f"TICKET {idx}/{len(issues)}: {issue.key}")
            print(f"{'='*80}")
            
            # Extract required fields
            ticket_id = issue.key
            created_date = str(issue.fields.created)
            updated_date = str(issue.fields.updated)
            resolved_date = str(issue.fields.resolutiondate) if hasattr(issue.fields, 'resolutiondate') and issue.fields.resolutiondate else None
            
            # Description
            description = ""
            if hasattr(issue.fields, 'description') and issue.fields.description:
                description = clean_html(str(issue.fields.description))
            
            # Root Cause (customfield_10059)
            root_cause = extract_custom_field(issue, 'customfield_10059', 'Root Cause')
            
            # Combination (customfield_10236)
            combination = extract_custom_field(issue, 'customfield_10236', 'Combination')
            
            # Fix Description (customfield_10402)
            fix_description = extract_custom_field(issue, 'customfield_10402', 'Fix Description')
            
            # Comments (less priority, but include)
            comments = []
            if hasattr(issue.fields, 'comment') and issue.fields.comment:
                for comment in issue.fields.comment.comments:
                    comment_body = clean_html(str(comment.body))
                    if comment_body.strip():
                        comments.append({
                            "author": str(comment.author),
                            "body": comment_body[:200] + "..." if len(comment_body) > 200 else comment_body,
                            "created": str(comment.created)
                        })
            
            # Status
            status = str(issue.fields.status)
            
            # Build ticket data
            ticket_data = {
                "ticket_id": ticket_id,
                "summary": issue.fields.summary,
                "created_date": created_date,
                "updated_date": updated_date,
                "resolved_date": resolved_date,
                "status": status,
                "description": description,
                "root_cause": root_cause,
                "combination": combination,
                "fix_description": fix_description,
                "comments_count": len(comments),
                "url": f"{JIRA_SERVER}/browse/{ticket_id}"
            }
            
            tickets_data.append(ticket_data)
            
            # Display extracted data
            print(f"\n[EXTRACTED DATA]")
            print(f"  Ticket ID: {ticket_id}")
            print(f"  Summary: {issue.fields.summary}")
            print(f"  Status: {status}")
            print(f"  Created: {created_date}")
            print(f"  Updated: {updated_date}")
            print(f"  Resolved: {resolved_date or 'N/A'}")
            print(f"  Description Length: {len(description)} characters")
            print(f"  Root Cause: {root_cause[:100] + '...' if root_cause and len(root_cause) > 100 else root_cause or 'N/A'}")
            print(f"  Combination: {combination or 'N/A'}")
            print(f"  Fix Description: {fix_description[:100] + '...' if fix_description and len(fix_description) > 100 else fix_description or 'N/A'}")
            print(f"  Comments: {len(comments)}")
            
            # Validation checks
            print(f"\n[VALIDATION]")
            issues_found = []
            
            if not description:
                issues_found.append("❌ Missing Description")
            else:
                print(f"  ✅ Description: Present ({len(description)} chars)")
            
            if not root_cause:
                issues_found.append("⚠️  Missing Root Cause")
            else:
                print(f"  ✅ Root Cause: Present ({len(root_cause)} chars)")
            
            if not combination:
                issues_found.append("⚠️  Missing Combination")
            else:
                print(f"  ✅ Combination: Present ({combination})")
            
            if not fix_description:
                issues_found.append("⚠️  Missing Fix Description")
            else:
                print(f"  ✅ Fix Description: Present ({len(fix_description)} chars)")
            
            if issues_found:
                print(f"  Issues: {', '.join(issues_found)}")
            
            # Show description preview
            if description:
                print(f"\n[DESCRIPTION PREVIEW]")
                desc_lines = description.split('\n')[:5]
                for line in desc_lines:
                    print(f"  {line[:100]}")
                if len(description.split('\n')) > 5:
                    print(f"  ... ({len(description.split('\n')) - 5} more lines)")
        
        # Summary
        print(f"\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tickets Processed: {len(tickets_data)}")
        print(f"Tickets with Description: {sum(1 for t in tickets_data if t['description'])}")
        print(f"Tickets with Root Cause: {sum(1 for t in tickets_data if t['root_cause'])}")
        print(f"Tickets with Combination: {sum(1 for t in tickets_data if t['combination'])}")
        print(f"Total Comments: {sum(t['comments_count'] for t in tickets_data)}")
        
        # Save to JSON for inspection
        output_file = "migration_kb_tickets_test.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(tickets_data, f, indent=2, ensure_ascii=False)
        print(f"\n[OK] Data saved to: {output_file}")
        
        # Field mapping verification
        print(f"\n{'='*80}")
        print("FIELD MAPPING VERIFICATION")
        print(f"{'='*80}")
        print("Expected Fields:")
        print("  ✅ Ticket ID: issue.key")
        print("  ✅ Date/Time: issue.fields.created, updated, resolutiondate")
        print("  ✅ Description: issue.fields.description")
        print("  ✅ Root Cause: issue.fields.customfield_10059")
        print("  ✅ Combination: issue.fields.customfield_10236")
        print("  ✅ Comments: issue.fields.comment.comments (less priority)")
        
        print(f"\n{'='*80}")
        print("TEST COMPLETE")
        print(f"{'='*80}")
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_migration_kb_tickets()
