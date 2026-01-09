#!/usr/bin/env python
"""Check the exact response from endpoint"""

import httpx

try:
    client = httpx.Client(timeout=60.0)
    
    response = client.get(
        "http://127.0.0.1:8002/analytics/langfuse/teams/summary?time_filter=today"
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
            
except Exception as e:
    print(f"Error: {e}")

