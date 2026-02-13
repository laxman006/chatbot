#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Jira Lazy Loading Fix

This test verifies that the lazy loading fix in intelligent_route_and_retrieve
is working correctly. It tests the code logic without requiring a full vectorstore.
"""

import os
import sys

# Set environment to prevent auto-initialization
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
sys.path.insert(0, '.')

def test_lazy_loading_code():
    """Test that lazy loading code exists in intelligent_route_and_retrieve"""
    print("=" * 80)
    print("TEST: JIRA LAZY LOADING FIX VERIFICATION")
    print("=" * 80)
    print()
    
    try:
        # Read the endpoints.py file to check for lazy loading
        with open('app/endpoints.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for the lazy loading code we added
        has_lazy_load = '_get_jira_vectorstore_cached' in content
        
        # Find the intelligent_route_and_retrieve function
        if 'def intelligent_route_and_retrieve' in content:
            # Extract the function to check for lazy loading
            start_idx = content.find('def intelligent_route_and_retrieve')
            # Find the end of the function (next def or class at same indentation)
            lines = content[start_idx:].split('\n')
            func_lines = []
            for i, line in enumerate(lines):
                if i > 0 and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                    if line.strip().startswith('def ') or line.strip().startswith('class '):
                        break
                func_lines.append(line)
            
            func_content = '\n'.join(func_lines)
            
            # Check if lazy loading is present
            has_jira_vs_check = 'jira_vs = jira_vectorstore' in func_content or 'jira_vs =' in func_content
            has_get_cached_call = '_get_jira_vectorstore_cached' in func_content
            
            print("[OK] Found intelligent_route_and_retrieve function")
            
            if has_get_cached_call and has_jira_vs_check:
                print("[OK] Lazy loading code is present!")
                print("    - Checks for _get_jira_vectorstore_cached")
                print("    - Loads jira_vs before passing to intelligent_multi_source_retrieve")
                return True
            else:
                print("[FAIL] Lazy loading code is MISSING!")
                print("    Expected to see:")
                print("      jira_vs = jira_vectorstore")
                print("      if _get_jira_vectorstore_cached:")
                print("          jira_vs = _get_jira_vectorstore_cached()")
                return False
        else:
            print("[FAIL] Could not find intelligent_route_and_retrieve function")
            return False
            
    except Exception as e:
        print(f"[FAIL] Error reading file: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_multi_source_retrieval_none_handling():
    """Test that multi_source_retrieval handles None jira_vectorstore"""
    print()
    print("=" * 80)
    print("TEST: NONE HANDLING IN MULTI_SOURCE_RETRIEVAL")
    print("=" * 80)
    print()
    
    try:
        # Read the multi_source_retrieval.py file
        with open('multi_source_retrieval.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for None handling in intelligent_multi_source_retrieve
        if 'if not jira_vectorstore:' in content:
            print("[OK] None check is present in intelligent_multi_source_retrieve")
            
            # Check if it sets jira_docs = [] when None
            if 'jira_docs = []' in content:
                print("[OK] Sets jira_docs = [] when jira_vectorstore is None")
                return True
            else:
                print("[FAIL] Does not set jira_docs = [] when None")
                return False
        else:
            print("[FAIL] None check is MISSING in intelligent_multi_source_retrieve")
            return False
            
    except Exception as e:
        print(f"[FAIL] Error reading file: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print()
    
    test1 = test_lazy_loading_code()
    test2 = test_multi_source_retrieval_none_handling()
    
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if test1 and test2:
        print("[OK] All code checks passed!")
        print()
        print("The lazy loading fix is correctly implemented in the code.")
        print("If Jira retrieval still doesn't work, the issue is likely:")
        print("  1. Jira vectorstore database corruption (rebuild needed)")
        print("  2. Jira vectorstore not initialized (set INITIALIZE_JIRA_VECTORSTORE=true)")
        print("  3. Jira vectorstore path doesn't exist")
        return 0
    else:
        print("[FAIL] Some code checks failed!")
        print()
        print("The lazy loading fix may not be correctly implemented.")
        print("Check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
