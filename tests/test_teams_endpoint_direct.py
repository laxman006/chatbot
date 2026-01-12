#!/usr/bin/env python
"""Direct test of teams endpoint logic without auth"""

import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from collections import Counter
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
from app.models.teams import get_all_teams, get_team_by_member_email, get_team_color

async def test_teams_logic():
    """Test the teams analytics logic directly"""
    
    print("=" * 80)
    print("TESTING TEAMS ANALYTICS LOGIC")
    print("=" * 80)
    
    # Test with different time filters
    time_filters = ["today", "yesterday", "this_week", "last_week", "this_month", "all"]
    
    for time_filter in time_filters:
        print(f"\n{'=' * 80}")
        print(f"Testing: {time_filter.upper()}")
        print(f"{'=' * 80}\n")
        
        # Calculate date range
        now = datetime.now(timezone.utc)
        start_time = None
        end_time = None
        
        if time_filter == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "yesterday":
            yesterday = now - timedelta(days=1)
            start_time = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif time_filter == "this_week":
            start_time = now - timedelta(days=now.weekday())
            start_time = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        elif time_filter == "last_week":
            start_time = now - timedelta(days=7)
            end_time = now
        elif time_filter == "this_month":
            start_time = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end_time = now
        
        print(f"Date range: {start_time} to {end_time}" if start_time else "All time")
        
        # Initialize team data
        teams_data = {}
        all_teams = get_all_teams()
        
        for team_name, team_info in all_teams.items():
            teams_data[team_name] = {
                "team_name": team_name,
                "lead": team_info.get("lead"),
                "lead_email": team_info.get("lead_email"),
                "member_count": len(team_info.get("members", [])) + (1 if team_info.get("lead_email") else 0),
                "total_questions": 0,
                "unique_questions": 0,
                "active_members": set(),
                "questions_list": []
            }
        
        # Fetch traces
        page = 1
        batch_limit = 100
        max_pages = 5 if time_filter in ["today", "yesterday"] else (10 if time_filter != "all" else 20)
        total_traces = 0
        traces_by_team = {}
        
        async with httpx.AsyncClient() as client:
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
                        timeout=45.0
                    )
                    
                    if response.status_code == 429:
                        print(f"Rate limited at page {page}")
                        break
                    
                    if response.status_code != 200:
                        print(f"Error: HTTP {response.status_code}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        print(f"No more traces at page {page}")
                        break
                    
                    total_traces += len(traces)
                    
                    for trace in traces:
                        metadata = trace.get("metadata", {})
                        question = trace.get("input", "")
                        user_email = str(metadata.get("user_email", "")).lower()
                        
                        if not user_email or not user_email.strip():
                            continue
                        
                        team_name = get_team_by_member_email(user_email)
                        
                        if team_name and team_name != "Unassigned" and question:
                            if team_name in teams_data:
                                teams_data[team_name]["total_questions"] += 1
                                teams_data[team_name]["questions_list"].append(question)
                                teams_data[team_name]["active_members"].add(user_email)
                                
                                if team_name not in traces_by_team:
                                    traces_by_team[team_name] = []
                                traces_by_team[team_name].append({
                                    "user": user_email,
                                    "question": question[:60] + "..." if len(question) > 60 else question
                                })
                    
                    if len(traces) < batch_limit:
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)  # Rate limiting
                    
                except Exception as e:
                    print(f"Error at page {page}: {e}")
                    break
        
        print(f"\nFetched {total_traces} total traces")
        print(f"Teams with data: {len(traces_by_team)}")
        
        # Calculate stats
        result_teams = []
        for team_name, stats in teams_data.items():
            stats["active_members_count"] = len(stats["active_members"])
            
            question_counts = Counter(stats["questions_list"])
            stats["top_questions"] = sorted(
                [{"question": q, "count": c} for q, c in question_counts.items()],
                key=lambda x: x["count"],
                reverse=True
            )[:3]
            
            stats["unique_questions"] = len(question_counts)
            
            del stats["questions_list"]
            del stats["active_members"]
            
            result_teams.append(stats)
        
        result_teams.sort(key=lambda x: x["total_questions"], reverse=True)
        
        print(f"\nTop 5 Teams:")
        print(f"{'Team':<20} {'Q':<5} {'Unique':<10} {'Active':<10}")
        print("-" * 50)
        for team in result_teams[:5]:
            print(f"{team['team_name']:<20} {team['total_questions']:<5} {team['unique_questions']:<10} {team['active_members_count']:<10}")
        
        total_questions = sum(t["total_questions"] for t in result_teams)
        print(f"\nTotal questions across all teams: {total_questions}")
        
        # Show sample traces for teams
        if traces_by_team:
            print(f"\nSample traces from teams:")
            for team_name in list(traces_by_team.keys())[:3]:
                traces = traces_by_team[team_name][:2]
                print(f"\n{team_name}:")
                for t in traces:
                    print(f"  - {t['user']}: {t['question']}")


if __name__ == "__main__":
    asyncio.run(test_teams_logic())

