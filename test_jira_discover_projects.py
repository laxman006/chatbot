# -*- coding: utf-8 -*-
"""
Discover all available Jira projects and boards
"""

import os
import sys
from dotenv import load_dotenv
from jira import JIRA

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://cf2020.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

if __name__ == "__main__":
    print("=" * 80)
    print("JIRA PROJECT & BOARD DISCOVERY")
    print("=" * 80)
    print(f"Server: {JIRA_SERVER}")
    print(f"Email: {JIRA_EMAIL}")
    print("-" * 80)
    
    try:
        # Connect to Jira
        print("\n[*] Connecting to Jira...")
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        print(f"[OK] Connected as: {jira.current_user()}")
        
        # Get all projects
        print("\n" + "=" * 80)
        print("ALL PROJECTS")
        print("=" * 80)
        
        projects = jira.projects()
        print(f"\nFound {len(projects)} projects:\n")
        
        for project in projects:
            print(f"  Project Key: {project.key}")
            print(f"  Name: {project.name}")
            print(f"  Lead: {project.lead if hasattr(project, 'lead') else 'N/A'}")
            
            # Try to get ticket count for resolved/closed
            try:
                jql = f"project = {project.key} AND (status = Resolved OR status = Closed)"
                count_results = jira.search_issues(jql, maxResults=0)
                resolved_count = count_results.total
                print(f"  Resolved/Closed Tickets: {resolved_count}")
            except Exception as e:
                print(f"  Resolved/Closed Tickets: Error - {e}")
            
            print()
        
        # Get all boards
        print("\n" + "=" * 80)
        print("ALL BOARDS")
        print("=" * 80)
        
        try:
            boards = jira.boards()
            print(f"\nFound {len(boards)} boards:\n")
            
            for board in boards:
                print(f"  Board ID: {board.id}")
                print(f"  Name: {board.name}")
                print(f"  Type: {board.type}")
                
                # Try to get the project for this board
                try:
                    board_config = jira.board(board.id)
                    if hasattr(board_config, 'location') and hasattr(board_config.location, 'projectKey'):
                        print(f"  Project Key: {board_config.location.projectKey}")
                except:
                    pass
                
                print()
        except Exception as e:
            print(f"[WARNING] Could not fetch boards: {e}")
        
        # Search for QA-related projects
        print("\n" + "=" * 80)
        print("QA-RELATED PROJECTS")
        print("=" * 80)
        
        qa_projects = [p for p in projects if 'qa' in p.name.lower() or 'qa' in p.key.lower() or 'quality' in p.name.lower()]
        
        if qa_projects:
            print(f"\nFound {len(qa_projects)} QA-related projects:\n")
            for project in qa_projects:
                print(f"  Key: {project.key} | Name: {project.name}")
                
                # Get ticket counts
                try:
                    # All tickets
                    jql_all = f"project = {project.key}"
                    all_results = jira.search_issues(jql_all, maxResults=0)
                    all_count = all_results.total
                    
                    # Resolved/Closed tickets
                    jql_resolved = f"project = {project.key} AND (status = Resolved OR status = Closed)"
                    resolved_results = jira.search_issues(jql_resolved, maxResults=0)
                    resolved_count = resolved_results.total
                    
                    print(f"    Total Tickets: {all_count}")
                    print(f"    Resolved/Closed: {resolved_count}")
                    
                    # Get a sample ticket
                    if resolved_count > 0:
                        sample = jira.search_issues(jql_resolved, maxResults=1)
                        if sample:
                            print(f"    Sample Ticket: {sample[0].key} - {sample[0].fields.summary[:60]}...")
                except Exception as e:
                    print(f"    Error getting counts: {e}")
                
                print()
        else:
            print("\n[INFO] No QA-related projects found")
            print("Searching all projects for 'Quality' or 'QA' in the name...")
        
        print("\n" + "=" * 80)
        print("DISCOVERY COMPLETE")
        print("=" * 80)
        print("\nRecommendation:")
        print("  1. Check the project keys listed above")
        print("  2. Look for QA board project key")
        print("  3. Update JIRA_PROJECT_KEYS in .env with correct keys")
        print("=" * 80)
        
    except Exception as e:
        print(f"\n[ERROR] Discovery failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
