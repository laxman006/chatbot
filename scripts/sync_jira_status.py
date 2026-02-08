# -*- coding: utf-8 -*-
"""
Check Jira sync status and statistics
"""
import os
import sys

# Add parent directory to path to import app module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app.jira_vectorstore import load_jira_vectorstore
from app.jira_sync_tracker import get_sync_stats

if __name__ == "__main__":
    print("=" * 70)
    print("JIRA SYNC STATUS")
    print("=" * 70)
    
    # Get sync statistics
    stats = get_sync_stats()
    
    if stats:
        print(f"\nLast Sync: {stats.get('last_sync_readable', 'Never')}")
        print(f"Last Sync (ISO): {stats.get('last_sync', 'N/A')}")
        
        sync_history = stats.get('sync_history', [])
        if sync_history:
            print(f"\nSync History ({len(sync_history)} records):")
            for idx, sync in enumerate(reversed(sync_history), 1):
                print(f"  {idx}. {sync['readable']}")
    else:
        print("\n⚠️ No sync history found")
        print("Run build_jira_vectorstore_all.py to initialize")
    
    # Get vectorstore statistics
    print("\n" + "=" * 70)
    print("VECTORSTORE STATISTICS")
    print("=" * 70)
    
    try:
        vectorstore = load_jira_vectorstore()
        
        if vectorstore:
            total_docs = vectorstore._collection.count()
            print(f"\nTotal Documents: {total_docs}")
            
            # Get sample metadata to show projects
            sample_docs = vectorstore.get(limit=100)
            if sample_docs and 'metadatas' in sample_docs:
                projects = {}
                for metadata in sample_docs['metadatas']:
                    if metadata and 'project_key' in metadata:
                        project = metadata['project_key']
                        projects[project] = projects.get(project, 0) + 1
                
                if projects:
                    print(f"\nProjects (from sample of {len(sample_docs['metadatas'])} docs):")
                    for project, count in sorted(projects.items()):
                        print(f"  {project}: {count} documents")
            
            print(f"\nVectorstore Path: ./data/jira_vectorstore")
            print("Status: ✅ Active")
        else:
            print("\n⚠️ Vectorstore not found")
            print("Run build_jira_vectorstore_all.py to create it")
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
