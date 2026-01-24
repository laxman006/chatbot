"""
Comprehensive test to check if Jira Chroma DB is working or corrupted.
Tests multiple aspects: file system, SQLite integrity, ChromaDB loading, and data access.
"""
import os
import sys
import sqlite3
import json
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# Add project root to path
sys.path.insert(0, '.')

# Set environment variable to prevent auto-initialization
os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'

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


def print_warning(text):
    """Print warning message"""
    print(f"{Colors.YELLOW}⚠ {text}{Colors.RESET}")


def print_info(text):
    """Print info message"""
    print(f"{Colors.BLUE}ℹ {text}{Colors.RESET}")


def test_filesystem():
    """Test 1: Check if database directory and files exist"""
    print_header("TEST 1: FILESYSTEM CHECK")
    
    results = {
        'directory_exists': False,
        'sqlite_exists': False,
        'directory_path': None,
        'sqlite_path': None,
        'directory_size': 0,
        'sqlite_size': 0,
        'other_files': []
    }
    
    # Check directory
    db_dir = Path(JIRA_VECTORSTORE_PATH)
    results['directory_path'] = str(db_dir.absolute())
    
    if db_dir.exists():
        results['directory_exists'] = True
        print_success(f"Directory exists: {db_dir.absolute()}")
        
        # Calculate directory size
        total_size = sum(f.stat().st_size for f in db_dir.rglob('*') if f.is_file())
        results['directory_size'] = total_size
        print_info(f"Directory size: {total_size:,} bytes ({total_size / 1024 / 1024:.2f} MB)")
        
        # List files
        files = list(db_dir.rglob('*'))
        print_info(f"Files in directory: {len(files)}")
        for f in files[:10]:  # Show first 10 files
            if f.is_file():
                size = f.stat().st_size
                print(f"  • {f.name}: {size:,} bytes")
                results['other_files'].append({'name': f.name, 'size': size})
        
        # Check SQLite file
        sqlite_path = db_dir / 'chroma.sqlite3'
        results['sqlite_path'] = str(sqlite_path.absolute())
        
        if sqlite_path.exists():
            results['sqlite_exists'] = True
            results['sqlite_size'] = sqlite_path.stat().st_size
            print_success(f"SQLite database exists: {sqlite_path.name}")
            print_info(f"SQLite size: {results['sqlite_size']:,} bytes ({results['sqlite_size'] / 1024 / 1024:.2f} MB)")
        else:
            print_error(f"SQLite database NOT found: {sqlite_path.name}")
    else:
        print_error(f"Directory does NOT exist: {db_dir.absolute()}")
    
    return results


def test_sqlite_integrity():
    """Test 2: Check SQLite database integrity"""
    print_header("TEST 2: SQLITE DATABASE INTEGRITY")
    
    results = {
        'accessible': False,
        'integrity_ok': False,
        'tables': [],
        'embeddings_count': 0,
        'segments_count': 0,
        'collections_count': 0,
        'error': None
    }
    
    db_dir = Path(JIRA_VECTORSTORE_PATH)
    sqlite_path = db_dir / 'chroma.sqlite3'
    
    if not sqlite_path.exists():
        print_error("SQLite database file not found - skipping integrity check")
        results['error'] = "File not found"
        return results
    
    try:
        # Connect to database
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.cursor()
        results['accessible'] = True
        print_success("Database is accessible via SQLite")
        
        # Check integrity
        print_info("Running integrity check...")
        cursor.execute("PRAGMA integrity_check")
        integrity_result = cursor.fetchone()
        
        if integrity_result and integrity_result[0] == 'ok':
            results['integrity_ok'] = True
            print_success("Database integrity check: OK")
        else:
            print_error(f"Database integrity check failed: {integrity_result}")
            results['error'] = f"Integrity check failed: {integrity_result}"
        
        # List tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = cursor.fetchall()
        results['tables'] = [t[0] for t in tables]
        print_info(f"Found {len(tables)} tables:")
        for table in tables:
            print(f"  • {table[0]}")
        
        # Check embeddings table
        if ('embeddings',) in tables:
            cursor.execute("SELECT COUNT(*) FROM embeddings")
            count = cursor.fetchone()[0]
            results['embeddings_count'] = count
            print_info(f"Embeddings table: {count:,} rows")
            
            if count > 0:
                cursor.execute("SELECT * FROM embeddings LIMIT 1")
                sample = cursor.fetchone()
                print_info(f"Sample row has {len(sample) if sample else 0} columns")
        
        # Check segments table
        if ('segments',) in tables:
            cursor.execute("SELECT COUNT(*) FROM segments")
            count = cursor.fetchone()[0]
            results['segments_count'] = count
            print_info(f"Segments table: {count:,} rows")
        
        # Check collections table
        if ('collections',) in tables:
            cursor.execute("SELECT COUNT(*) FROM collections")
            count = cursor.fetchone()[0]
            results['collections_count'] = count
            print_info(f"Collections table: {count:,} rows")
            
            cursor.execute("SELECT id, name FROM collections")
            collections = cursor.fetchall()
            print_info("Collections:")
            for coll in collections:
                print(f"  • {coll[1]} (ID: {coll[0]})")
        
        conn.close()
        
    except sqlite3.Error as e:
        print_error(f"SQLite error: {e}")
        results['error'] = str(e)
        import traceback
        traceback.print_exc()
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        results['error'] = str(e)
        import traceback
        traceback.print_exc()
    
    return results


