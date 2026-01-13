# -*- coding: utf-8 -*-
"""
Script to build Jira Vectorstore with 300 tickets
This script sets JIRA_MAX_ISSUES=300 and builds a fresh vectorstore
"""

import os
import sys

# Set environment variables before importing config
os.environ['JIRA_MAX_ISSUES'] = '300'
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'true'

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

from app.jira_vectorstore import build_jira_vectorstore

if __name__ == "__main__":
    print("=" * 70)
    print("BUILDING JIRA VECTORSTORE WITH 300 TICKETS")
    print("=" * 70)
    print(f"JIRA_MAX_ISSUES: {os.getenv('JIRA_MAX_ISSUES', '300')}")
    print("=" * 70)
    print()
    
    try:
        vectorstore = build_jira_vectorstore()
        
        if vectorstore:
            total_docs = vectorstore._collection.count()
            print("\n" + "=" * 70)
            print("✅ JIRA VECTORSTORE BUILT SUCCESSFULLY!")
            print("=" * 70)
            print(f"Total documents in vectorstore: {total_docs}")
            print(f"Vectorstore path: ./data/jira_chroma_db")
            print("=" * 70)
        else:
            print("\n" + "=" * 70)
            print("❌ FAILED TO BUILD JIRA VECTORSTORE")
            print("=" * 70)
            sys.exit(1)
            
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
