# -*- coding: utf-8 -*-
"""
Simple test to verify AI suggestions extraction from Jira ticket CFITS-2065
"""

import os
import sys
from dotenv import load_dotenv
from app.jira_processor import JiraProcessor

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def test_ai_suggestions():
    """Test extracting AI suggestions from ticket CFITS-2065."""
    
    print("=" * 60)
    print("TESTING AI SUGGESTIONS EXTRACTION")
    print("=" * 60)
    
    try:
        processor = JiraProcessor()
        
        # Fetch the specific ticket
        ticket_key = "CFITS-2065"
        print(f"\n[*] Fetching ticket {ticket_key}...")
        
        issue = processor.jira.issue(ticket_key, expand='comments')
        ticket_data = processor._extract_ticket_data(issue)
        
        if ticket_data:
            print(f"\n[OK] Successfully extracted ticket data")
            print(f"  Ticket: {ticket_data['key']}")
            print(f"  Summary: {ticket_data['summary']}")
            print(f"  Comments: {len(ticket_data.get('comments', []))}")
            print(f"  AI Suggestions: {bool(ticket_data.get('ai_suggestions'))}")
            
            if ticket_data.get('ai_suggestions'):
                suggestions = ticket_data['ai_suggestions']
                print(f"\n[SUCCESS] Found AI Suggestions!")
                print(f"  Summary: {suggestions.get('summary', 'N/A')}")
                print(f"  Step Count: {suggestions.get('step_count', 0)}")
                print(f"\n  Solution Steps:")
                for idx, step in enumerate(suggestions.get('solution_steps', []), 1):
                    print(f"    {idx}. {step[:100]}...")
            else:
                print("\n[INFO] No AI suggestions found in this ticket")
                print("  Note: AI suggestions may appear as comments later")
                print("  The system will automatically detect them when they're added")
            
            # Test document formatting
            print(f"\n[*] Testing document formatting...")
            doc = processor.format_ticket_document(ticket_data)
            print(f"[OK] Document created")
            print(f"  Content length: {len(doc.page_content)} characters")
            print(f"  Has AI suggestions in metadata: {doc.metadata.get('has_ai_suggestions', False)}")
            print(f"  AI solution steps count: {doc.metadata.get('ai_solution_steps', 0)}")
            
            # Show preview of content
            print(f"\n[*] Document content preview:")
            print("-" * 60)
            preview_lines = doc.page_content.split('\n')[:30]
            for line in preview_lines:
                print(line)
            if len(doc.page_content.split('\n')) > 30:
                print("... (truncated)")
            print("-" * 60)
            
        else:
            print(f"\n[WARNING] Could not extract ticket data")
            print("  This might be because:")
            print("  - Ticket has no description")
            print("  - Ticket has no comments or AI suggestions")
        
        print("\n" + "=" * 60)
        print("TEST COMPLETE")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[ERROR] Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_ai_suggestions()
