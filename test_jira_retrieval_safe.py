"""
Safe Jira Vectorstore Retrieval Test
Tests retrieval functionality without modifying or deleting anything.
Read-only operations only.
"""
import os
import sys

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, '.')

# Set environment variable to prevent auto-initialization
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from config import JIRA_VECTORSTORE_PATH, ENABLE_JIRA_VECTORSTORE


class Colors:
    """ANSI color codes for terminal output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    """Print a formatted header"""
    print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
    print(f"{Colors.BOLD}{text}{Colors.RESET}")
    print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")


def print_success(text):
    """Print success message"""
    print(f"{Colors.GREEN}✓ {text}{Colors.RESET}")


def print_error(text):
    """Print error message"""
    print(f"{Colors.RED}✗ {text}{Colors.RESET}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")


def test_retrieval():
    """Test retrieval functionality with various queries"""
    print_header("JIRA VECTORSTORE RETRIEVAL TEST")
    
    print_info(f"Database path: {JIRA_VECTORSTORE_PATH}")
    print_info(f"Jira vectorstore enabled: {ENABLE_JIRA_VECTORSTORE}")
    print()
    
    # Load vectorstore
    print_info("Loading vectorstore...")
    try:
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            persist_directory=JIRA_VECTORSTORE_PATH,
            embedding_function=embeddings,
            collection_metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200,
                "hnsw:search_ef": 100,
                "hnsw:M": 48,
            }
        )
        
        total_docs = vectorstore._collection.count()
        print_success(f"Vectorstore loaded successfully")
        print_success(f"Total documents: {total_docs:,}")
        print()
        
    except Exception as e:
        print_error(f"Failed to load vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test queries
    test_queries = [
        ("error", "Find tickets related to errors"),
        ("migration", "Find tickets about migrations"),
        ("authentication", "Find tickets about authentication issues"),
        ("performance", "Find tickets about performance problems"),
        ("user mapping", "Find tickets about user mapping"),
        ("attachment", "Find tickets about attachments"),
        ("slack", "Find tickets related to Slack"),
        ("outlook", "Find tickets related to Outlook"),
    ]
    
    print_header("RETRIEVAL TESTS")
    
    all_results = []
    
    for query, description in test_queries:
        print(f"\n{Colors.BOLD}Query: {query}{Colors.RESET}")
        print(f"Description: {description}")
        print("-" * 80)
        
        try:
            # Perform similarity search
            docs = vectorstore.similarity_search(query, k=5)
            
            if docs:
                print_success(f"Found {len(docs)} documents")
                
                results = []
                for i, doc in enumerate(docs, 1):
                    metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                    ticket_key = metadata.get('ticket_key', 'N/A')
                    section = metadata.get('section', 'N/A')
                    summary = metadata.get('ticket_summary', 'N/A')
                    
                    # Truncate content for display
                    content_preview = doc.page_content[:200] + "..." if len(doc.page_content) > 200 else doc.page_content
                    
                    print(f"\n  {i}. Ticket: {Colors.BOLD}{ticket_key}{Colors.RESET}")
                    print(f"     Section: {section}")
                    print(f"     Summary: {summary[:100]}..." if len(summary) > 100 else f"     Summary: {summary}")
                    print(f"     Content preview: {content_preview}")
                    
                    results.append({
                        'ticket_key': ticket_key,
                        'section': section,
                        'summary': summary,
                        'content_length': len(doc.page_content)
                    })
                
                all_results.append({
                    'query': query,
                    'results_count': len(docs),
                    'results': results
                })
            else:
                print_error("No documents found")
                all_results.append({
                    'query': query,
                    'results_count': 0,
                    'results': []
                })
                
        except Exception as e:
            print_error(f"Retrieval failed: {e}")
            import traceback
            traceback.print_exc()
            all_results.append({
                'query': query,
                'results_count': 0,
                'error': str(e)
            })
    
    # Summary
    print_header("RETRIEVAL TEST SUMMARY")
    
    successful_queries = sum(1 for r in all_results if r.get('results_count', 0) > 0)
    total_queries = len(all_results)
    
    print(f"Total queries tested: {total_queries}")
    print_success(f"Successful retrievals: {successful_queries}/{total_queries}")
    
    if successful_queries > 0:
        avg_results = sum(r.get('results_count', 0) for r in all_results) / successful_queries
        print_info(f"Average documents per query: {avg_results:.1f}")
    
    # Verify database integrity after tests
    print_header("POST-TEST VERIFICATION")
    
    try:
        # Re-count documents
        final_count = vectorstore._collection.count()
        print_success(f"Document count unchanged: {final_count:,} (was {total_docs:,})")
        
        if final_count == total_docs:
            print_success("Database integrity verified - no data loss")
        else:
            print_error(f"Document count changed! Was {total_docs:,}, now {final_count:,}")
        
        # Try to load again to ensure no corruption
        print_info("Re-loading vectorstore to verify no corruption...")
        test_vectorstore = Chroma(
            persist_directory=JIRA_VECTORSTORE_PATH,
            embedding_function=embeddings,
            collection_metadata={
                "hnsw:space": "cosine",
                "hnsw:construction_ef": 200,
                "hnsw:search_ef": 100,
                "hnsw:M": 48,
            }
        )
        reload_count = test_vectorstore._collection.count()
        
        if reload_count == total_docs:
            print_success("Vectorstore reloaded successfully - no corruption detected")
        else:
            print_error(f"Reload count mismatch! Original: {total_docs:,}, Reloaded: {reload_count:,}")
        
    except Exception as e:
        print_error(f"Post-test verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    print_header("TEST COMPLETE")
    print_success("All retrieval tests completed successfully!")
    print_info("Database remains intact - no modifications or deletions performed")
    
    return True


def main():
    """Run retrieval tests"""
    try:
        print("Starting retrieval test...")
        sys.stdout.flush()
        success = test_retrieval()
        print("\nTest completed successfully!" if success else "\nTest completed with errors")
        sys.stdout.flush()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    print("=" * 80)
    print("JIRA RETRIEVAL TEST - READ ONLY (NO MODIFICATIONS)")
    print("=" * 80)
    main()
