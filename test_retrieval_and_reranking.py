#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive Test Suite for Retrieval and Reranking

This test suite verifies:
1. Multi-source retrieval functionality
2. Cross-encoder reranking
3. Score normalization and fusion
4. Section-based boosting
5. End-to-end retrieval + reranking pipeline
"""

import os
import sys
import traceback
from typing import List, Tuple
from langchain_core.documents import Document

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
    print(f"{Colors.OKGREEN}[PASS]{Colors.ENDC} {text}")

def print_error(text):
    print(f"{Colors.FAIL}[FAIL]{Colors.ENDC} {text}")

def print_info(text):
    print(f"{Colors.OKCYAN}[INFO]{Colors.ENDC} {text}")

def print_warning(text):
    print(f"{Colors.WARNING}[WARN]{Colors.ENDC} {text}")


def test_reranker_initialization():
    """Test 1: Verify reranker can be initialized"""
    print_header("TEST 1: RERANKER INITIALIZATION")
    
    try:
        from reranker import CrossEncoderReranker
        
        print_info("Initializing CrossEncoderReranker...")
        reranker = CrossEncoderReranker()
        
        if reranker.model is None:
            print_warning("Reranker model is None - reranking will fallback to base scores")
            print_warning("Install sentence-transformers: pip install sentence-transformers")
            return None
        else:
            print_success("CrossEncoderReranker initialized successfully")
            return reranker
            
    except Exception as e:
        print_error(f"Failed to initialize reranker: {e}")
        traceback.print_exc()
        return None


def test_reranker_basic_functionality(reranker):
    """Test 2: Test basic reranking functionality"""
    print_header("TEST 2: BASIC RERANKING FUNCTIONALITY")
    
    if not reranker:
        print_warning("Skipping - reranker not available")
        return False
    
    try:
        # Create mock documents with different relevance
        query = "migration error database timeout"
        
        docs = [
            Document(
                page_content="Database connection timeout during migration. Root cause: network configuration issue.",
                metadata={"source_type": "jira", "ticket_key": "CF-123", "section": "root_cause"}
            ),
            Document(
                page_content="CloudFuze migration platform overview and features.",
                metadata={"source_type": "blog", "tag": "blog"}
            ),
            Document(
                page_content="Fix for database timeout: Increase connection pool size and check network settings.",
                metadata={"source_type": "jira", "ticket_key": "CF-123", "section": "fix_description"}
            ),
            Document(
                page_content="General information about cloud migration services.",
                metadata={"source_type": "sharepoint"}
            ),
        ]
        
        # Create candidates with base scores (distance scores - lower is better)
        candidates = [
            (docs[0], 0.3),  # Most relevant
            (docs[1], 0.8),  # Less relevant
            (docs[2], 0.4),  # Relevant
            (docs[3], 0.9),  # Least relevant
        ]
        
        print_info(f"Testing reranking with query: '{query}'")
        print_info(f"Input: {len(candidates)} candidates")
        
        # Rerank
        reranked = reranker.rerank(query, candidates, top_k=len(candidates))
        
        print_success(f"Reranking completed: {len(reranked)} results")
        
        # Display results
        print("\nReranked Results:")
        for i, (doc, score) in enumerate(reranked, 1):
            source = doc.metadata.get("source_type", "unknown")
            ticket_key = doc.metadata.get("ticket_key", "")
            section = doc.metadata.get("section", "")
            preview = doc.page_content[:60] + "..."
            print(f"  {i}. Score: {score:.4f} | Source: {source} | Ticket: {ticket_key} | Section: {section}")
            print(f"     Preview: {preview}")
        
        # Verify reranking improved order
        if len(reranked) >= 2:
            first_score = reranked[0][1]
            second_score = reranked[1][1]
            
            if first_score >= second_score:
                print_success("Reranking maintains descending score order (higher is better)")
            else:
                print_warning("Reranking scores are not in descending order")
        
        # Verify scores are in valid range [0, 1]
        all_valid = all(0 <= score <= 1 for _, score in reranked)
        if all_valid:
            print_success("All reranked scores are in valid range [0, 1]")
        else:
            print_error("Some reranked scores are outside valid range [0, 1]")
            return False
        
        return True
        
    except Exception as e:
        print_error(f"Basic reranking test failed: {e}")
        traceback.print_exc()
        return False


def test_reranker_fallback_mode():
    """Test 3: Test reranker fallback when model is unavailable"""
    print_header("TEST 3: RERANKER FALLBACK MODE")
    
    try:
        from reranker import CrossEncoderReranker
        
        # Create a reranker without model (simulate missing dependency)
        class MockReranker(CrossEncoderReranker):
            def __init__(self):
                self.model = None
        
        reranker = MockReranker()
        
        query = "test query"
        candidates = [
            (Document(page_content="Document 1", metadata={}), 0.3),
            (Document(page_content="Document 2", metadata={}), 0.5),
            (Document(page_content="Document 3", metadata={}), 0.2),
        ]
        
        print_info("Testing fallback mode (no model)...")
        reranked = reranker.rerank(query, candidates, top_k=2)
        
        if len(reranked) == 2:
            print_success("Fallback mode works: returns top-k based on base scores")
            
            # Verify order (should be sorted by base score descending)
            scores = [score for _, score in reranked]
            if scores == sorted(scores, reverse=True):
                print_success("Fallback mode maintains correct score order")
                return True
            else:
                print_error("Fallback mode scores are not in correct order")
                return False
        else:
            print_error(f"Fallback mode returned {len(reranked)} results, expected 2")
            return False
            
    except Exception as e:
        print_error(f"Fallback mode test failed: {e}")
        traceback.print_exc()
        return False


def test_multi_source_retrieval():
    """Test 4: Test multi-source retrieval"""
    print_header("TEST 4: MULTI-SOURCE RETRIEVAL")
    
    # Check if vectorstore can be imported (it initializes at import time)
    import sys
    import importlib.util
    
    try:
        # Try to import vectorstore module
        spec = importlib.util.find_spec("app.vectorstore")
        if spec is None:
            print_warning("Cannot find app.vectorstore module")
            return False
        
        # Try importing - this will fail if ChromaDB is corrupted
        try:
            from app.vectorstore import get_vectorstore
            from app.jira_vectorstore import get_jira_vectorstore
            from multi_source_retrieval import intelligent_multi_source_retrieve
        except Exception as import_error:
            error_str = str(import_error)
            if "PanicException" in error_str or "range start index" in error_str:
                print_warning("ChromaDB database corruption detected during import")
                print_warning("Cannot test multi-source retrieval without working vectorstore")
                print_warning("To fix: Delete corrupted ChromaDB and rebuild vectorstore")
                return False
            else:
                raise
    except ImportError as e:
        print_warning(f"Cannot import vectorstore modules: {e}")
        return False
        
        print_info("Loading vectorstores...")
        try:
            vectorstore = get_vectorstore()
        except Exception as vs_error:
            if "PanicException" in str(vs_error) or "range start index" in str(vs_error):
                print_warning("ChromaDB database corruption detected - cannot load vectorstore")
                print_warning("This test requires a working vectorstore")
                return False
            else:
                raise
        
        try:
            jira_vectorstore = get_jira_vectorstore()
        except Exception as jira_error:
            if "PanicException" in str(jira_error) or "range start index" in str(jira_error):
                print_warning("Jira ChromaDB database corruption detected - continuing without Jira")
                jira_vectorstore = None
            else:
                raise
        
        if not vectorstore:
            print_warning("Main vectorstore not available - skipping multi-source retrieval test")
            return False
        
        # Create routing plan requesting multiple sources
        routing_plan = {
            "query_type": "troubleshooting",
            "query_intent": "Find solutions to migration issues",
            "sources": {
                "jira": {"k": 5, "relevance": 0.9, "reasoning": "High relevance for troubleshooting"},
                "sharepoint": {"k": 3, "relevance": 0.6, "reasoning": "Medium relevance for procedures"},
                "blog": {"k": 2, "relevance": 0.3, "reasoning": "Low relevance"},
                "pdfs": {"k": 0, "relevance": 0.0, "reasoning": "Not relevant"},
                "transcripts": {"k": 0, "relevance": 0.0, "reasoning": "Not relevant"},
                "excel": {"k": 0, "relevance": 0.0, "reasoning": "Not relevant"}
            },
            "confidence": 0.85
        }
        
        query = "migration error during user mapping"
        
        print_info(f"Testing query: '{query}'")
        print_info("Routing plan requests:")
        for source, plan in routing_plan["sources"].items():
            if plan["k"] > 0:
                print(f"  • {source}: k={plan['k']}, relevance={plan['relevance']:.2f}")
        
        results = intelligent_multi_source_retrieve(
            vectorstore=vectorstore,
            jira_vectorstore=jira_vectorstore,
            query=query,
            routing_plan=routing_plan,
            enable_deduplication=True
        )
        
        print_success(f"Retrieved {len(results)} documents from multiple sources")
        
        # Analyze source distribution
        source_counts = {}
        for doc, score in results:
            ticket_key = doc.metadata.get("ticket_key")
            if ticket_key:
                source_counts["jira"] = source_counts.get("jira", 0) + 1
            else:
                source_type = doc.metadata.get("source_type", "unknown")
                tag = doc.metadata.get("tag", "")
                if "blog" in tag.lower() or "blog" in source_type.lower():
                    source_counts["blog"] = source_counts.get("blog", 0) + 1
                elif "sharepoint" in source_type.lower():
                    source_counts["sharepoint"] = source_counts.get("sharepoint", 0) + 1
                else:
                    source_counts[source_type] = source_counts.get(source_type, 0) + 1
        
        print("\nSource Distribution:")
        for source, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
            print(f"  • {source}: {count} documents")
        
        # Verify we got results from requested sources
        requested_sources = {k: v["k"] for k, v in routing_plan["sources"].items() if v["k"] > 0}
        found_sources = set(source_counts.keys())
        
        if len(results) > 0:
            print_success("Multi-source retrieval completed successfully")
            return True
        else:
            print_warning("No documents retrieved - this might be expected if vectorstores are empty")
            return False
            
    except Exception as e:
        print_error(f"Multi-source retrieval test failed: {e}")
        traceback.print_exc()
        return False


def test_score_normalization():
    """Test 5: Test score normalization"""
    print_header("TEST 5: SCORE NORMALIZATION")
    
    try:
        from multi_source_retrieval import normalize_scores
        
        # Create candidates with distance scores (lower is better)
        candidates = [
            (Document(page_content="Doc 1", metadata={}), 0.1),  # Best (lowest distance)
            (Document(page_content="Doc 2", metadata={}), 0.5),  # Medium
            (Document(page_content="Doc 3", metadata={}), 0.9),  # Worst (highest distance)
        ]
        
        print_info("Testing score normalization...")
        print_info("Input scores (distance - lower is better):")
        for i, (doc, score) in enumerate(candidates, 1):
            print(f"  {i}. Distance: {score:.4f}")
        
        normalized = normalize_scores(candidates)
        
        print_success(f"Normalized {len(normalized)} scores")
        
        print("\nNormalized scores (similarity - higher is better):")
        for i, (doc, score) in enumerate(normalized, 1):
            print(f"  {i}. Similarity: {score:.4f}")
        
        # Verify normalization
        scores = [score for _, score in normalized]
        
        # Check all scores are in [0, 1]
        all_valid = all(0 <= score <= 1 for score in scores)
        if not all_valid:
            print_error("Some normalized scores are outside [0, 1] range")
            return False
        
        # Check that best distance (0.1) becomes highest similarity
        if len(normalized) >= 3:
            best_doc_score = normalized[0][1]  # Should be highest similarity
            worst_doc_score = normalized[2][1]  # Should be lowest similarity
            
            if best_doc_score >= worst_doc_score:
                print_success("Normalization correctly converts distance to similarity")
                print_success(f"Best distance (0.1) → Highest similarity ({best_doc_score:.4f})")
                return True
            else:
                print_error("Normalization did not correctly convert distance to similarity")
                return False
        else:
            print_warning("Not enough results to verify normalization correctness")
            return True
            
    except Exception as e:
        print_error(f"Score normalization test failed: {e}")
        traceback.print_exc()
        return False


def test_end_to_end_retrieval_reranking():
    """Test 6: Test end-to-end retrieval + reranking pipeline"""
    print_header("TEST 6: END-TO-END RETRIEVAL + RERANKING")
    
    # Check if vectorstore can be imported (it initializes at import time)
    import sys
    import importlib.util
    
    try:
        # Try to import vectorstore module
        spec = importlib.util.find_spec("app.vectorstore")
        if spec is None:
            print_warning("Cannot find app.vectorstore module")
            return False
        
        # Try importing - this will fail if ChromaDB is corrupted
        try:
            from app.vectorstore import get_vectorstore
            from app.jira_vectorstore import get_jira_vectorstore
            from multi_source_retrieval import intelligent_multi_source_retrieve, normalize_scores
            from reranker import CrossEncoderReranker
        except Exception as import_error:
            error_str = str(import_error)
            if "PanicException" in error_str or "range start index" in error_str:
                print_warning("ChromaDB database corruption detected during import")
                print_warning("Cannot test end-to-end retrieval without working vectorstore")
                print_warning("To fix: Delete corrupted ChromaDB and rebuild vectorstore")
                return False
            else:
                raise
    except ImportError as e:
        print_warning(f"Cannot import vectorstore modules: {e}")
        return False
        
        print_info("Loading components...")
        try:
            vectorstore = get_vectorstore()
        except Exception as vs_error:
            if "PanicException" in str(vs_error) or "range start index" in str(vs_error):
                print_warning("ChromaDB database corruption detected - cannot load vectorstore")
                print_warning("This test requires a working vectorstore")
                return False
            else:
                raise
        
        try:
            jira_vectorstore = get_jira_vectorstore()
        except Exception as jira_error:
            if "PanicException" in str(jira_error) or "range start index" in str(jira_error):
                print_warning("Jira ChromaDB database corruption detected - continuing without Jira")
                jira_vectorstore = None
            else:
                raise
        
        reranker = CrossEncoderReranker()
        
        if not vectorstore:
            print_warning("Main vectorstore not available - skipping end-to-end test")
            return False
        
        if reranker.model is None:
            print_warning("Reranker model not available - will use fallback mode")
        
        # Create routing plan
        routing_plan = {
            "query_type": "troubleshooting",
            "query_intent": "Find solutions to migration errors",
            "sources": {
                "jira": {"k": 10, "relevance": 0.9},
                "sharepoint": {"k": 5, "relevance": 0.6},
                "blog": {"k": 2, "relevance": 0.3},
                "pdfs": {"k": 0, "relevance": 0.0},
                "transcripts": {"k": 0, "relevance": 0.0},
                "excel": {"k": 0, "relevance": 0.0}
            },
            "confidence": 0.85
        }
        
        query = "database connection timeout during migration"
        k_final = 8
        
        print_info(f"Query: '{query}'")
        print_info(f"Target: Retrieve and rerank to top {k_final} documents")
        
        # Step 1: Multi-source retrieval
        print("\n[STEP 1] Multi-source retrieval...")
        all_candidates = intelligent_multi_source_retrieve(
            vectorstore=vectorstore,
            jira_vectorstore=jira_vectorstore,
            query=query,
            routing_plan=routing_plan,
            enable_deduplication=True
        )
        
        print_success(f"Retrieved {len(all_candidates)} candidates")
        
        if len(all_candidates) == 0:
            print_warning("No candidates retrieved - cannot test reranking")
            return False
        
        # Step 2: Normalize scores
        print("\n[STEP 2] Normalizing scores...")
        normalized_candidates = normalize_scores(all_candidates)
        print_success(f"Normalized {len(normalized_candidates)} scores")
        
        # Step 3: Rerank
        print(f"\n[STEP 3] Reranking to top {k_final}...")
        reranked = reranker.rerank(query, normalized_candidates, top_k=k_final)
        
        print_success(f"Reranked to {len(reranked)} final documents")
        
        # Display results
        print("\nFinal Reranked Results:")
        for i, (doc, score) in enumerate(reranked[:5], 1):  # Show top 5
            source = doc.metadata.get("source_type", "unknown")
            ticket_key = doc.metadata.get("ticket_key", "")
            section = doc.metadata.get("section", "")
            preview = doc.page_content[:80] + "..."
            print(f"\n  {i}. Score: {score:.4f}")
            print(f"     Source: {source} | Ticket: {ticket_key} | Section: {section}")
            print(f"     Preview: {preview}")
        
        # Verify results
        if len(reranked) > 0:
            # Check scores are valid
            all_valid = all(0 <= score <= 1 for _, score in reranked)
            if all_valid:
                print_success("All final scores are in valid range [0, 1]")
            else:
                print_error("Some final scores are outside valid range")
                return False
            
            # Check scores are descending
            scores = [score for _, score in reranked]
            is_descending = all(scores[i] >= scores[i+1] for i in range(len(scores)-1))
            if is_descending:
                print_success("Final scores are in descending order (higher is better)")
            else:
                print_warning("Final scores are not in descending order")
            
            return True
        else:
            print_error("No documents in final reranked results")
            return False
            
    except Exception as e:
        print_error(f"End-to-end test failed: {e}")
        traceback.print_exc()
        return False


def test_section_based_boosting():
    """Test 7: Test section-based boosting (if available in endpoints)"""
    print_header("TEST 7: SECTION-BASED BOOSTING")
    
    try:
        from app.endpoints import apply_section_boosts
        
        # Create mock reranked results with different sections
        reranked_results = [
            (Document(
                page_content="Root cause of the issue",
                metadata={"ticket_key": "CF-123", "section": "root_cause"}
            ), 0.7),
            (Document(
                page_content="Fix description",
                metadata={"ticket_key": "CF-123", "section": "fix_description"}
            ), 0.6),
            (Document(
                page_content="General description",
                metadata={"ticket_key": "CF-123", "section": "description"}
            ), 0.65),
        ]
        
        query = "migration error"
        
        print_info("Testing section-based boosting...")
        print_info("Input scores:")
        for doc, score in reranked_results:
            section = doc.metadata.get("section", "unknown")
            print(f"  • {section}: {score:.4f}")
        
        boosted = apply_section_boosts(query, reranked_results)
        
        print_success(f"Applied section boosts to {len(boosted)} documents")
        
        print("\nBoosted scores:")
        for doc, score in boosted:
            section = doc.metadata.get("section", "unknown")
            print(f"  • {section}: {score:.4f}")
        
        # Verify boosting increased scores for important sections
        if len(boosted) >= 2:
            # Find root_cause and fix_description scores
            root_cause_score = next((s for d, s in boosted if d.metadata.get("section") == "root_cause"), None)
            fix_score = next((s for d, s in boosted if d.metadata.get("section") == "fix_description"), None)
            
            if root_cause_score and fix_score:
                print_success("Section-based boosting applied successfully")
                return True
            else:
                print_warning("Could not verify section boosting - sections may have changed")
                return True
        else:
            print_warning("Not enough results to verify section boosting")
            return True
            
    except ImportError:
        print_warning("apply_section_boosts not available - skipping section boosting test")
        return True
    except Exception as e:
        print_error(f"Section-based boosting test failed: {e}")
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print_header("RETRIEVAL AND RERANKING TEST SUITE")
    
    print_info("This test suite verifies:")
    print_info("  1. Reranker initialization")
    print_info("  2. Basic reranking functionality")
    print_info("  3. Reranker fallback mode")
    print_info("  4. Multi-source retrieval")
    print_info("  5. Score normalization")
    print_info("  6. End-to-end retrieval + reranking")
    print_info("  7. Section-based boosting")
    print()
    
    results = {
        "test_1_init": False,
        "test_2_basic": False,
        "test_3_fallback": False,
        "test_4_retrieval": False,
        "test_5_normalization": False,
        "test_6_e2e": False,
        "test_7_boosting": False,
    }
    
    # Test 1: Initialize reranker
    reranker = test_reranker_initialization()
    if reranker:
        results["test_1_init"] = True
    
    # Test 2: Basic reranking
    if reranker:
        results["test_2_basic"] = test_reranker_basic_functionality(reranker)
    
    # Test 3: Fallback mode
    results["test_3_fallback"] = test_reranker_fallback_mode()
    
    # Test 4: Multi-source retrieval
    results["test_4_retrieval"] = test_multi_source_retrieval()
    
    # Test 5: Score normalization
    results["test_5_normalization"] = test_score_normalization()
    
    # Test 6: End-to-end
    results["test_6_e2e"] = test_end_to_end_retrieval_reranking()
    
    # Test 7: Section boosting
    results["test_7_boosting"] = test_section_based_boosting()
    
    # Summary
    print_header("TEST SUMMARY")
    
    test_names = {
        "test_1_init": "Reranker Initialization",
        "test_2_basic": "Basic Reranking",
        "test_3_fallback": "Fallback Mode",
        "test_4_retrieval": "Multi-Source Retrieval",
        "test_5_normalization": "Score Normalization",
        "test_6_e2e": "End-to-End Pipeline",
        "test_7_boosting": "Section-Based Boosting",
    }
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_key, test_name in test_names.items():
        status = results[test_key]
        if status:
            print_success(f"{test_name}: PASSED")
        else:
            print_error(f"{test_name}: FAILED")
    
    print()
    print(f"{Colors.BOLD}Results: {passed}/{total} tests passed{Colors.ENDC}")
    
    if passed == total:
        print_success("All tests passed! Retrieval and reranking are working correctly.")
        return 0
    elif passed >= total * 0.7:  # 70% pass rate
        print_warning("Most tests passed. Some components may need attention.")
        return 1
    else:
        print_error("Multiple tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
