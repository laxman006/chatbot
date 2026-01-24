# -*- coding: utf-8 -*-
"""
Test script to check for Jira tickets updated in the last 3 days
(today, yesterday, day before yesterday)
Uses lightweight API calls to just count tickets, not fetch full details
"""

import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
from datetime import datetime, timedelta
from config import JIRA_SERVER, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEYS

def build_jql_for_date(date_str: str) -> str:
    """Build JQL query for tickets updated on a specific date."""
    jql_parts = []
    
    # Project filter
    if JIRA_PROJECT_KEYS:
        raw_keys = JIRA_PROJECT_KEYS.split(',')
        project_keys = [key.strip() for key in raw_keys if key.strip() and not key.strip().startswith('#')]
        if project_keys:
            project_filter = " OR ".join([f"project = {key}" for key in project_keys])
            jql_parts.append(f"({project_filter})")
    
    # Status filter
    status_filter = "(status = Resolved OR status = 'Resolved-' OR status = Closed)"
    jql_parts.append(status_filter)
    
    # Date filter - updated on this specific date
    start_date = f"{date_str} 00:00"
    end_date = f"{date_str} 23:59"
    jql_parts.append(f"updated >= '{start_date}'")
    jql_parts.append(f"updated <= '{end_date}'")
    
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    return jql

def count_tickets_for_date(date_str: str) -> tuple[int, list]:
    """Count tickets updated on a specific date. Returns (count, sample_keys)."""
    jql = build_jql_for_date(date_str)
    print(f"  JQL Query: {jql}")
    
    url = f"{JIRA_SERVER}/rest/api/3/search/jql"
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    }
    
    params = {
        'jql': jql,
        'startAt': 0,
        'maxResults': 10,  # Just get first 10 for samples
        'fields': 'key,summary,updated,status'  # Minimal fields
    }
    
    try:
        response = requests.get(
            url,
            headers=headers,
            params=params,
            auth=(JIRA_EMAIL, JIRA_API_TOKEN),
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"  [ERROR] API returned {response.status_code}: {response.text[:200]}")
            return 0, []
        
        data = response.json()
        total = data.get('total', 0)
        
        # Get sample ticket keys
        sample_keys = []
        for issue in data.get('issues', [])[:5]:
            key = issue.get('key', 'N/A')
            summary = issue.get('fields', {}).get('summary', 'N/A')[:50]
            updated = issue.get('fields', {}).get('updated', 'N/A')
            status = issue.get('fields', {}).get('status', {}).get('name', 'N/A')
            sample_keys.append({
                'key': key,
                'summary': summary,
                'updated': updated,
                'status': status
            })
        
        return total, sample_keys
        
    except Exception as e:
        print(f"  [ERROR] Failed to fetch: {e}")
        return 0, []

def main():
    print("=" * 80)
    print("Checking Jira Tickets for Last 3 Days (Lightweight Check)")
    print("=" * 80)
    print()
    
    # Calculate dates
    now = datetime.now()
    today = now.strftime('%Y-%m-%d')
    yesterday = (now - timedelta(days=1)).strftime('%Y-%m-%d')
    day_before_yesterday = (now - timedelta(days=2)).strftime('%Y-%m-%d')
    
    print(f"Today: {today}")
    print(f"Yesterday: {yesterday}")
    print(f"Day Before Yesterday: {day_before_yesterday}")
    print()
    
    # Check each day
    days_to_check = [
        ("Today", today),
        ("Yesterday", yesterday),
        ("Day Before Yesterday", day_before_yesterday)
    ]
    
    total_tickets = 0
    
    for day_name, date_str in days_to_check:
        print("-" * 80)
        print(f"Checking {day_name} ({date_str})...")
        print("-" * 80)
        
        count, samples = count_tickets_for_date(date_str)
        total_tickets += count
        
        print(f"\n[{day_name}] Found {count} tickets updated on {date_str}")
        
        if samples:
            print(f"\nSample tickets:")
            for i, ticket in enumerate(samples, 1):
                print(f"  {i}. {ticket['key']}: {ticket['summary']}...")
                print(f"     Status: {ticket['status']}, Updated: {ticket['updated']}")
        
        print()
    
    print("=" * 80)
    print(f"SUMMARY: Total tickets in last 3 days: {total_tickets}")
    print("=" * 80)
    
    if total_tickets == 0:
        print("\n⚠️  No tickets found in the last 3 days.")
        print("   This explains why sync shows 0 documents added.")
    else:
        print(f"\n✅ Found {total_tickets} tickets that should be synced.")
        print("   If sync shows 0 documents, there may be an issue with the sync logic.")

if __name__ == "__main__":
    main()
