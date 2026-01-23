"""
Comprehensive Multi-Source Data Analysis
Analyzes blogs, SharePoint, Jira, and other sources to understand data types,
content patterns, and metadata for improving intelligent routing.
"""
import sys
import os
from collections import defaultdict
import json

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

def analyze_data_sources():
    """Analyze all data sources in vectorstore and Jira vectorstore."""
    print("=" * 80)
    print(" MULTI-SOURCE DATA ANALYSIS FOR INTELLIGENT ROUTING")
    print("=" * 80)
    
    results = {
        "main_vectorstore": analyze_main_vectorstore(),
        "jira_vectorstore": analyze_jira_vectorstore()
    }
    
    # Print recommendations
    print_routing_recommendations(results)
    
    return results


def analyze_main_vectorstore():
    """Analyze the main vectorstore (blogs, SharePoint, PDFs, etc.)."""
    print("\n" + "=" * 80)
    print(" MAIN VECTORSTORE ANALYSIS")
    print("=" * 80)
    
    try:
        # Use direct ChromaDB client without HNSW to avoid corruption issues
        print("[*] Attempting to load vectorstore with basic client...")
        
        from langchain_openai import OpenAIEmbeddings
        from langchain_chroma import Chroma
        from config import CHROMA_DB_PATH
        
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        vectorstore = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings,
            collection_metadata={"hnsw:space": "cosine"}
        )
        
        if not vectorstore:
            print("[ERROR] Main vectorstore not initialized")
            return None
        
        # Get count first
        try:
            total_count = vectorstore._collection.count()
            print(f"[OK] Total documents in vectorstore: {total_count}")
        except Exception as e:
            print(f"[WARNING] Could not get count: {e}")
            total_count = 0
        
        # Get sample documents instead of all
        print("[*] Loading sample documents for analysis...")
        
        # Use similarity search with different queries to sample different sources
        all_docs = []
        queries = ["blog migration", "sharepoint certificate", "jira error", "pdf documentation", "transcript sales"]
        
        for query in queries:
            try:
                docs = vectorstore.similarity_search(query, k=100)
                all_docs.extend(docs)
                print(f"[*] Sampled {len(docs)} docs for '{query}'")
            except Exception as e:
                print(f"[WARNING] Failed to query '{query}': {e}")
        
        # Extract metadatas and documents
        metadatas = [doc.metadata for doc in all_docs]
        documents = [doc.page_content for doc in all_docs]
        
        sampled_docs = len(metadatas)
        print(f"[OK] Sampled {sampled_docs} documents for analysis (Total in DB: {total_count})")
        
        # Analyze by source
        analysis = {
            "total_documents": total_count,
            "sampled_documents": sampled_docs,
            "by_source": defaultdict(lambda: {
                "count": 0,
                "samples": [],
                "content_types": defaultdict(int),
                "tags": defaultdict(int),
                "metadata_fields": set()
            })
        }
        
        # Categorize each document
        for i, (metadata, content) in enumerate(zip(metadatas, documents)):
            if not metadata:
                continue
            
            # Determine source category
            source_type = metadata.get("source_type", "unknown")
            tag = metadata.get("tag", "unknown")
            source = metadata.get("source", "unknown")
            
            # Categorize
            if metadata.get("is_blog_post") or tag == "blog" or source_type == "web":
                category = "blog"
            elif "sharepoint" in source_type.lower() or "sharepoint" in source.lower():
                category = "sharepoint"
            elif "pdf" in source_type.lower() or "pdf" in str(metadata.get("file_name", "")).lower():
                category = "pdfs"
            elif "transcript" in source_type.lower() or "transcript" in tag.lower():
                category = "transcripts"
            elif "excel" in source_type.lower() or "xlsx" in str(metadata.get("file_name", "")).lower():
                category = "excel"
            elif "email" in source_type.lower() or "outlook" in source_type.lower():
                category = "email"
            else:
                category = "other"
            
            # Update analysis
            cat_data = analysis["by_source"][category]
            cat_data["count"] += 1
            
            # Store sample if we have less than 3
            if len(cat_data["samples"]) < 3:
                cat_data["samples"].append({
                    "content_preview": content[:300] + "..." if len(content) > 300 else content,
                    "metadata": metadata,
                    "length": len(content)
                })
            
            # Track content types
            content_type = metadata.get("content_type", "unknown")
            cat_data["content_types"][content_type] += 1
            
            # Track tags
            cat_data["tags"][tag] += 1
            
            # Track metadata fields
            cat_data["metadata_fields"].update(metadata.keys())
        
        # Print detailed analysis for each source
        print("\n" + "-" * 80)
        print(" SOURCE BREAKDOWN")
        print("-" * 80)
        
        for category in ["blog", "sharepoint", "pdfs", "transcripts", "excel", "email", "other"]:
            if category not in analysis["by_source"]:
                continue
            
            cat_data = analysis["by_source"][category]
            count = cat_data["count"]
            percentage = (count / sampled_docs * 100) if sampled_docs > 0 else 0
            
            print(f"\n📦 {category.upper()}")
            print(f"   Sampled chunks: {count} ({percentage:.1f}% of sample)")
            
            # Content types
            if cat_data["content_types"]:
                print(f"   Content types:")
                for ctype, ccount in sorted(cat_data["content_types"].items(), 
                                          key=lambda x: x[1], reverse=True)[:5]:
                    print(f"     - {ctype}: {ccount}")
            
            # Tags
            if cat_data["tags"]:
                print(f"   Tags (top 5):")
                for tag, tcount in sorted(cat_data["tags"].items(), 
                                        key=lambda x: x[1], reverse=True)[:5]:
                    print(f"     - {tag}: {tcount}")
            
            # Metadata fields
            if cat_data["metadata_fields"]:
                print(f"   Metadata fields: {', '.join(sorted(cat_data['metadata_fields'])[:10])}")
            
            # Sample documents
            if cat_data["samples"]:
                print(f"   Sample documents:")
                for idx, sample in enumerate(cat_data["samples"], 1):
                    print(f"     Sample {idx}:")
                    print(f"       Length: {sample['length']} chars")
                    print(f"       Preview: {sample['content_preview'][:150]}...")
                    
                    # Show key metadata
                    meta = sample['metadata']
                    if 'post_title' in meta:
                        print(f"       Title: {meta['post_title']}")
                    if 'post_url' in meta:
                        print(f"       URL: {meta['post_url']}")
                    if 'file_name' in meta:
                        print(f"       File: {meta['file_name']}")
                    if 'folder_path' in meta:
                        print(f"       Path: {meta['folder_path']}")
                    print()
        
        return analysis
        
    except Exception as e:
        print(f"[ERROR] Failed to analyze main vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return None


def analyze_jira_vectorstore():
    """Analyze the Jira vectorstore."""
    print("\n" + "=" * 80)
    print(" JIRA VECTORSTORE ANALYSIS")
    print("=" * 80)
    
    try:
        from app.jira_vectorstore import load_jira_vectorstore
        
        jira_vs = load_jira_vectorstore()
        if not jira_vs:
            print("[WARNING] Jira vectorstore not initialized")
            return None
        
        # Get all documents
        print("[*] Loading Jira vectorstore data...")
        all_data = jira_vs.get(include=["metadatas", "documents"])
        metadatas = all_data.get("metadatas", [])
        documents = all_data.get("documents", [])
        
        total_docs = len(metadatas)
        print(f"[OK] Total Jira documents: {total_docs}")
        
        # Analyze Jira tickets
        analysis = {
            "total_documents": total_docs,
            "unique_tickets": set(),
            "by_project": defaultdict(int),
            "by_status": defaultdict(int),
            "by_section": defaultdict(int),
            "by_combination": defaultdict(int),
            "samples": []
        }
        
        for i, (metadata, content) in enumerate(zip(metadatas, documents)):
            if not metadata:
                continue
            
            # Track ticket
            ticket_key = metadata.get("ticket_key", "unknown")
            analysis["unique_tickets"].add(ticket_key)
            
            # Track project
            project_key = metadata.get("project_key", "unknown")
            analysis["by_project"][project_key] += 1
            
            # Track status
            status = metadata.get("status", "unknown")
            analysis["by_status"][status] += 1
            
            # Track section
            section = metadata.get("section", "unknown")
            analysis["by_section"][section] += 1
            
            # Track combination (migration type)
            combination = metadata.get("combination", "unknown")
            if combination and combination != "unknown":
                analysis["by_combination"][combination] += 1
            
            # Store samples
            if len(analysis["samples"]) < 5:
                analysis["samples"].append({
                    "ticket_key": ticket_key,
                    "summary": metadata.get("ticket_summary", ""),
                    "section": section,
                    "combination": combination,
                    "status": status,
                    "content_preview": content[:300] + "..." if len(content) > 300 else content,
                    "has_root_cause": bool(metadata.get("root_cause")),
                    "has_fix": bool(metadata.get("fix_description"))
                })
        
        # Print analysis
        print(f"\n📊 JIRA STATISTICS")
        print(f"   Unique tickets: {len(analysis['unique_tickets'])}")
        print(f"   Total chunks: {total_docs}")
        print(f"   Avg chunks per ticket: {total_docs / len(analysis['unique_tickets']):.1f}")
        
        print(f"\n   By Project:")
        for proj, count in sorted(analysis["by_project"].items(), 
                                 key=lambda x: x[1], reverse=True)[:10]:
            print(f"     {proj}: {count} chunks")
        
        print(f"\n   By Status:")
        for status, count in sorted(analysis["by_status"].items(), 
                                   key=lambda x: x[1], reverse=True):
            print(f"     {status}: {count} chunks")
        
        print(f"\n   By Section:")
        for section, count in sorted(analysis["by_section"].items(), 
                                    key=lambda x: x[1], reverse=True):
            print(f"     {section}: {count} chunks")
        
        print(f"\n   By Migration Type:")
        for combo, count in sorted(analysis["by_combination"].items(), 
                                  key=lambda x: x[1], reverse=True)[:10]:
            if combo and combo != "unknown":
                print(f"     {combo}: {count} chunks")
        
        print(f"\n   Sample Tickets:")
        for idx, sample in enumerate(analysis["samples"], 1):
            print(f"     {idx}. {sample['ticket_key']} - {sample['summary'][:60]}...")
            print(f"        Section: {sample['section']} | Status: {sample['status']}")
            print(f"        Migration: {sample['combination']}")
            print(f"        Has root cause: {sample['has_root_cause']} | Has fix: {sample['has_fix']}")
            print()
        
        return analysis
        
    except Exception as e:
        print(f"[ERROR] Failed to analyze Jira vectorstore: {e}")
        import traceback
        traceback.print_exc()
        return None


def print_routing_recommendations(results):
    """Print recommendations for improving intelligent routing based on analysis."""
    print("\n" + "=" * 80)
    print(" RECOMMENDATIONS FOR INTELLIGENT ROUTING")
    print("=" * 80)
    
    main_vs = results.get("main_vectorstore")
    jira_vs = results.get("jira_vectorstore")
    
    if not main_vs:
        print("[WARNING] Cannot provide recommendations without main vectorstore analysis")
        return
    
    print("\n📝 SYSTEM PROMPT IMPROVEMENTS:")
    print()
    
    # Analyze blog content
    if "blog" in main_vs["by_source"]:
        blog_data = main_vs["by_source"]["blog"]
        print(f"1. BLOG SOURCE ({blog_data['count']} chunks)")
        print(f"   Current description: 'Marketing blog posts, product announcements...'")
        print(f"   Data found:")
        
        # Check actual content types
        top_tags = sorted(blog_data["tags"].items(), key=lambda x: x[1], reverse=True)[:5]
        print(f"   - Top tags: {', '.join([t[0] for t in top_tags])}")
        
        print(f"   Recommended description update:")
        print(f"   'Marketing blog posts, migration guides, how-to articles, product features,")
        print(f"    best practices, use cases. Good for: general product questions, migration")
        print(f"    setup, feature overviews, conceptual understanding.'")
        print()
    
    # Analyze SharePoint content
    if "sharepoint" in main_vs["by_source"]:
        sp_data = main_vs["by_source"]["sharepoint"]
        print(f"2. SHAREPOINT SOURCE ({sp_data['count']} chunks)")
        print(f"   Current description: 'Internal documentation, policies, SOC certificates...'")
        print(f"   Data found:")
        
        top_content_types = sorted(sp_data["content_types"].items(), 
                                  key=lambda x: x[1], reverse=True)[:5]
        print(f"   - Content types: {', '.join([t[0] for t in top_content_types])}")
        
        print(f"   Recommended weight adjustments:")
        print(f"   - For 'SOC', 'compliance', 'certificate', 'security' → weight: 0.9-1.0")
        print(f"   - For 'policy', 'internal', 'documentation' → weight: 0.7-0.9")
        print()
    
    # Analyze Jira content
    if jira_vs:
        print(f"3. JIRA SOURCE ({jira_vs['total_documents']} chunks, "
              f"{len(jira_vs['unique_tickets'])} tickets)")
        print(f"   Current description: 'Resolved tickets with bug fixes, error resolutions...'")
        print(f"   Data found:")
        
        top_combos = sorted(jira_vs["by_combination"].items(), 
                          key=lambda x: x[1], reverse=True)[:5]
        print(f"   - Top migration types: {', '.join([c[0] for c in top_combos if c[0] != 'unknown'])}")
        
        top_sections = sorted(jira_vs["by_section"].items(), 
                            key=lambda x: x[1], reverse=True)
        print(f"   - Sections: {', '.join([s[0] for s in top_sections])}")
        
        print(f"   Recommended weight adjustments:")
        print(f"   - For error messages/logs (exact match) → weight: 1.0")
        print(f"   - For 'failed', 'error', 'not working' → weight: 0.8-0.9")
        print(f"   - For 'migration issue' + combination mention → weight: 0.7-0.8")
        print(f"   - For general 'how to' with migration context → weight: 0.4-0.6")
        print()
    
    # Check other sources
    if "pdfs" in main_vs["by_source"]:
        pdf_data = main_vs["by_source"]["pdfs"]
        print(f"4. PDF SOURCE ({pdf_data['count']} chunks)")
        print(f"   Recommended for: technical deep-dives, API documentation, detailed specs")
        print()
    
    if "transcripts" in main_vs["by_source"]:
        trans_data = main_vs["by_source"]["transcripts"]
        print(f"5. TRANSCRIPTS SOURCE ({trans_data['count']} chunks)")
        print(f"   Recommended for: sales scenarios, customer objections, real conversations")
        print()
    
    if "excel" in main_vs["by_source"]:
        excel_data = main_vs["by_source"]["excel"]
        print(f"6. EXCEL SOURCE ({excel_data['count']} chunks)")
        print(f"   Recommended for: pricing, feature comparisons, structured data")
        print()
    
    print("\n💡 QUERY INTENT DETECTION IMPROVEMENTS:")
    print()
    print("Based on the query from terminal:")
    print("'if during a on-going migration the csv needs to be changed...'")
    print()
    print("Current routing: blog (k=20, 0.70), pdfs (k=10, 0.30) → Retrieved 0 docs")
    print()
    print("Recommended routing for this query:")
    print("  - Type: 'migration_procedure'")
    print("  - blog: k=25, relevance=0.8 (migration guides, how-to)")
    print("  - jira: k=15, relevance=0.6 (past similar issues/workarounds)")
    print("  - pdfs: k=10, relevance=0.5 (technical documentation)")
    print()
    print("Keywords to detect 'migration_procedure' queries:")
    print("  - 'during migration', 'ongoing migration', 'in progress'")
    print("  - 'csv', 'file', 'data', 'change', 'modify', 'update'")
    print("  - 'should we', 'how to', 'best practice'")
    print()
    
    print("\n🎯 ACTION ITEMS:")
    print("1. Add 'migration_procedure' as a new query_type in intelligent_router.py")
    print("2. Update system prompt with refined source descriptions (see above)")
    print("3. Add query understanding patterns for ongoing migration scenarios")
    print("4. Adjust relevance weights based on actual data distribution")
    print("5. Test with common query patterns to validate routing decisions")
    print()
    
    # Export detailed analysis
    export_path = "data_source_analysis_results.json"
    try:
        with open(export_path, 'w', encoding='utf-8') as f:
            # Convert sets to lists for JSON serialization
            export_data = {}
            if main_vs:
                main_export = dict(main_vs)
                for cat in main_export.get("by_source", {}).values():
                    if "metadata_fields" in cat:
                        cat["metadata_fields"] = list(cat["metadata_fields"])
                export_data["main_vectorstore"] = main_export
            
            if jira_vs:
                jira_export = dict(jira_vs)
                jira_export["unique_tickets"] = list(jira_vs["unique_tickets"])
                export_data["jira_vectorstore"] = jira_export
            
            json.dump(export_data, f, indent=2, default=str)
        print(f"✅ Detailed analysis exported to: {export_path}")
    except Exception as e:
        print(f"⚠️  Could not export analysis: {e}")


if __name__ == "__main__":
    analyze_data_sources()
