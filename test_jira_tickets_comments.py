# test_jira_tickets_comments.py
"""
Test script to fetch Jira tickets with comments (customer queries + developer solutions).
This will show you exactly what data structure you'll get for the knowledge base.
"""

import os
from dotenv import load_dotenv
from jira import JIRA
from typing import List, Dict, Any
import json
from datetime import datetime
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

JIRA_SERVER = os.getenv("JIRA_SERVER", "https://cf2020.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "laxman.kadari@cloudfuze.com")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")

def clean_html(text: str) -> str:
    """Clean HTML tags from text."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return soup.get_text(separator="\n", strip=True)

def fetch_tickets_with_comments(jira: JIRA, project_key: str = None, max_results: int = 10, status_filter: str = None):
    """
    Fetch tickets with comments - focusing on customer queries and developer solutions.
    
    Args:
        jira: JIRA instance
        project_key: Specific project key (None for all projects)
        max_results: Maximum number of tickets to fetch
        status_filter: Filter by status (e.g., "Resolved", "Done", "Closed")
    """
    print("=" * 60)
    print("FETCHING TICKETS WITH COMMENTS")
    print("=" * 60)
    
    # Build JQL query
    jql_parts = []
    
    if project_key:
        jql_parts.append(f"project = {project_key}")
    
    # Filter by status if specified
    if status_filter:
        jql_parts.append(f"status = {status_filter}")
    else:
        # Default: Get resolved/closed tickets (solved issues)
        jql_parts.append("(status = Resolved OR status = Closed)")
    
    # Note: commentCount may not work in JQL, so we'll filter in Python
    # jql_parts.append("commentCount > 0")  # Commented out - filter in Python instead
    
    # Order by most recently updated
    jql = " AND ".join(jql_parts) + " ORDER BY updated DESC"
    
    print(f"\nJQL Query: {jql}")
    print(f"Fetching up to {max_results} tickets...")
    
    try:
        # Fetch issues with comments expanded
        # Fetch more than needed since we'll filter for comments
        issues = jira.search_issues(jql, maxResults=max_results * 3, expand='changelog,renderedFields,comments')
        
        print(f"\nFound {len(issues)} tickets (filtering for comments)...")
        
        tickets_data = []
        
        for issue in issues:
            # Extract ticket information
            ticket_data = {
                "key": issue.key,
                "summary": issue.fields.summary,
                "description": clean_html(str(issue.fields.description)) if hasattr(issue.fields, 'description') and issue.fields.description else "",
                "status": str(issue.fields.status),
                "issue_type": str(issue.fields.issuetype),
                "priority": str(issue.fields.priority) if hasattr(issue.fields, 'priority') else "N/A",
                "assignee": str(issue.fields.assignee) if issue.fields.assignee else "Unassigned",
                "reporter": str(issue.fields.reporter) if issue.fields.reporter else "Unknown",
                "created": str(issue.fields.created),
                "updated": str(issue.fields.updated),
                "resolved": str(issue.fields.resolutiondate) if hasattr(issue.fields, 'resolutiondate') and issue.fields.resolutiondate else None,
                "url": f"{JIRA_SERVER}/browse/{issue.key}",
                "comments": []
            }
            
            # Extract comments (developer solutions/responses)
            if hasattr(issue.fields, 'comment') and issue.fields.comment:
                for comment in issue.fields.comment.comments:
                    comment_data = {
                        "author": str(comment.author),
                        "body": clean_html(str(comment.body)),
                        "created": str(comment.created),
                        "updated": str(comment.updated) if hasattr(comment, 'updated') else None
                    }
                    ticket_data["comments"].append(comment_data)
            
            # Only add tickets that have comments
            if ticket_data["comments"]:
                tickets_data.append(ticket_data)
                if len(tickets_data) >= max_results:
                    break
            
            # Print summary
            print(f"\n{'='*60}")
            print(f"Ticket: {ticket_data['key']}")
            print(f"Summary: {ticket_data['summary']}")
            print(f"Status: {ticket_data['status']}")
            print(f"Reporter: {ticket_data['reporter']} (Customer)")
            print(f"Assignee: {ticket_data['assignee']} (Developer)")
            print(f"Comments: {len(ticket_data['comments'])}")
            print(f"\nDescription (Customer Query):")
            print(f"  {ticket_data['description'][:300]}..." if len(ticket_data['description']) > 300 else f"  {ticket_data['description']}")
            
            if ticket_data['comments']:
                print(f"\nComments (Developer Solutions):")
                for idx, comment in enumerate(ticket_data['comments'][:3], 1):  # Show first 3 comments
                    print(f"\n  Comment {idx} by {comment['author']} ({comment['created'][:10]}):")
                    print(f"  {comment['body'][:200]}..." if len(comment['body']) > 200 else f"  {comment['body']}")
        
        return tickets_data
        
    except Exception as e:
        print(f"[ERROR] Failed to fetch tickets: {e}")
        import traceback
        traceback.print_exc()
        return []

def format_ticket_for_knowledge_base(ticket_data: Dict[str, Any]) -> str:
    """
    Format a ticket with comments into a knowledge base document format.
    This shows how the data will be structured in your vectorstore.
    """
    content_parts = [
        f"# Jira Ticket: {ticket_data['key']}",
        f"Summary: {ticket_data['summary']}",
        f"Status: {ticket_data['status']}",
        f"Priority: {ticket_data['priority']}",
        "",
        "## Customer Query/Issue",
        f"Reporter: {ticket_data['reporter']}",
        f"Created: {ticket_data['created']}",
        "",
        ticket_data['description'],
        ""
    ]
    
    if ticket_data['comments']:
        content_parts.append("## Developer Solutions/Comments")
        content_parts.append("")
        
        for idx, comment in enumerate(ticket_data['comments'], 1):
            content_parts.append(f"### Solution {idx} - {comment['author']} ({comment['created'][:10]})")
            content_parts.append("")
            content_parts.append(comment['body'])
            content_parts.append("")
    
    if ticket_data['resolved']:
        content_parts.append(f"## Resolution")
        content_parts.append(f"Resolved: {ticket_data['resolved']}")
        content_parts.append("")
    
    return "\n".join(content_parts)

def main():
    """Main test function."""
    print("\n" + "=" * 60)
    print("JIRA TICKETS & COMMENTS TEST")
    print("=" * 60)
    print("\nThis script fetches:")
    print("  - Customer queries (ticket descriptions)")
    print("  - Developer solutions (comments)")
    print("  - Resolved/closed tickets")
    print("\nThis data will be added to your knowledge base!")
    
    if not JIRA_API_TOKEN:
        print("\n[ERROR] JIRA_API_TOKEN not found in .env file!")
        return
    
    try:
        # Connect to Jira
        jira = JIRA(
            server=JIRA_SERVER,
            basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN)
        )
        
        print(f"\n[OK] Connected to Jira: {JIRA_SERVER}")
        
        # Get projects
        projects = jira.projects()
        print(f"\nAvailable projects: {len(projects)}")
        for proj in projects[:5]:
            print(f"  - {proj.key}: {proj.name}")
        
        # Fetch tickets with comments
        print("\n" + "=" * 60)
        project_key = None  # Set to specific project key if needed, e.g., "PROJ"
        
        # Fetch tickets with comments
        tickets = fetch_tickets_with_comments(
            jira=jira,
            project_key=project_key,
            max_results=10,
            status_filter=None  # None = Resolved/Done/Closed
        )
        
        if tickets:
            # Show formatted example
            print("\n" + "=" * 60)
            print("KNOWLEDGE BASE FORMAT EXAMPLE")
            print("=" * 60)
            print("\nThis is how ticket data will be formatted for your knowledge base:")
            print("\n" + "-" * 60)
            formatted = format_ticket_for_knowledge_base(tickets[0])
            print(formatted[:1000] + "..." if len(formatted) > 1000 else formatted)
            print("-" * 60)
            
            # Save results
            output_file = "jira_tickets_comments_test.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "timestamp": datetime.now().isoformat(),
                    "server": JIRA_SERVER,
                    "total_tickets": len(tickets),
                    "tickets": tickets
                }, f, indent=2, default=str, ensure_ascii=False)
            
            print(f"\n[OK] Results saved to: {output_file}")
            print(f"\nSummary:")
            print(f"  - Total tickets fetched: {len(tickets)}")
            print(f"  - Total comments: {sum(len(t['comments']) for t in tickets)}")
            print(f"  - Average comments per ticket: {sum(len(t['comments']) for t in tickets) / len(tickets):.1f}")
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