def test_chromadb_loading():
    """Test 3: Check if ChromaDB can load the vectorstore"""
    print_header("TEST 3: CHROMADB LOADING")
    
    results = {
        'loaded': False,
        'collection_count': 0,
        'sample_docs': [],
        'metadata_keys': set(),
        'error': None,
        'corruption_detected': False
    }
    
    try:
        # Import directly to avoid module-level initialization
        import os
        os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
        
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma
        
        print_info("Attempting to load Jira vectorstore via ChromaDB...")
        
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
        except BaseException as chroma_error:  # Catch all exceptions including PanicException
            error_msg = str(chroma_error)
            error_type = type(chroma_error).__name__
            error_repr = repr(chroma_error)
            
            # Check for common corruption indicators
            corruption_indicators = [
                "range start index",
                "out of range",
                "PanicException",
                "panic",
                "index",
                "slice",
                "pyo3_runtime"
            ]
            
            is_corruption = (
                any(indicator.lower() in error_msg.lower() for indicator in corruption_indicators) or
                any(indicator.lower() in error_repr.lower() for indicator in corruption_indicators) or
                "PanicException" in error_type or
                "panic" in error_type.lower()
            )
            
            if is_corruption:
                results['corruption_detected'] = True
                print_error("ChromaDB index corruption detected!")
                print_error(f"Error type: {error_type}")
                print_error(f"Error message: {error_msg}")
                print_warning("This indicates the HNSW index or vector data is corrupted")
                print_info("The SQLite database is intact, but ChromaDB's index files are corrupted")
                results['error'] = f"Index corruption ({error_type}): {error_msg}"
                return results
            else:
                # Re-raise if it's not a corruption error
                results['error'] = f"{error_type}: {error_msg}"
                raise
        
        if vectorstore:
            results['loaded'] = True
            print_success("ChromaDB loaded vectorstore successfully")
            
            # Get collection count
            try:
                count = vectorstore._collection.count()
                results['collection_count'] = count
                print_success(f"Collection contains {count:,} documents")
                
                # Get sample documents
                if count > 0:
                    print_info("Retrieving sample documents...")
                    sample = vectorstore._collection.get(
                        limit=min(5, count),
                        include=['metadatas', 'documents']  # IDs are always returned automatically
                    )
                    
                    if sample and sample.get('ids'):
                        print_info(f"Retrieved {len(sample['ids'])} sample documents")
                        
                        for i, (doc_id, metadata, doc_text) in enumerate(
                            zip(
                                sample['ids'],
                                sample.get('metadatas', [{}] * len(sample['ids'])),
                                sample.get('documents', [''] * len(sample['ids']))
                            ),
                            1
                        ):
                            results['sample_docs'].append({
                                'id': doc_id[:50] + '...' if len(doc_id) > 50 else doc_id,
                                'metadata': metadata,
                                'text_length': len(doc_text) if doc_text else 0
                            })
                            
                            # Collect metadata keys
                            if metadata:
                                results['metadata_keys'].update(metadata.keys())
                            
                            ticket_key = metadata.get('ticket_key', 'N/A')
                            section = metadata.get('section', 'N/A')
                            print(f"  {i}. Ticket: {ticket_key}, Section: {section}, Text length: {len(doc_text) if doc_text else 0}")
                        
                        print_info(f"Metadata keys found: {', '.join(sorted(results['metadata_keys']))}")
                    else:
                        print_warning("No documents retrieved from collection")
                else:
                    print_warning("Collection is empty")
                    
            except Exception as e:
                print_error(f"Error accessing collection: {e}")
                results['error'] = str(e)
                import traceback
                traceback.print_exc()
        else:
            print_error("Failed to load vectorstore - returned None")
            results['error'] = "load_jira_vectorstore returned None"
            
    except Exception as e:
        print_error(f"Error loading ChromaDB vectorstore: {e}")
        results['error'] = str(e)
        import traceback
        traceback.print_exc()
    
    return results


