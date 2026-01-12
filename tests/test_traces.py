#!/usr/bin/env python
"""Test script to verify Langfuse traces and their structure"""

import httpx
from datetime import datetime, timedelta
from config import LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST

def inspect_traces():
    """Fetch and inspect traces from Langfuse"""
    
    print("=" * 60)
    print("LANGFUSE TRACES INSPECTION")
    print("=" * 60)
    
    try:
        client = httpx.Client()
        
        # Fetch recent traces
        params = {
            "page": 1,
            "limit": 10,
            "orderBy[createdAt]": "DESC"
        }
        
        response = client.get(
            f"{LANGFUSE_HOST}/api/public/traces",
            params=params,
            auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
            timeout=30.0
        )
        
        if response.status_code != 200:
            print(f"[ERROR] API returned status {response.status_code}")
            print(f"Response: {response.text}")
            return
        
        traces_data = response.json()
        traces = traces_data.get("data", [])
        
        print(f"\n[INFO] Found {len(traces)} traces\n")
        
        if not traces:
            print("[WARN] No traces found")
            return
        
        # Inspect first few traces
        for i, trace in enumerate(traces[:3], 1):
            print(f"\n--- TRACE {i} ---")
            print(f"ID: {trace.get('id')}")
            print(f"User ID: {trace.get('userId')}")
            print(f"Session ID: {trace.get('sessionId')}")
            print(f"Name: {trace.get('name')}")
            print(f"Input: {str(trace.get('input', ''))[:100]}...")
            print(f"Output: {str(trace.get('output', ''))[:100]}...")
            
            metadata = trace.get("metadata", {})
            print(f"\nMetadata:")
            for key, value in metadata.items():
                print(f"  {key}: {value} (type: {type(value).__name__})")
            
            # Check for user_email
            user_email = metadata.get("user_email")
            user_name = metadata.get("user_name")
            print(f"\nEmail Field: {user_email} (type: {type(user_email).__name__})")
            print(f"Name Field: {user_name} (type: {type(user_name).__name__})")
            
            # Test email matching
            if user_email:
                from app.models.teams import get_team_by_member_email
                email_str = str(user_email) if isinstance(user_email, list) else user_email
                team = get_team_by_member_email(email_str)
                print(f"\nMatched Team: {team}")
        
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total traces fetched: {len(traces)}")
        print(f"Sample size analyzed: {min(3, len(traces))}")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
    finally:
        client.close()

if __name__ == "__main__":
    inspect_traces()

