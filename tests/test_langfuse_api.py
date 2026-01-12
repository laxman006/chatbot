#!/usr/bin/env python3
"""
Test script to verify Langfuse API connectivity and data retrieval.
Tests the analytics endpoints before using in production.
"""

import asyncio
import httpx
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get Langfuse credentials
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY")
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    """Print a section header"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.RESET}\n")

def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}[OK] {text}{Colors.RESET}")

def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}[ERROR] {text}{Colors.RESET}")

def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}[WARNING] {text}{Colors.RESET}")

def print_info(text):
    """Print info message"""
    print(f"{Colors.CYAN}[INFO] {text}{Colors.RESET}")

def check_credentials():
    """Check if Langfuse credentials are set"""
    print_header("1. Checking Langfuse Credentials")
    
    if not LANGFUSE_PUBLIC_KEY:
        print_error("LANGFUSE_PUBLIC_KEY not set in .env")
        return False
    
    if not LANGFUSE_SECRET_KEY:
        print_error("LANGFUSE_SECRET_KEY not set in .env")
        return False
    
    print_success(f"Public Key: {LANGFUSE_PUBLIC_KEY[:10]}...")
    print_success(f"Secret Key: {LANGFUSE_SECRET_KEY[:10]}...")
    print_success(f"Host: {LANGFUSE_HOST}")
    
    return True

async def test_api_connection():
    """Test basic API connection"""
    print_header("2. Testing API Connection")
    
    try:
        async with httpx.AsyncClient() as client:
            # Test with a simple request
            response = await client.get(
                f"{LANGFUSE_HOST}/api/public/traces",
                params={
                    "page": 1,
                    "limit": 1
                },
                auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                timeout=30.0
            )
            
            if response.status_code == 200:
                print_success(f"API Connection successful (Status: {response.status_code})")
                return True
            elif response.status_code == 401:
                print_error(f"Authentication failed (Status: {response.status_code})")
                print_error("Check your Langfuse credentials")
                return False
            elif response.status_code == 429:
                print_warning(f"Rate limited (Status: {response.status_code})")
                return True  # API works, but rate limited
            else:
                print_error(f"API Error (Status: {response.status_code})")
                print_error(f"Response: {response.text}")
                return False
                
    except Exception as e:
        print_error(f"Connection failed: {e}")
        return False

async def test_fetch_traces():
    """Test fetching traces from Langfuse"""
    print_header("3. Fetching Traces (First 3 Pages)")
    
    try:
        all_traces = []
        page_count = 0
        
        async with httpx.AsyncClient() as client:
            for page in range(1, 4):  # Fetch first 3 pages
                try:
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params={
                            "page": page,
                            "limit": 100
                        },
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=30.0
                    )
                    
                    if response.status_code == 429:
                        print_warning(f"Rate limited at page {page}, stopping")
                        break
                    
                    if response.status_code != 200:
                        print_error(f"Page {page} failed: {response.status_code}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        print_info(f"Page {page}: No traces found")
                        break
                    
                    all_traces.extend(traces)
                    page_count += 1
                    print_success(f"Page {page}: {len(traces)} traces fetched")
                    
                    # Rate limiting delay
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print_error(f"Error fetching page {page}: {e}")
                    break
        
        print_success(f"\nTotal: {len(all_traces)} traces fetched across {page_count} pages")
        return all_traces
        
    except Exception as e:
        print_error(f"Failed to fetch traces: {e}")
        return []

async def test_aggregate_data(traces):
    """Test data aggregation"""
    print_header("4. Testing Data Aggregation")
    
    if not traces:
        print_warning("No traces to aggregate")
        return
    
    try:
        users_activity = defaultdict(lambda: {"count": 0, "email": "", "name": ""})
        all_questions = []
        
        for trace in traces:
            user_id = trace.get("userId")
            metadata = trace.get("metadata", {})
            question = trace.get("input", "")
            
            if user_id:
                users_activity[user_id]["count"] += 1
                
                # Safely extract email
                user_email = metadata.get("user_email", "N/A")
                if isinstance(user_email, list):
                    user_email = user_email[0] if user_email else "N/A"
                users_activity[user_id]["email"] = str(user_email)
                
                # Safely extract name
                user_name = metadata.get("user_name", "Unknown")
                if isinstance(user_name, list):
                    user_name = user_name[0] if user_name else "Unknown"
                users_activity[user_id]["name"] = str(user_name)
            
            if question:
                all_questions.append(str(question))
        
        # Get statistics
        total_users = len(users_activity)
        total_questions = len(all_questions)
        unique_questions = len(set(all_questions))
        
        print_success(f"Total Users: {total_users}")
        print_success(f"Total Questions: {total_questions}")
        print_success(f"Unique Questions: {unique_questions}")
        
        if total_users > 0:
            avg = round(total_questions / total_users, 2)
            print_success(f"Avg Questions/User: {avg}")
        
        # Get most active users
        most_active = sorted(
            users_activity.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:5]
        
        print_info("\nTop 5 Most Active Users:")
        for i, (user_id, user_info) in enumerate(most_active, 1):
            print(f"  {i}. {user_info['email']} ({user_info['name']}) - {user_info['count']} questions")
        
        # Get top questions
        try:
            question_counter = Counter(all_questions)
            top_questions = question_counter.most_common(5)
            
            print_info("\nTop 5 Questions:")
            for i, (question, count) in enumerate(top_questions, 1):
                print(f"  {i}. [{count}x] {question[:60]}...")
                
        except Exception as e:
            print_error(f"Error counting questions: {e}")
        
        return {
            "total_users": total_users,
            "total_questions": total_questions,
            "unique_questions": unique_questions,
            "most_active": most_active,
            "top_questions": top_questions if 'top_questions' in locals() else []
        }
        
    except Exception as e:
        print_error(f"Aggregation failed: {e}")
        return None

async def test_dashboard_summary():
    """Test the full dashboard summary flow"""
    print_header("5. Testing Full Dashboard Summary Flow")
    
    try:
        users_activity = defaultdict(lambda: {"count": 0, "email": "", "name": ""})
        all_questions = []
        page = 1
        max_pages = 30
        total_fetched = 0
        
        async with httpx.AsyncClient() as client:
            while page <= max_pages:
                try:
                    response = await client.get(
                        f"{LANGFUSE_HOST}/api/public/traces",
                        params={
                            "page": page,
                            "limit": 100
                        },
                        auth=(LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY),
                        timeout=60.0
                    )
                    
                    if response.status_code == 429:
                        print_warning(f"Rate limited at page {page}")
                        break
                    
                    if response.status_code != 200:
                        print_error(f"Error at page {page}: {response.status_code}")
                        break
                    
                    traces_response = response.json()
                    traces = traces_response.get("data", [])
                    
                    if not traces:
                        print_info(f"Reached end of data at page {page}")
                        break
                    
                    for trace in traces:
                        user_id = trace.get("userId")
                        metadata = trace.get("metadata", {})
                        question = trace.get("input", "")
                        
                        if user_id:
                            users_activity[user_id]["count"] += 1
                            
                            user_email = metadata.get("user_email", "N/A")
                            if isinstance(user_email, list):
                                user_email = user_email[0] if user_email else "N/A"
                            users_activity[user_id]["email"] = str(user_email)
                            
                            user_name = metadata.get("user_name", "Unknown")
                            if isinstance(user_name, list):
                                user_name = user_name[0] if user_name else "Unknown"
                            users_activity[user_id]["name"] = str(user_name)
                        
                        if question:
                            all_questions.append(str(question))
                    
                    total_fetched += len(traces)
                    print_info(f"Page {page}: {len(traces)} traces (Total: {total_fetched})")
                    
                    if len(traces) < 100:
                        print_info("Reached end of data")
                        break
                    
                    page += 1
                    await asyncio.sleep(0.5)
                    
                except Exception as e:
                    print_error(f"Error processing page {page}: {e}")
                    break
        
        # Calculate summary
        most_active = sorted(
            users_activity.items(),
            key=lambda x: x[1]["count"],
            reverse=True
        )[:10]
        
        try:
            question_counter = Counter(all_questions)
            top_questions = question_counter.most_common(5)
        except Exception as e:
            print_error(f"Counter error: {e}")
            top_questions = []
        
        print_success(f"\nDashboard Summary Complete!")
        print_success(f"  - Total Users: {len(users_activity)}")
        print_success(f"  - Total Questions: {len(all_questions)}")
        print_success(f"  - Unique Questions: {len(set(all_questions))}")
        print_success(f"  - Pages Fetched: {page - 1}")
        
        return {
            "status": "success",
            "summary": {
                "total_users": len(users_activity),
                "total_questions": len(all_questions),
                "unique_questions": len(set(all_questions)),
                "pages_fetched": page - 1
            },
            "most_active_users": [
                {
                    "user_id": user[0],
                    "email": user[1]["email"],
                    "name": user[1]["name"],
                    "questions_asked": user[1]["count"]
                }
                for user in most_active
            ],
            "top_questions": [
                {
                    "question": q[0],
                    "times_asked": q[1]
                }
                for q in top_questions
            ]
        }
        
    except Exception as e:
        print_error(f"Dashboard summary test failed: {e}")
        return {"status": "error", "error": str(e)}

async def main():
    """Run all tests"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}")
    print("=" * 60)
    print("LANGFUSE API TEST SUITE")
    print("Testing analytics endpoint connectivity")
    print("=" * 60)
    print(f"{Colors.RESET}")
    
    start_time = datetime.now()
    
    # Test 1: Check credentials
    if not check_credentials():
        print_error("\nCredential check failed. Cannot continue.")
        return
    
    # Test 2: Test API connection
    connected = await test_api_connection()
    if not connected:
        print_error("\nAPI connection failed. Cannot continue.")
        return
    
    # Test 3: Fetch traces
    traces = await test_fetch_traces()
    
    # Test 4: Aggregate data
    if traces:
        await test_aggregate_data(traces)
    
    # Test 5: Full dashboard flow
    result = await test_dashboard_summary()
    
    # Print final result
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    
    print_header("Test Summary")
    
    if result and result.get("status") == "success":
        print_success(f"All tests passed!")
        print_success(f"Total duration: {duration:.2f} seconds")
        print_success(f"Users found: {result['summary']['total_users']}")
        print_success(f"Questions found: {result['summary']['total_questions']}")
        
        # Print JSON result
        print_info("\nJSON Response (for debugging):")
        print(json.dumps(result, indent=2))
    else:
        print_error("Tests failed or incomplete")
        if result and "error" in result:
            print_error(f"Error: {result['error']}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print_warning("\n\nTest interrupted by user")
    except Exception as e:
        print_error(f"\nUnexpected error: {e}")

