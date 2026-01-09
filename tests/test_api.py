"""Quick test script to verify the API is working"""
import requests
import json

print("🧪 Testing Suggested Questions API...\n")

try:
    response = requests.get("http://localhost:8002/api/suggested-questions?limit=4")
    
    if response.status_code == 200:
        questions = response.json()
        print(f"✅ API Working! Got {len(questions)} questions:\n")
        for i, q in enumerate(questions, 1):
            print(f"{i}. {q['question_text']}")
            print(f"   Category: {q['category']} | Priority: {q['priority']}\n")
    else:
        print(f"❌ API Error: {response.status_code}")
        print(response.text)
        
except requests.exceptions.ConnectionError:
    print("❌ Cannot connect to server. Is it running on port 8002?")
except Exception as e:
    print(f"❌ Error: {e}")

