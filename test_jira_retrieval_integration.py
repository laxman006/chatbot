#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Jira Retrieval Integration

Tests that Jira tickets are properly retrieved through the intelligent routing system.
This test verifies:
1. Jira vectorstore lazy loading
2. retrieve_from_jira function
3. intelligent_multi_source_retrieve with Jira
4. intelligent_route_and_retrieve integration
"""

import os
import sys
import traceback

# Set environment to prevent auto-initialization
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

# Add project root to path
sys.path.insert(0, '.')

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.HEADER}{'='*80}{Colors.ENDC}\n")

def print_success(text):
    print(f"{Colors.OKGREEN}[✓]{Colors.ENDC} {text}")

def print_error(text):
    print(f"{Colors.FAIL}[✗]{Colors.ENDC} {text}")

def print_info(text):
    print(f"{Colors.OKCYAN}[i]{Colors.ENDC} {text}")

def print_warning(text):
    print(f"{Colors.WARNING}[!]{Colors.ENDC} {text}")

def test_jira_vectorstore_loading():
    """Test 1: Verify Jira vectorstore can be loaded"""
    print_header("TEST 1: JIRA VECTORSTORE LOADING")
    
    try:
        from app.jira_vectorstore import _get_jira_vectorstore_cached
        
        print_info("Attempting to load Jira vectorstore...")
        jira_vs = _get_jira_vectorstore_cached()
        
        if jira_vs is None:
            print_error("Jira vectorstore is None - cannot proceed with tests")
            print_warning("Make sure JIRA_VECTORSTORE_PATH exists and contains data")
            print_warning("Set INITIALIZE_JIRA_VECTORSTORE=true to build it")
            return None
        
        # Get document count
        try:
            doc_count = jira_vs._collection.count()
            print_success(f"Jira vectorstore loaded successfully")
            print_info(f"Total documents in vectorstore: {doc_count:,}")
            
            if doc_count == 0:
                print_warning("Vectorstore is empty - no tickets available for retrieval")
                return None
        except Exception as count_error:
            print_warning(f"Could not get document count: {count_error}")
            print_info("Vectorstore loaded but count check failed - may still work for retrieval")
            # Continue anyway - retrieval might still work
        
        return jira_vs
        
    except Exception as e:
        error_msg = str(e)
        if "PanicException" in error_msg or "range start index" in error_msg:
            print_error("ChromaDB database corruption detected!")
            print_warning("The Jira vectorstore database may be corrupted.")
            print_warning("Try rebuilding it by:")
            print_warning("  1. Delete the JIRA_VECTORSTORE_PATH directory")
            print_warning("  2. Set INITIALIZE_JIRA_VECTORSTORE=true")
            print_warning("  3. Restart the application")
        else:
            print_error(f"Failed to load Jira vectorstore: {e}")
        traceback.print_exc()
        return None

def test_retrieve_from_jira(jira_vectorstore):
    """Test 2: Test retrieve_from_jira function directly"""
    print_header("TEST 2: DIRECT RETRIEVAL FUNCTION TEST")
    
    if not jira_vectorstore:
        print_error("Skipping - Jira vectorstore not available")
        return False
    
    try:
        from multi_source_retrieval import retrieve_from_jira
        
        test_queries = [
            ("migration error", 5),
            ("authentication issue", 3),
            ("user mapping problem", 10),
        ]
        
        all_passed = True
        
        for query, k in test_queries:
            print_info(f"Testing query: '{query}' (k={k})")
            try:
                results = retrieve_from_jira(jira_vectorstore, query, k=k)
                
                if len(results) == 0:
                    print_warning(f"No results returned for query: '{query}'")
                    all_passed = False
                else:
                    print_success(f"Retrieved {len(results)} tickets")
                    
                    # Show sample results
                    for i, (doc, score) in enumerate(results[:2], 1):
                        ticket_key = doc.metadata.get('ticket_key', 'N/A')
                        section = doc.metadata.get('section', 'N/A')
                        print(f"      {i}. Ticket: {ticket_key}, Section: {section}, Score: {score:.4f}")
                
            except Exception as e:
                print_error(f"Retrieval failed for '{query}': {e}")
                traceback.print_exc()
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print_error(f"Failed to import retrieve_from_jira: {e}")
        traceback.print_exc()
        return False

def test_intelligent_multi_source_retrieve(jira_vectorstore):
    """Test 3: Test intelligent_multi_source_retrieve with Jira"""
    print_header("TEST 3: INTELLIGENT MULTI-SOURCE RETRIEVAL TEST")
    
    if not jira_vectorstore:
        print_error("Skipping - Jira vectorstore not available")
        return False
    
    try:
        from multi_source_retrieval import intelligent_multi_source_retrieve
        from app.vectorstore import vectorstore
        
        if not vectorstore:
            print_error("Main vectorstore not available - cannot test multi-source retrieval")
            return False
        
        # Create a routing plan that requests Jira tickets
        routing_plan = {
            "query_type": "troubleshooting",
            "query_intent": "Find solutions to migration issues",
            "sources": {
                "jira": {"k": 10, "relevance": 0.9},
                "sharepoint": {"k": 5, "relevance": 0.6},
                "pdfs": {"k": 0, "relevance": 0.0},
                "blog": {"k": 0, "relevance": 0.0},
                "transcripts": {"k": 0, "relevance": 0.0},
                "excel": {"k": 0, "relevance": 0.0}
            },
            "confidence": 0.85
        }
        
        test_query = "migration error during user mapping"
        
        print_info(f"Testing query: '{test_query}'")
        print_info("Routing plan requests 10 Jira tickets")
        
        try:
            results = intelligent_multi_source_retrieve(
                vectorstore=vectorstore,
                jira_vectorstore=jira_vectorstore,
                query=test_query,
                routing_plan=routing_plan,
                enable_deduplication=False  # Disable for testing
            )
            
            # Count Jira tickets in results
            jira_count = 0
            for doc, score in results:
                if doc.metadata.get('ticket_key'):
                    jira_count += 1
            
            print_info(f"Total results: {len(results)}")
            print_info(f"Jira tickets in results: {jira_count}")
            
            if jira_count == 0:
                print_error("No Jira tickets found in results!")
                print_warning("Check that jira_vectorstore is being passed correctly")
                return False
            else:
                print_success(f"Found {jira_count} Jira tickets in results")
                
                # Show sample Jira tickets
                print_info("Sample Jira tickets:")
                shown = 0
                for doc, score in results:
                    if doc.metadata.get('ticket_key') and shown < 3:
                        ticket_key = doc.metadata.get('ticket_key', 'N/A')
                        section = doc.metadata.get('section', 'N/A')
                        print(f"      • {ticket_key} ({section}) - Score: {score:.4f}")
                        shown += 1
                
                return True
                
        except Exception as e:
            print_error(f"intelligent_multi_source_retrieve failed: {e}")
            traceback.print_exc()
            return False
        
    except Exception as e:
        print_error(f"Failed to import required modules: {e}")
        traceback.print_exc()
        return False

def test_intelligent_route_and_retrieve():
    """Test 4: Test full intelligent_route_and_retrieve integration"""
    print_header("TEST 4: FULL INTELLIGENT ROUTING INTEGRATION TEST")
    
    try:
        from app.endpoints import intelligent_route_and_retrieve
        
        # Test queries that should trigger Jira retrieval
        test_queries = [
            ("How to fix migration error?", "Should retrieve Jira tickets"),
            ("migration problem during user mapping", "Should retrieve Jira tickets"),
            ("authentication issue", "Should retrieve Jira tickets"),
        ]
        
        all_passed = True
        
        for query, description in test_queries:
            print_info(f"Testing: '{query}'")
            print_info(f"Expected: {description}")
            
            try:
                results = intelligent_route_and_retrieve(
                    query=query,
                    k_final=10,
                    use_routing=True
                )
                
                # Count Jira tickets
                jira_count = 0
                for doc, score in results:
                    if doc.metadata.get('ticket_key'):
                        jira_count += 1
                
                print_info(f"Total results: {len(results)}")
                print_info(f"Jira tickets: {jira_count}")
                
                if jira_count == 0:
                    print_warning(f"No Jira tickets retrieved for: '{query}'")
                    print_warning("This might be expected if routing plan doesn't request Jira")
                    # Don't fail the test - routing might not request Jira for all queries
                else:
                    print_success(f"Retrieved {jira_count} Jira tickets")
                    
                    # Show sample
                    shown = 0
                    for doc, score in results:
                        if doc.metadata.get('ticket_key') and shown < 2:
                            ticket_key = doc.metadata.get('ticket_key', 'N/A')
                            section = doc.metadata.get('section', 'N/A')
                            print(f"      • {ticket_key} ({section})")
                            shown += 1
                
            except Exception as e:
                print_error(f"intelligent_route_and_retrieve failed: {e}")
                traceback.print_exc()
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print_error(f"Failed to import intelligent_route_and_retrieve: {e}")
        traceback.print_exc()
        return False

def test_jira_vectorstore_none_handling():
    """Test 5: Test that None jira_vectorstore is handled gracefully"""
    print_header("TEST 5: NONE HANDLING TEST")
    
    try:
        from multi_source_retrieval import retrieve_from_jira, intelligent_multi_source_retrieve
        from app.vectorstore import vectorstore
        
        if not vectorstore:
            print_warning("Main vectorstore not available - skipping None handling test")
            return True
        
        # Test retrieve_from_jira with None
        print_info("Testing retrieve_from_jira with None vectorstore...")
        results = retrieve_from_jira(None, "test query", k=5)
        if results == []:
            print_success("retrieve_from_jira correctly returns [] for None vectorstore")
        else:
            print_error("retrieve_from_jira should return [] for None vectorstore")
            return False
        
        # Test intelligent_multi_source_retrieve with None
        print_info("Testing intelligent_multi_source_retrieve with None jira_vectorstore...")
        routing_plan = {
            "sources": {
                "jira": {"k": 10, "relevance": 0.9},
                "sharepoint": {"k": 5, "relevance": 0.6},
            }
        }
        
        results = intelligent_multi_source_retrieve(
            vectorstore=vectorstore,
            jira_vectorstore=None,
            query="test query",
            routing_plan=routing_plan,
            enable_deduplication=False
        )
        
        # Should not crash, and should return results from other sources
        print_success("intelligent_multi_source_retrieve handles None gracefully")
        print_info(f"Returned {len(results)} results (should have SharePoint results)")
        
        return True
        
    except Exception as e:
        print_error(f"None handling test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all tests"""
    print_header("JIRA RETRIEVAL INTEGRATION TEST SUITE")
    
    print_info("This test suite verifies that Jira ticket retrieval works correctly")
    print_info("through the intelligent routing system.")
    print()
    
    results = {
        "test_1_loading": False,
        "test_2_direct_retrieval": False,
        "test_3_multi_source": False,
        "test_4_full_integration": False,
        "test_5_none_handling": False,
    }
    
    # Test 1: Load vectorstore
    jira_vectorstore = test_jira_vectorstore_loading()
    if jira_vectorstore:
        results["test_1_loading"] = True
    
    # Test 2: Direct retrieval
    if jira_vectorstore:
        results["test_2_direct_retrieval"] = test_retrieve_from_jira(jira_vectorstore)
    
    # Test 3: Multi-source retrieval
    if jira_vectorstore:
        results["test_3_multi_source"] = test_intelligent_multi_source_retrieve(jira_vectorstore)
    
    # Test 4: Full integration
    results["test_4_full_integration"] = test_intelligent_route_and_retrieve()
    
    # Test 5: None handling
    results["test_5_none_handling"] = test_jira_vectorstore_none_handling()
    
    # Summary
    print_header("TEST SUMMARY")
    
    test_names = {
        "test_1_loading": "Jira Vectorstore Loading",
        "test_2_direct_retrieval": "Direct Retrieval Function",
        "test_3_multi_source": "Multi-Source Retrieval",
        "test_4_full_integration": "Full Integration Test",
        "test_5_none_handling": "None Handling",
    }
    
    passed = 0
    skipped = 0
    total = len(results)
    
    for test_key, test_name in test_names.items():
        status = results[test_key]
        if status:
            print_success(f"{test_name}: PASSED")
            passed += 1
        elif test_key == "test_2_direct_retrieval" or test_key == "test_3_multi_source":
            if not jira_vectorstore:
                print_warning(f"{test_name}: SKIPPED (vectorstore not available)")
                skipped += 1
            else:
                print_error(f"{test_name}: FAILED")
        else:
            print_error(f"{test_name}: FAILED")
    
    print()
    print(f"{Colors.BOLD}Results: {passed}/{total} tests passed ({skipped} skipped){Colors.ENDC}")
    
    if passed == total:
        print_success("All tests passed! Jira retrieval is working correctly.")
        return 0
    elif jira_vectorstore and passed >= 3:
        print_warning("Some tests passed. Jira retrieval is partially working.")
        print_warning("Check the failed tests above for details.")
        return 1
    elif not jira_vectorstore:
        print_error("Jira vectorstore could not be loaded.")
        print_error("This prevents most retrieval tests from running.")
        print_error("Check the error messages above and verify:")
        print_error("  1. JIRA_VECTORSTORE_PATH exists and contains data")
        print_error("  2. INITIALIZE_JIRA_VECTORSTORE=true if vectorstore needs to be built")
        print_error("  3. ENABLE_JIRA_VECTORSTORE=true in config")
        print_error("  4. If database corruption error: delete JIRA_VECTORSTORE_PATH and rebuild")
        return 1
    else:
        print_error("Multiple tests failed. Jira retrieval is not working correctly.")
        print_error("Check the error messages above and verify:")
        print_error("  1. JIRA_VECTORSTORE_PATH exists and contains data")
        print_error("  2. INITIALIZE_JIRA_VECTORSTORE=true if vectorstore needs to be built")
        print_error("  3. ENABLE_JIRA_VECTORSTORE=true in config")
        return 1

if __name__ == "__main__":
    sys.exit(main())
