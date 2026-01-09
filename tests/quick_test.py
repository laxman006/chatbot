#!/usr/bin/env python
"""Quick test of endpoint"""

import httpx
import json

try:
    client = httpx.Client(timeout=30.0)
    response = client.get(
        "http://localhost:8002/analytics/langfuse/teams/summary",
        params={
            "start_date": "2025-11-16",
            "end_date": "2025-12-16"
        }
    )
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"\nTotal Questions: {data.get('total_questions')}")
        print(f"Total Teams: {data.get('total_teams')}")
        print(f"Active Teams: {data.get('total_active_teams')}")
        
        teams = data.get('teams', [])
        if teams:
            print(f"\nTop Teams:")
            for team in teams[:5]:
                print(f"  - {team['team_name']:20s}: {team['total_questions']:3d} questions, {team['active_members_count']}/{team['member_count']} members")
    else:
        print(f"Response: {response.text[:500]}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()

