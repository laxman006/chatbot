#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script for team analytics endpoints
"""

import httpx
import json

BASE_URL = "http://localhost:8002"

def test_endpoint(endpoint: str, headers: dict = None):
    """Test an endpoint"""
    print(f"\n{'='*60}")
    print(f"Testing: {endpoint}")
    print('='*60)
    
    try:
        response = httpx.get(
            f"{BASE_URL}{endpoint}",
            headers=headers or {},
            timeout=30.0
        )
        
        print(f"[Status] {response.status_code}")
        
        if response.status_code == 200:
            try:
                data = response.json()
                print(f"[Response] {json.dumps(data, indent=2)[:500]}...")  # Show first 500 chars
            except:
                print(f"[Response] {response.text[:200]}")
        elif response.status_code == 401:
            print(f"[ERROR] Unauthorized - need valid admin token")
        elif response.status_code == 404:
            print(f"[ERROR] Endpoint not found")
            print(f"[Response] {response.text}")
        else:
            print(f"[ERROR] {response.text[:200]}")
    
    except Exception as e:
        print(f"[EXCEPTION] {type(e).__name__}: {e}")

if __name__ == "__main__":
    print("[INFO] Testing Team Analytics Endpoints")
    print(f"[INFO] Base URL: {BASE_URL}")
    
    # Test 1: Check if backend is up
    try:
        response = httpx.get(f"{BASE_URL}/auth/config", timeout=5)
        print(f"\n[OK] Backend is running (status: {response.status_code})")
    except Exception as e:
        print(f"\n[CRITICAL] Backend not responding: {e}")
        exit(1)
    
    # Test 2: Teams summary endpoint (without auth)
    test_endpoint("/analytics/langfuse/teams/summary?time_filter=today")
    
    # Test 3: Teams details endpoint (without auth)
    test_endpoint("/analytics/langfuse/teams/details?team_name=Content&time_filter=today")
    
    print(f"\n{'='*60}")
    print("Test Complete")
    print(f"{'='*60}\n")

