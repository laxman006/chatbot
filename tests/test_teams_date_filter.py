#!/usr/bin/env python
"""Test teams endpoint with date filtering"""

import httpx
import json
from datetime import datetime, timedelta

def test_teams_endpoint():
    """Test the /analytics/langfuse/teams/summary endpoint"""
    
    print("=" * 80)
    print("TESTING TEAMS SUMMARY ENDPOINT WITH DATE FILTERING")
    print("=" * 80)
    
    base_url = "http://localhost:8000"
    
    try:
        # Test different date ranges
        test_cases = [
            {
                "name": "Last 30 days (Nov 16 - Dec 16)",
                "params": {
                    "start_date": "2025-11-16",
                    "end_date": "2025-12-16"
                }
            },
            {
                "name": "Last 7 days",
                "params": {
                    "start_date": "2025-12-09",
                    "end_date": "2025-12-16"
                }
            },
            {
                "name": "Today only",
                "params": {
                    "time_filter": "today"
                }
            },
            {
                "name": "All time",
                "params": {
                    "time_filter": "all"
                }
            }
        ]
        
        for test_case in test_cases:
            print(f"\n{'=' * 80}")
            print(f"TEST: {test_case['name']}")
            print(f"Parameters: {test_case['params']}")
            print(f"{'=' * 80}\n")
            
            client = httpx.Client(timeout=60.0)
            
            try:
                response = client.get(
                    f"{base_url}/analytics/langfuse/teams/summary",
                    params=test_case['params'],
                    headers={"Authorization": "Bearer dummy_token"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"[SUCCESS] Status: {data.get('status')}")
                    print(f"Total Teams: {data.get('total_teams')}")
                    print(f"Total Questions: {data.get('total_questions')}")
                    print(f"Total Unique Questions: {data.get('total_unique_questions_overall')}")
                    print(f"Active Teams: {data.get('total_active_teams')}\n")
                    
                    teams = data.get('teams', [])
                    if teams:
                        print("Top 10 Teams by Questions:")
                        print(f"{'#':<3} {'Team':<20} {'Total Q':<10} {'Unique':<10} {'Active Mbrs':<15}")
                        print("-" * 70)
                        for i, team in enumerate(teams[:10], 1):
                            print(f"{i:<3} {team['team_name']:<20} {team['total_questions']:<10} {team['unique_questions']:<10} {team['active_members_count']}/{team['member_count']:<13}")
                    else:
                        print("No teams with data found!")
                
                elif response.status_code == 401:
                    print("[ERROR] 401 Unauthorized - Need valid auth token")
                    print("Trying without auth header...")
                    
                    response = client.get(
                        f"{base_url}/analytics/langfuse/teams/summary",
                        params=test_case['params']
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        print(f"[SUCCESS] Total Questions: {data.get('total_questions')}")
                    else:
                        print(f"[ERROR] HTTP {response.status_code}: {response.text[:200]}")
                
                else:
                    print(f"[ERROR] HTTP {response.status_code}")
                    print(f"Response: {response.text[:300]}")
                    
            except Exception as e:
                print(f"[ERROR] Request failed: {e}")
            
            finally:
                client.close()
        
        # Direct Langfuse API test
        print(f"\n{'=' * 80}")
        print("TESTING LANGFUSE API DIRECTLY")
        print(f"{'=' * 80}\n")
        
        from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST
        
        client = httpx.Client(timeout=60.0)
        
        start_date = "2025-11-16"
        end_date = "2025-12-16"
        
        params = {
            "page": 1,
            "limit": 100,
            "orderBy[createdAt]": "DESC",
            f"createdAt[gte]": f"{start_date}T00:00:00Z",
            f"createdAt[lte]": f"{end_date}T23:59:59Z"
        }
        
        print(f"Fetching from: {LANGFUSE_HOST}/api/public/traces")
        print(f"Date range: {start_date} to {end_date}\n")
        
        response = client.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            params=params,
            auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
            timeout=60.0
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            traces = data.get('data', [])
            print(f"Traces fetched: {len(traces)}")
            
            if traces:
                print(f"\nFirst 5 traces:")
                for i, trace in enumerate(traces[:5], 1):
                    metadata = trace.get('metadata', {})
                    user_email = metadata.get('user_email', 'Unknown')
                    question = trace.get('input', '')[:50]
                    print(f"  {i}. User: {user_email}, Q: {question}...")
        else:
            print(f"Error: {response.text}")
        
        client.close()
        
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_teams_endpoint()

