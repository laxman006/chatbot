#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for team analytics endpoints with auth token
"""

import httpx
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BASE_URL = "http://localhost:8002"

def test_endpoint_with_token(endpoint: str, token: str):
    """Test an endpoint with auth token"""
    print(f"\n{'='*60}")
    print(f"Testing: {endpoint}")
    print(f"{'='*60}")
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        }
        
        response = httpx.get(
            f"{BASE_URL}{endpoint}",
            headers=headers,
            timeout=30.0
        )
        
        print(f"[Status] {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"\n[Response]:")
                print(json.dumps(data, indent=2))
            except:
                print(f"[Response] {response.text[:500]}")
        elif response.status_code == 401:
            print(f"[ERROR] Unauthorized - need valid admin token")
        elif response.status_code == 403:
            print(f"[ERROR] Forbidden - not an admin")
        elif response.status_code == 404:
            print(f"[ERROR] Endpoint not found")
            print(f"[Response] {response.text}")
        else:
            print(f"[ERROR] HTTP {response.status_code}")
            print(f"[Response] {response.text[:500]}")
    
    except Exception as e:
        print(f"[EXCEPTION] {type(e).__name__}: {e}")

if __name__ == "__main__":
    # Get a test admin token from environment
    TEST_ADMIN_TOKEN = os.getenv('TEST_ADMIN_TOKEN', '')
    
    if not TEST_ADMIN_TOKEN:
        print("[ERROR] TEST_ADMIN_TOKEN not set in environment")
        print("Please set TEST_ADMIN_TOKEN in .env file or environment")
        exit(1)
    
    print("[INFO] Testing Team Analytics Endpoints")
    print(f"[INFO] Base URL: {BASE_URL}")
    print(f"[INFO] Token: {TEST_ADMIN_TOKEN[:20]}...")
    
    # Test 1: Check if backend is up
    try:
        response = httpx.get(f"{BASE_URL}/auth/config", timeout=5)
        print(f"\n[OK] Backend is running (status: {response.status_code})")
    except Exception as e:
        print(f"\n[CRITICAL] Backend not responding: {e}")
        exit(1)
    
    # Test 2: Teams summary endpoint
    test_endpoint_with_token("/analytics/langfuse/teams/summary?time_filter=today", TEST_ADMIN_TOKEN)
    
    # Test 3: Teams details endpoint
    test_endpoint_with_token("/analytics/langfuse/teams/details?team_name=Content&time_filter=today", TEST_ADMIN_TOKEN)
    
    print(f"\n{'='*60}")
    print("Test Complete")
    print(f"{'='*60}\n")