def test_document_retrieval():
    """Test 4: Test document retrieval functionality"""
    print_header("TEST 4: DOCUMENT RETRIEVAL TEST")
    
    results = {
        'retrieval_works': False,
        'query_results': [],
        'error': None
    }
    
    try:
        # Import directly to avoid module-level initialization
        import os
        os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
        
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma
        
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
        except Exception as e:
            print_error(f"Cannot test retrieval - ChromaDB loading failed: {e}")
            results['error'] = f"ChromaDB loading failed: {e}"
            return results
        
        if not vectorstore:
            print_error("Cannot test retrieval - vectorstore not loaded")
            results['error'] = "Vectorstore not loaded"
            return results
        
        # Test similarity search
        test_queries = [
            "error",
            "bug",
            "migration"
        ]
        
        print_info("Testing similarity search with sample queries...")
        
        for query in test_queries:
            try:
                docs = vectorstore.similarity_search(query, k=3)
                results['query_results'].append({
                    'query': query,
                    'results_count': len(docs),
                    'success': True
                })
                print_success(f"Query '{query}': Found {len(docs)} documents")
                
                if docs:
                    for i, doc in enumerate(docs[:2], 1):
                        metadata = doc.metadata if hasattr(doc, 'metadata') else {}
                        ticket_key = metadata.get('ticket_key', 'N/A')
                        print(f"  {i}. Ticket: {ticket_key}")
                
            except Exception as e:
                print_error(f"Query '{query}' failed: {e}")
                results['query_results'].append({
                    'query': query,
                    'results_count': 0,
                    'success': False,
                    'error': str(e)
                })
        
        if any(r['success'] for r in results['query_results']):
            results['retrieval_works'] = True
            print_success("Document retrieval is working")
        else:
            print_error("Document retrieval failed for all queries")
            
    except Exception as e:
        print_error(f"Error testing retrieval: {e}")
        results['error'] = str(e)
        import traceback
        traceback.print_exc()
    
    return results


def test_cache_comparison():
    """Test 5: Compare vectorstore with cache file"""
    print_header("TEST 5: CACHE COMPARISON")
    
    results = {
        'cache_exists': False,
        'cache_ticket_count': 0,
        'vectorstore_count': 0,
        'match': False,
        'error': None
    }
    
    cache_path = Path('data/jira_tickets_cache.json')
    
    if not cache_path.exists():
        print_warning(f"Cache file not found: {cache_path}")
        results['error'] = "Cache file not found"
        return results
    
    results['cache_exists'] = True
    print_success(f"Cache file exists: {cache_path}")
    
    try:
        # Load cache
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache_data = json.load(f)
            tickets = cache_data.get('tickets', [])
            results['cache_ticket_count'] = len(tickets)
            print_info(f"Cache contains {len(tickets):,} ticket entries")
        
        # Get vectorstore count
        import os
        os.environ['INITIALIZE_JIRA_VECTORSTORE'] = 'false'
        
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma
        
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
        except Exception as e:
            print_error(f"Cannot compare - ChromaDB loading failed: {e}")
            results['error'] = f"ChromaDB loading failed: {e}"
            return results
        
        if vectorstore:
            count = vectorstore._collection.count()
            results['vectorstore_count'] = count
            print_info(f"Vectorstore contains {count:,} documents")
            
            # Compare
            if count == len(tickets):
                results['match'] = True
                print_success("Perfect match: Vectorstore count equals cache count")
            elif count < len(tickets):
                missing = len(tickets) - count
                pct_missing = (missing / len(tickets)) * 100
                print_warning(f"Vectorstore has {missing:,} fewer documents ({pct_missing:.1f}% missing)")
            else:
                extra = count - len(tickets)
                print_warning(f"Vectorstore has {extra:,} more documents than cache")
        else:
            print_error("Cannot compare - vectorstore not loaded")
            results['error'] = "Vectorstore not loaded"
            
    except Exception as e:
        print_error(f"Error comparing cache: {e}")
        results['error'] = str(e)
        import traceback
        traceback.print_exc()
    
    return results


