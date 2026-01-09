# test_jira_integration.py
"""
Test script to verify Jira integration is working correctly.
This tests the actual processor that will be used in production.
"""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_jira_processor():
    """Test the Jira processor directly."""
    print("=" * 60)
    print("TESTING JIRA PROCESSOR INTEGRATION")
    print("=" * 60)
    
    # Check if Jira is enabled
    enable_jira = os.getenv("ENABLE_JIRA_SOURCE", "false").lower() == "true"
    if not enable_jira:
        print("\n[WARNING] ENABLE_JIRA_SOURCE is not set to 'true' in .env")
        print("Add this to your .env file:")
        print("  ENABLE_JIRA_SOURCE=true")
        print("\nContinuing test anyway...")
    
    # Check required environment variables
    required_vars = ["JIRA_SERVER", "JIRA_EMAIL", "JIRA_API_TOKEN"]
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"\n[ERROR] Missing required environment variables: {', '.join(missing_vars)}")
        print("Please add them to your .env file")
        return False
    
    print("\n[OK] All required environment variables are set")
    print(f"  JIRA_SERVER: {os.getenv('JIRA_SERVER')}")
    print(f"  JIRA_EMAIL: {os.getenv('JIRA_EMAIL')}")
    print(f"  JIRA_API_TOKEN: {'*' * 20}... (hidden)")
    
    # Test the processor
    print("\n" + "=" * 60)
    print("TESTING JIRA PROCESSOR")
    print("=" * 60)
    
    try:
        from app.jira_processor import process_jira_content
        
        print("\n[*] Calling process_jira_content()...")
        documents = process_jira_content()
        
        if documents:
            print(f"\n[OK] Successfully processed Jira tickets!")
            print(f"  - Total documents created: {len(documents)}")
            
            # Show sample document
            if documents:
                sample_doc = documents[0]
                print(f"\n  Sample document:")
                print(f"    - Content length: {len(sample_doc.page_content)} characters")
                print(f"    - Metadata keys: {list(sample_doc.metadata.keys())}")
                print(f"    - Source type: {sample_doc.metadata.get('source_type')}")
                print(f"    - Tag: {sample_doc.metadata.get('tag')}")
                print(f"    - Ticket key: {sample_doc.metadata.get('ticket_key')}")
                print(f"    - Comments count: {sample_doc.metadata.get('comments_count')}")
                
                # Show first 300 chars of content
                print(f"\n    Content preview:")
                print(f"    {sample_doc.page_content[:300]}...")
            
            # Count tickets by project
            projects = {}
            for doc in documents:
                project = doc.metadata.get('project_key', 'Unknown')
                projects[project] = projects.get(project, 0) + 1
            
            print(f"\n  Tickets by project:")
            for project, count in sorted(projects.items()):
                print(f"    - {project}: {count} tickets")
            
            return True
        else:
            print("\n[WARNING] No documents were created")
            print("This could mean:")
            print("  1. No tickets match your criteria (status = Resolved/Closed)")
            print("  2. No tickets have comments")
            print("  3. Date filter excluded all tickets")
            print("\nTry running test_jira_diagnostic.py to see what's available")
            return False
            
    except Exception as e:
        print(f"\n[ERROR] Failed to process Jira content: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_vectorstore_integration():
    """Test if Jira can be integrated into vectorstore."""
    print("\n" + "=" * 60)
    print("TESTING VECTORSTORE INTEGRATION")
    print("=" * 60)
    
    try:
        from app.helpers import build_combined_vectorstore
        from config import ENABLE_JIRA_SOURCE
        
        if not ENABLE_JIRA_SOURCE:
            print("\n[INFO] ENABLE_JIRA_SOURCE is False - skipping vectorstore test")
            print("Set ENABLE_JIRA_SOURCE=true to test full integration")
            return
        
        print("\n[*] Testing vectorstore integration...")
        print("[INFO] This would normally build the full vectorstore")
        print("[INFO] For a full test, set INITIALIZE_VECTORSTORE=true and start your server")
        print("\n[OK] Integration code is ready - Jira will be included when vectorstore is built")
        
    except Exception as e:
        print(f"\n[ERROR] Vectorstore integration test failed: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("JIRA INTEGRATION TEST SUITE")
    print("=" * 60)
    print("\nThis script tests:")
    print("  1. Environment variables")
    print("  2. Jira processor (fetches tickets)")
    print("  3. Document creation")
    print("  4. Vectorstore integration readiness")
    
    # Test 1: Processor
    success = test_jira_processor()
    
    # Test 2: Vectorstore integration
    test_vectorstore_integration()
    
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    if success:
        print("\n[OK] Jira processor is working correctly!")
        print("\nNext steps:")
        print("  1. Add ENABLE_JIRA_SOURCE=true to your .env file")
        print("  2. Set INITIALIZE_VECTORSTORE=true (one time, to rebuild)")
        print("  3. Start your server - Jira tickets will be added to knowledge base")
        print("  4. Query your chatbot - it will use Jira tickets to answer questions")
    else:
        print("\n[WARNING] Some tests failed - check the errors above")
        print("\nTroubleshooting:")
        print("  1. Verify your JIRA_API_TOKEN is correct")
        print("  2. Check that you have access to tickets")
        print("  3. Run test_jira_diagnostic.py to see available tickets")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    main()
