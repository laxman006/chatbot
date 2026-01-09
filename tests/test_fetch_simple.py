#!/usr/bin/env python
"""Simple test to verify the endpoint works"""

import httpx

def test_endpoint():
    """Test endpoint directly"""
    
    try:
        client = httpx.Client(timeout=60.0)
        
        print("Testing: http://127.0.0.1:8002/analytics/langfuse/teams/summary?time_filter=today")
        print("=" * 80)
        
        response = client.get(
            "http://127.0.0.1:8002/analytics/langfuse/teams/summary?time_filter=today"
        )
        
        print(f"Status: {response.status_code}")
        
        if response.status_code == 401:
            print("\n401 Unauthorized - Need valid auth token")
            print("Response:", response.text[:500])
            
        elif response.status_code == 200:
            data = response.json()
            print(f"\n✓ SUCCESS!")
            print(f"Total Questions: {data.get('total_questions')}")
            print(f"Total Teams: {data.get('total_teams')}")
            print(f"Active Teams: {data.get('total_active_teams')}")
            
            teams = data.get('teams', [])
            if teams:
                print(f"\nTop 3 Teams:")
                for team in teams[:3]:
                    print(f"  - {team['team_name']}: {team['total_questions']} questions")
        else:
            print(f"\n✗ HTTP {response.status_code}")
            print("Response:", response.text[:500])
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_endpoint()

