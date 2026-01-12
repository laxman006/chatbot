#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Simulate the team analytics endpoint logic to debug what's being returned
"""

import asyncio
import httpx
import json
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from app.models.teams import TEAMS, get_team_for_member
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST


def get_team_color(team_name: str) -> str:
    """Get the color hex code for a team."""
    colors = {
        "Content": "#3B82F6",  # Blue
        "Messaging & Email": "#10B981",  # Green
        "CF Manage": "#F59E0B",  # Amber
        "QA": "#EF4444",  # Red
        "Neutara Labs": "#8B5CF6",  # Purple
        "Infra": "#EC4899",  # Pink
        "Pre-Sales": "#06B6D4",  # Cyan
        "Sales Ops": "#14B8A6"  # Teal
    }
    return colors.get(team_name, "#6B7280")


async def simulate_endpoint():
    print("[INFO] Simulating team analytics endpoint\n")
    
    time_filter = "today"
    
    # Calculate time range
    start_time = None
    end_time = datetime.utcnow()
    max_pages = 30
    request_timeout = 60.0
    
    if time_filter == "today":
        start_time = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        max_pages = 10
        request_timeout = 30.0
    
    # Initialize team data
    team_stats = {}
    for team_name in TEAMS.keys():
        team_stats[team_name] = {
            "team_name": team_name,
            "lead": TEAMS[team_name].get("Lead"),
            "lead_email": "",
            "member_count": len(TEAMS[team_name].get("Members", [])),
            "active_members_count": 0,
            "color": get_team_color(team_name),
            "total_questions": 0,
            "unique_questions": 0,
            "top_questions": [],
            "questions_list": [],
            "active_members": set()
        }
    
    print(f"[1] Initialized {len(team_stats)} teams")
    
    # Fetch traces from Langfuse
    page = 1
    batch_limit = 100
    total_traces = 0
    
    async with httpx.AsyncClient() as client:
        print(f"\n[2] Fetching traces from Langfuse...")
        print(f"    Time range: {start_time} to {end_time}")
        print(f"    Max pages: {max_pages}, Batch size: {batch_limit}\n")
        
        while page <= max_pages:
            try:
                params = {
                    "page": page,
                    "limit": batch_limit,
                    "orderBy[createdAt]": "DESC"
                }
                if start_time:
                    params["createdAt[gte]"] = start_time.isoformat() + "Z"
                if end_time:
                    params["createdAt[lte]"] = end_time.isoformat() + "Z"
                
                response = await client.get(
                    f"{LANGFUSE_HOST}/api/public/traces",
                    params=params,
                    auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                    timeout=request_timeout
                )
                
                if response.status_code == 429:
                    print(f"[WARN] Rate limited at page {page}, stopping")
                    break
                
                response.raise_for_status()
                
                traces_response = response.json()
                traces = traces_response.get("data", [])
                
                print(f"    Page {page}: Got {len(traces)} traces")
                
                if not traces:
                    print(f"    No more traces, stopping pagination")
                    break
                
                total_traces += len(traces)
                
                for i, trace in enumerate(traces[:3]):  # Show first 3 traces
                    user_id = trace.get("userId", "")
                    metadata = trace.get("metadata", {})
                    question = trace.get("input", "")
                    user_email = str(metadata.get("user_email", ""))
                    user_name = str(metadata.get("user_name", "Unknown"))
                    
                    print(f"      Trace {i+1}: user_id={user_id}, email={user_email}, name={user_name}")
                    if question:
                        print(f"              question={question[:50]}...")
                
                if len(traces) < batch_limit:
                    print(f"    Last page reached (< {batch_limit} traces)")
                    break
                
                page += 1
                await asyncio.sleep(0.5)
                
            except Exception as e:
                print(f"[ERROR] {e}")
                break
    
    print(f"\n[3] Total traces fetched: {total_traces}")
    print(f"\n[4] Team statistics:")
    for team_name, stats in team_stats.items():
        print(f"    {team_name}: {stats['total_questions']} questions, " +
              f"{stats['active_members_count']} active members")
    
    # Calculate summary
    teams_list = list(team_stats.values())
    total_questions = sum(t["total_questions"] for t in teams_list)
    active_teams = sum(1 for t in teams_list if t["total_questions"] > 0)
    
    print(f"\n[5] Summary:")
    print(f"    Total teams: {len(TEAMS)}")
    print(f"    Total questions: {total_questions}")
    print(f"    Active teams: {active_teams}")
    print(f"    Response would have {len(teams_list)} teams")


if __name__ == "__main__":
    asyncio.run(simulate_endpoint())

