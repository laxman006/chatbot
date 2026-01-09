# -*- coding: utf-8 -*-
"""
Test script to extract AI suggestions from Jira ticket CFITS-2065
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA
import json

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://cf2020.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

def test_extract_suggestions():
    """Test extracting AI suggestions from a specific ticket."""
    
    print("=" * 60)
    print("TESTING JIRA AI SUGGESTIONS EXTRACTION")
    print("=" * 60)
    print(f"Server: {JIRA_SERVER}")
    print(f"Ticket: CFITS-2065")
    print("-" * 60)
    
    try:
        # Connect to Jira
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        print(f"[OK] Connected to Jira as: {jira.current_user()}")
        
        # Fetch the specific ticket with all possible expansions
        ticket_key = "CFITS-2065"
        print(f"\n[*] Fetching ticket {ticket_key}...")
        
        # Try different expand options
        expand_options = [
            'renderedFields,comments',
            'renderedFields,comments,changelog',
            'renderedFields,comments,changelog,names',
            '*all'  # Try to get everything
        ]
        
        issue = None
        for expand in expand_options:
            try:
                print(f"\n[*] Trying expand: {expand}")
                issue = jira.issue(ticket_key, expand=expand)
                print(f"[OK] Successfully fetched with expand: {expand}")
                break
            except Exception as e:
                print(f"[WARN] Failed with expand '{expand}': {e}")
                continue
        
        if not issue:
            print("[ERROR] Could not fetch ticket")
            return
        
        print(f"\n[*] Ticket: {issue.key} - {issue.fields.summary}")
        print(f"    Status: {issue.fields.status}")
        print(f"    Type: {issue.fields.issuetype}")
        
        # Method 1: Check all fields in issue.fields
        print("\n" + "=" * 60)
        print("METHOD 1: Checking all fields in issue.fields")
        print("=" * 60)
        
        all_fields = []
        for attr_name in dir(issue.fields):
            if not attr_name.startswith('_'):
                try:
                    attr_value = getattr(issue.fields, attr_name)
                    if attr_value and isinstance(attr_value, (str, list, dict)):
                        # Check if it contains suggestion-like content
                        attr_str = str(attr_value).lower()
                        if any(keyword in attr_str for keyword in ['suggest', 'solution', 'rovo', 'ai']):
                            all_fields.append({
                                'name': attr_name,
                                'type': type(attr_value).__name__,
                                'value_preview': str(attr_value)[:200]
                            })
                            print(f"\n[FOUND] Field: {attr_name}")
                            print(f"  Type: {type(attr_value).__name__}")
                            print(f"  Preview: {str(attr_value)[:200]}...")
                except Exception as e:
                    pass
        
        if not all_fields:
            print("[INFO] No suggestion-related fields found in issue.fields")
        
        # Method 2: Check renderedFields
        print("\n" + "=" * 60)
        print("METHOD 2: Checking renderedFields")
        print("=" * 60)
        
        if hasattr(issue.fields, 'renderedFields'):
            rendered = issue.fields.renderedFields
            rendered_fields = []
            for attr_name in dir(rendered):
                if not attr_name.startswith('_'):
                    try:
                        attr_value = getattr(rendered, attr_name, None)
                        if attr_value:
                            attr_str = str(attr_value).lower()
                            if any(keyword in attr_str for keyword in ['suggest', 'solution', 'rovo', 'ai']):
                                rendered_fields.append({
                                    'name': attr_name,
                                    'value_preview': str(attr_value)[:300]
                                })
                                print(f"\n[FOUND] Rendered Field: {attr_name}")
                                print(f"  Preview: {str(attr_value)[:300]}...")
                    except Exception as e:
                        pass
            
            if not rendered_fields:
                print("[INFO] No suggestion-related fields found in renderedFields")
        else:
            print("[INFO] renderedFields not available")
        
        # Method 3: Check comments for AI suggestions
        print("\n" + "=" * 60)
        print("METHOD 3: Checking comments for AI suggestions")
        print("=" * 60)
        
        if hasattr(issue.fields, 'comment') and issue.fields.comment:
            print(f"[INFO] Found {len(issue.fields.comment.comments)} comments")
            for idx, comment in enumerate(issue.fields.comment.comments, 1):
                comment_body = str(comment.body).lower()
                if any(marker in comment_body for marker in ['uses ai', 'ai suggestion', 'rovo', 'solution:', 'verify results']):
                    print(f"\n[FOUND] AI-related comment #{idx}:")
                    print(f"  Author: {comment.author}")
                    print(f"  Created: {comment.created}")
                    print(f"  Body preview: {str(comment.body)[:500]}...")
        
        # Method 4: Try REST API directly for suggestions
        print("\n" + "=" * 60)
        print("METHOD 4: Trying REST API endpoints")
        print("=" * 60)
        
        api_endpoints = [
            f"/rest/api/3/issue/{ticket_key}/suggestions",
            f"/rest/api/3/issue/{ticket_key}/rovo",
            f"/rest/api/3/issue/{ticket_key}/ai",
            f"/rest/api/2/issue/{ticket_key}/suggestions",
        ]
        
        for endpoint in api_endpoints:
            try:
                url = f"{JIRA_SERVER}{endpoint}"
                print(f"\n[*] Trying: {endpoint}")
                response = jira._session.get(url)
                print(f"  Status: {response.status_code}")
                if response.status_code == 200:
                    data = response.json()
                    print(f"  [SUCCESS] Response: {json.dumps(data, indent=2)[:500]}...")
                elif response.status_code == 404:
                    print(f"  [INFO] Endpoint not found (404)")
                else:
                    print(f"  [INFO] Response: {response.text[:200]}")
            except Exception as e:
                print(f"  [ERROR] {e}")
        
        # Method 5: Get raw JSON to see all available fields
        print("\n" + "=" * 60)
        print("METHOD 5: Getting raw JSON to inspect all fields")
        print("=" * 60)
        
        try:
            raw_url = f"{JIRA_SERVER}/rest/api/3/issue/{ticket_key}?expand=renderedFields,names"
            response = jira._session.get(raw_url)
            if response.status_code == 200:
                raw_data = response.json()
                
                # Look for suggestion-related keys
                print("\n[*] Searching for suggestion-related keys in raw JSON...")
                suggestion_keys = []
                
                def search_dict(d, path=""):
                    """Recursively search for suggestion-related keys."""
                    if isinstance(d, dict):
                        for key, value in d.items():
                            current_path = f"{path}.{key}" if path else key
                            key_lower = key.lower()
                            if any(kw in key_lower for kw in ['suggest', 'rovo', 'ai', 'solution']):
                                suggestion_keys.append({
                                    'path': current_path,
                                    'key': key,
                                    'value_preview': str(value)[:200]
                                })
                            if isinstance(value, (dict, list)):
                                search_dict(value, current_path)
                    elif isinstance(d, list):
                        for idx, item in enumerate(d):
                            search_dict(item, f"{path}[{idx}]")
                
                search_dict(raw_data)
                
                if suggestion_keys:
                    print(f"\n[FOUND] {len(suggestion_keys)} suggestion-related keys:")
                    for item in suggestion_keys:
                        print(f"\n  Path: {item['path']}")
                        print(f"  Key: {item['key']}")
                        print(f"  Preview: {item['value_preview']}")
                else:
                    print("[INFO] No suggestion-related keys found in raw JSON")
                    
                # Save full JSON for inspection
                output_file = "jira_ticket_raw.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(raw_data, f, indent=2, ensure_ascii=False)
                print(f"\n[OK] Full JSON saved to: {output_file}")
        except Exception as e:
            print(f"[ERROR] Failed to get raw JSON: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_extract_suggestions()