def generate_summary(filesystem_results, sqlite_results, chromadb_results, retrieval_results, cache_results):
    """Generate final summary and recommendations"""
    print_header("FINAL SUMMARY & RECOMMENDATIONS")
    
    # Determine overall status
    status = "UNKNOWN"
    issues = []
    recommendations = []
    
    # Check filesystem
    if not filesystem_results['directory_exists']:
        status = "NOT_FOUND"
        issues.append("Database directory does not exist")
        recommendations.append("Build Jira vectorstore using: python build_jira_vectorstore_all.py")
    elif not filesystem_results['sqlite_exists']:
        status = "INCOMPLETE"
        issues.append("SQLite database file missing")
        recommendations.append("Rebuild Jira vectorstore: python build_jira_vectorstore_all.py")
    else:
        # Check SQLite integrity
        if not sqlite_results['accessible']:
            status = "CORRUPTED"
            issues.append("SQLite database is not accessible")
            recommendations.append("Database may be corrupted - rebuild required")
        elif not sqlite_results['integrity_ok']:
            status = "CORRUPTED"
            issues.append("SQLite integrity check failed")
            recommendations.append("Database is corrupted - rebuild required: python build_jira_vectorstore_all.py")
        else:
            # Check ChromaDB loading
            if chromadb_results.get('corruption_detected'):
                status = "CORRUPTED"
                issues.append("ChromaDB index corruption detected (HNSW index or vector data corrupted)")
                issues.append("SQLite database is intact, but ChromaDB cannot load the index")
                recommendations.append("REBUILD REQUIRED: python build_jira_vectorstore_all.py")
                recommendations.append("The SQLite data is fine, but the HNSW index files are corrupted")
            elif not chromadb_results['loaded']:
                status = "CORRUPTED"
                issues.append("ChromaDB cannot load the vectorstore")
                if chromadb_results.get('error'):
                    issues.append(f"Error: {chromadb_results['error']}")
                recommendations.append("Database may be corrupted - rebuild required: python build_jira_vectorstore_all.py")
            elif chromadb_results['collection_count'] == 0:
                status = "EMPTY"
                issues.append("Vectorstore is empty")
                recommendations.append("Rebuild Jira vectorstore: python build_jira_vectorstore_all.py")
            else:
                # Check retrieval
                if not retrieval_results['retrieval_works']:
                    status = "DEGRADED"
                    issues.append("Document retrieval is not working")
                    recommendations.append("Vectorstore may be corrupted - consider rebuilding")
                else:
                    status = "WORKING"
                    print_success("✓ Database is WORKING correctly!")
    
    # Print status
    print(f"\n{Colors.BOLD}STATUS: {status}{Colors.RESET}\n")
    
    if issues:
        print(f"{Colors.RED}ISSUES FOUND:{Colors.RESET}")
        for issue in issues:
            print(f"  • {issue}")
        print()
    
    if recommendations:
        print(f"{Colors.YELLOW}RECOMMENDATIONS:{Colors.RESET}")
        for rec in recommendations:
            print(f"  • {rec}")
        print()
    
    # Print statistics
    if status == "WORKING":
        print(f"{Colors.GREEN}Database Statistics:{Colors.RESET}")
        print(f"  • Total documents: {chromadb_results['collection_count']:,}")
        print(f"  • SQLite size: {filesystem_results['sqlite_size'] / 1024 / 1024:.2f} MB")
        print(f"  • Directory size: {filesystem_results['directory_size'] / 1024 / 1024:.2f} MB")
        if cache_results.get('cache_exists'):
            print(f"  • Cache entries: {cache_results['cache_ticket_count']:,}")
            if cache_results.get('match'):
                print(f"  • Status: Perfect match with cache")
    
    return status


def main():
    """Run all tests"""
    print_header("JIRA CHROMA DB HEALTH CHECK")
    
    print_info(f"Database path: {JIRA_VECTORSTORE_PATH}")
    print_info(f"Jira vectorstore enabled: {ENABLE_JIRA_VECTORSTORE}")
    print()
    
    # Run all tests
    filesystem_results = test_filesystem()
    sqlite_results = test_sqlite_integrity()
    chromadb_results = test_chromadb_loading()
    retrieval_results = test_document_retrieval()
    cache_results = test_cache_comparison()
    
    # Generate summary
    status = generate_summary(
        filesystem_results,
        sqlite_results,
        chromadb_results,
        retrieval_results,
        cache_results
    )
    
    print_header("TEST COMPLETE")
    
    # Exit code
    if status == "WORKING":
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(130)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
