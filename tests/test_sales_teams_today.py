#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test file to check which users from Sales [SMB], Sales [ENT], Sales [AM] teams are active TODAY.

This script:
1. Fetches all traces from TODAY
2. Filters by the 3 Sales teams
3. Shows which users made queries and their trace counts
4. Identifies missing users (in team but no traces)
5. Identifies unassigned emails (in traces but not in teams)
"""

import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Set
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

# Import from app
import sys
sys.path.insert(0, '/root')

from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.models.teams import get_all_teams, get_team_by_member_email, get_all_email_to_team_mapping

# Target teams for testing
TARGET_TEAMS = ["Sales [SMB]", "Sales [ENT]", "Sales [AM]"]


async def get_today_traces():
    """Fetch all traces from TODAY."""
    now = datetime.now(timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    print(f"\n{'='*80}")
    print(f"[TEST] Fetching traces for TODAY")
    print(f"Date Range: {start_of_today} to {end_of_today}")
    print(f"{'='*80}\n")
    
    all_traces = []
    page = 1
    max_pages = 15              
    
    async with httpx.AsyncClient() as client:
        while page <= max_pages:
            try:
                params = {
                    "page": page,
                    "limit": 100,
                    "orderBy[createdAt]": "DESC",
                    "createdAt[gte]": start_of_today.isoformat() + "Z",
                    "createdAt[lte]": end_of_today.isoformat() + "Z"
                }
                
                print(f"[FETCH] Page {page}...")
                response = await client.get(
                    f"{LANGFUSE_HOST}/api/public/traces",
                    params=params,
                    auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                    timeout=45.0
                )
                
                if response.status_code != 200:
                    print(f"[ERROR] HTTP {response.status_code}")
                    break
                
                traces_response = response.json()
                traces = traces_response.get("data", [])
                
                if not traces:
                    print(f"[INFO] No more traces at page {page}")
                    break
                
                all_traces.extend(traces)
                print(f"[INFO] Got {len(traces)} traces, total so far: {len(all_traces)}")
                
                if len(traces) < 100:
                    break
                
                page += 1
                await asyncio.sleep(0.5)
            
            except Exception as e:
                print(f"[ERROR] Page {page}: {e}")
                break
    
    return all_traces


def analyze_traces_by_team(all_traces: List[Dict]) -> Dict:
    """Analyze traces grouped by target teams."""
    
    email_to_team_map = get_all_email_to_team_mapping()
    all_teams = get_all_teams()
    
    # Initialize result structure
    result = {
        team_name: {
            "total_traces": 0,
            "active_members": {},  # email -> trace_count
            "missing_members": [],  # members with no traces
            "all_members": []  # all members in team
        }
        for team_name in TARGET_TEAMS
    }
    
    # Populate all members
    for team_name in TARGET_TEAMS:
        team_info = all_teams.get(team_name, {})
        members = team_info.get("members", [])
        for member in members:
            result[team_name]["all_members"].append({
                "name": member.get("name"),
                "email": member.get("email")
            })
    
    # Process traces
    print(f"\n{'='*80}")
    print(f"[ANALYSIS] Processing {len(all_traces)} total traces...")
    print(f"{'='*80}\n")
    
    unassigned_emails_set = set()
    
    for trace in all_traces:
        # Get email from trace
        metadata = trace.get("metadata", {})
        user_email = metadata.get("user_email")
        
        if not user_email:
            continue
        
        # Handle email being list or string
        if isinstance(user_email, list):
            email_str = user_email[0].lower().strip() if user_email else None
        else:
            email_str = str(user_email).lower().strip() if user_email else None
        
        if not email_str:
            continue
        
        # Find team for this email
        team_name = get_team_by_member_email(email_str)
        
        # Check if it's in one of our target teams
        if team_name in TARGET_TEAMS:
            result[team_name]["total_traces"] += 1
            
            if email_str not in result[team_name]["active_members"]:
                result[team_name]["active_members"][email_str] = 0
            result[team_name]["active_members"][email_str] += 1
        else:
            unassigned_emails_set.add((email_str, team_name))
    
    # Find missing members (in team but no traces)
    for team_name in TARGET_TEAMS:
        all_member_emails = [m["email"].lower() for m in result[team_name]["all_members"]]
        active_emails = set(result[team_name]["active_members"].keys())
        
        for member in result[team_name]["all_members"]:
            if member["email"].lower() not in active_emails:
                result[team_name]["missing_members"].append(member)
    
    # Print detailed report
    print(f"\n{'='*80}")
    print(f"[REPORT] TODAY'S TRACE ACTIVITY BY TEAM")
    print(f"{'='*80}\n")
    
    for team_name in TARGET_TEAMS:
        team_data = result[team_name]
        print(f"\n[TEAM] {team_name}")
        print(f"   Total Traces: {team_data['total_traces']}")
        print(f"   Total Members: {len(team_data['all_members'])}")
        print(f"   Active Members: {len(team_data['active_members'])}")
        print(f"   Inactive Members: {len(team_data['missing_members'])}")
        
        if team_data['active_members']:
            print(f"\n   [ACTIVE] ACTIVE MEMBERS (Used today):")
            for email, count in sorted(team_data['active_members'].items(), key=lambda x: x[1], reverse=True):
                # Find member name
                member_name = next((m["name"] for m in team_data["all_members"] if m["email"].lower() == email), email)
                print(f"      * {member_name}: {count} traces")
        
        if team_data['missing_members']:
            print(f"\n   [INACTIVE] INACTIVE MEMBERS (No traces today):")
            for member in team_data['missing_members']:
                print(f"      * {member['name']} ({member['email']})")
        
        print(f"\n   {'-'*76}")
    
    # Print unassigned emails
    if unassigned_emails_set:
        print(f"\n\n[WARNING] EMAILS IN TRACES BUT NOT IN TARGET TEAMS:")
        for email, assigned_team in sorted(unassigned_emails_set):
            print(f"   * {email} -> Assigned to: {assigned_team}")
    
    return result


async def main():
    """Main test function."""
    try:
        # Fetch traces
        traces = await get_today_traces()
        print(f"\n[SUCCESS] Fetched {len(traces)} traces from TODAY")
        
        # Analyze by team
        analysis = analyze_traces_by_team(traces)
        
        # Summary
        print(f"\n\n{'='*80}")
        print(f"[SUMMARY]")
        print(f"{'='*80}\n")
        
        total_today = sum(data["total_traces"] for data in analysis.values())
        print(f"Total traces in 3 Sales teams TODAY: {total_today}")
        
        for team_name in TARGET_TEAMS:
            traces_count = analysis[team_name]["total_traces"]
            active_count = len(analysis[team_name]["active_members"])
            print(f"  • {team_name}: {traces_count} traces from {active_count} members")
        
        print(f"\n[DONE] Test completed!")
    
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

