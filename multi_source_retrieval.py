# -*- coding: utf-8 -*-
"""
Multi-Source Retrieval Helpers

Provides functions for retrieving documents from multiple knowledge sources
and combining them intelligently.
"""

from typing import List, Tuple, Dict, Optional
from langchain_core.documents import Document
from collections import defaultdict


def chroma_where(**kwargs):
    """
    Helper function to create ChromaDB-compatible where filters.
    
    ChromaDB requires multi-field filters to use $and operator.
    This function automatically formats filters correctly.
    
    Args:
        **kwargs: Filter field-value pairs (e.g., source_type="web", tag="blog")
    
    Returns:
        None if no filters provided, single field dict if one field, or $and dict if multiple fields
    
    Example:
        chroma_where(source_type="web", tag="blog")
        # Returns: {"$and": [{"source_type": "web"}, {"tag": "blog"}]}
    """
    items = [{k: v} for k, v in kwargs.items() if v is not None]
    if len(items) == 0:
        return None
    if len(items) == 1:
        return items[0]
    return {"$and": items}


def retrieve_from_source(
    vectorstore,
    query: str, 
    source_type: str, 
    k: int,
    filter_field: str = "source_type"
) -> List[Tuple[Document, float]]:
    """
    Retrieve documents from specific source with metadata filtering.
    
    Uses flexible multi-strategy filtering to handle different metadata schemas.
    
    Args:
        vectorstore: ChromaDB vectorstore instance
        query: User query string
        source_type: Source type (blog, sharepoint, pdf, transcript, excel)
        k: Number of documents to retrieve
        filter_field: Metadata field to filter on (default: "source_type")
    
    Returns:
        List of (document, score) tuples where score is distance (lower=better)
    """
    
    if not vectorstore or k == 0:
        return []
    
    try:
        # Map source types to MULTIPLE possible metadata filter strategies
        # Try each strategy in order until we get results
        source_filter_strategies = {
            "blog": [
                chroma_where(source_type="web", tag="blog"),  # Primary: blog posts are tagged as "web"
                chroma_where(tag="blog"),                      # Fallback: tag only
                chroma_where(source="cloudfuze_blog"),        # Fallback: source field
            ],
            "sharepoint": [
                {"source_type": "sharepoint"},           # Primary
                {"source": "sharepoint"},                # Fallback
            ],
            "pdf": [
                {"source_type": "pdf"},                  # Primary
                {"source": "pdf"},                       # Fallback
            ],
            "transcript": [
                {"kb_tier": "secondary"},                # Primary: Transcripts are secondary KB
                {"source_type": "transcript"},           # Fallback
                {"tag": "transcript"},                   # Fallback
            ],
            "excel": [
                {"source_type": "excel"},                # Primary
                {"source": "excel"},                     # Fallback
            ]
        }
        
        strategies = source_filter_strategies.get(source_type, [])
        
        if not strategies:
            print(f"[WARN] No filter strategies for source_type={source_type}, searching without filter")
            results = vectorstore.similarity_search_with_score(query, k=k*2)  # Get more for post-filtering
            return [(doc, float(dist)) for doc, dist in results]
        
        # Try each filter strategy until we get results
        results = []
        for i, filter_dict in enumerate(strategies):
            try:
                print(f"[RETRIEVAL] Trying filter strategy {i+1}/{len(strategies)} for '{source_type}': {filter_dict}")
                results = vectorstore.similarity_search_with_score(
                    query, 
                    k=k,
                    filter=filter_dict
                )
                
                if results:
                    print(f"[RETRIEVAL] ✓ Strategy {i+1} succeeded: retrieved {len(results)} documents")
                    break
                else:
                    print(f"[RETRIEVAL] ✗ Strategy {i+1} returned 0 documents, trying next...")
                    
            except Exception as strategy_error:
                # Note: This is the MAIN vectorstore (blog/sharepoint/pdfs), not capabilities ChromaDB.
                # "Error finding id" / "Internal error" can occur with some Chroma versions when using
                # metadata filters; fallback (unfiltered + post-filter) still returns docs.
                print(f"[RETRIEVAL] ✗ Strategy {i+1} failed with error: {strategy_error}, trying next...")
                continue
        
        # If no strategy worked, try unfiltered search with post-filtering
        if not results:
            print(f"[RETRIEVAL] All filter strategies failed for '{source_type}', trying unfiltered search with post-filtering...")
            try:
                all_results = vectorstore.similarity_search_with_score(query, k=k*3)  # Get 3x to have room for filtering
                
                # Post-filter by checking metadata keywords
                post_filter_keywords = {
                    "blog": ["blog", "wordpress", "cloudfuze.com", "web"],
                    "sharepoint": ["sharepoint"],
                    "pdf": ["pdf"],
                    "transcript": ["transcript", "secondary"],
                    "excel": ["excel", "xlsx"]
                }
                
                keywords = post_filter_keywords.get(source_type, [])
                for doc, dist in all_results:
                    # Check if any keyword appears in metadata values
                    metadata_str = " ".join(str(v).lower() for v in doc.metadata.values())
                    if any(kw in metadata_str for kw in keywords):
                        results.append((doc, dist))
                        if len(results) >= k:
                            break
                
                if results:
                    print(f"[RETRIEVAL] ✓ Post-filtering succeeded: {len(results)} documents matched")
                else:
                    print(f"[RETRIEVAL] ✗ Post-filtering found no matches for '{source_type}'")
                    
            except Exception as post_filter_error:
                print(f"[RETRIEVAL] ✗ Post-filtering failed: {post_filter_error}")
        
        return [(doc, float(dist)) for doc, dist in results]
        
    except Exception as e:
        print(f"[ERROR] Retrieval from {source_type} failed completely: {e}")
        import traceback
        traceback.print_exc()
        return []


def retrieve_from_jira(
    jira_vectorstore,
    query: str,
    k: int
) -> List[Tuple[Document, float]]:
    """
    Retrieve documents from Jira vectorstore.
    
    Args:
        jira_vectorstore: Jira-specific vectorstore instance
        query: User query
        k: Number of tickets to retrieve
        
    Returns:
        List of (document, score) tuples
    """
    if not jira_vectorstore or k == 0:
        return []
    
    try:
        results = jira_vectorstore.similarity_search_with_score(query, k=k)
        return [(doc, float(dist)) for doc, dist in results]
    except Exception as e:
        print(f"[WARN] Jira retrieval failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def retrieve_limitations_documents(
    vectorstore,
    query: str,
    k: int = 4
) -> List[Tuple[Document, float]]:
    """
    ALWAYS retrieve limitations documents regardless of query.
    This ensures limitations/features/support questions get correct answers.
    
    Uses doc_type="limitations" as primary filter (most reliable).
    
    Args:
        vectorstore: Main vectorstore instance
        query: User query (used for semantic search, kept clean)
        k: Number of limitations documents to retrieve (default: 4)
    
    Returns:
        List of (document, score) tuples from limitations source
    """
    if not vectorstore or k == 0:
        return []
    
    try:
        # ✅ CHECK 2: Use strongest filter first (source_type is most reliable)
        # PRIMARY: Filter by source_type (strongest, most reliable)
        # FALLBACK: Try other metadata fields if source_type doesn't exist
        filter_strategies = [
            {"source_type": "sharepoint_limitations"},      # Primary: strongest filter
            {"doc_type": "limitations"},                    # Fallback: doc_type
            {"is_limitations_doc": True},                   # Fallback: explicit flag
            chroma_where(tag="sharepoint_limitations"),      # Fallback: tag filter
        ]
        
        results = []
        search_query = query  # Keep query clean for semantic relevance
        
        # Try each filter strategy until we get results
        for i, filter_dict in enumerate(filter_strategies):
            try:
                print(f"[LIMITATIONS] Trying filter strategy {i+1}/{len(filter_strategies)}: {filter_dict}")
                results = vectorstore.similarity_search_with_score(
                    search_query,
                    k=k,
                    filter=filter_dict
                )
                
                if results:
                    print(f"[LIMITATIONS] ✓ Strategy {i+1} succeeded: retrieved {len(results)} limitations documents")
                    break
                else:
                    print(f"[LIMITATIONS] ✗ Strategy {i+1} returned 0 documents, trying next...")
                    
            except Exception as strategy_error:
                print(f"[LIMITATIONS] ✗ Strategy {i+1} failed with error: {strategy_error}, trying next...")
                continue
        
        # If no filtered results, try fallback query with post-filtering
        if not results:
            print("[LIMITATIONS] All filter strategies failed, trying fallback query with post-filtering...")
            try:
                # Use a stable fallback query for limitations topics
                fallback_query = "limitations supported features not supported"
                all_results = vectorstore.similarity_search_with_score(
                    fallback_query, 
                    k=k*3
                )
                
                # Post-filter for limitations keywords in metadata or content
                for doc, dist in all_results:
                    metadata_str = " ".join(str(v).lower() for v in doc.metadata.values())
                    content_str = doc.page_content.lower()
                    
                    keywords = ["limitations", "sharepoint_limitations", "features", "supported", "not supported"]
                    if any(kw in metadata_str or kw in content_str for kw in keywords):
                        results.append((doc, dist))
                        if len(results) >= k:
                            break
                
                if results:
                    print(f"[LIMITATIONS] ✓ Post-filtering found {len(results)} limitations documents")
                else:
                    print(f"[LIMITATIONS] ✗ Post-filtering found no matches")
                    
            except Exception as post_error:
                print(f"[LIMITATIONS] ✗ Post-filtering failed: {post_error}")
        
        return [(doc, float(dist)) for doc, dist in results]
        
    except Exception as e:
        print(f"[ERROR] Limitations retrieval failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def deduplicate_by_content(
    candidates: List[Tuple[Document, float]],
    fingerprint_length: int = 400
) -> List[Tuple[Document, float]]:
    """
    Remove duplicate documents based on content similarity or unique identifiers.
    
    IMPORTANT: Jira tickets are NEVER deduplicated - all tickets are kept.
    Only non-Jira documents are deduplicated based on content fingerprint.
    
    Strategy:
    - For Jira tickets: NEVER deduplicate - keep all tickets (even if same ticket_key)
    - For other sources: Use content fingerprint (first N characters)
    
    Args:
        candidates: List of (document, score) tuples
        fingerprint_length: Number of characters to use for content fingerprint (default: 400)
        
    Returns:
        Deduplicated list (Jira tickets always kept, other sources deduplicated)
    """
    seen_keys = {}
    deduplicated = []
    jira_count = 0
    content_dedup_count = 0
    
    for doc, score in candidates:
        # Check if this is a Jira document
        ticket_key = doc.metadata.get("ticket_key")
        
        if ticket_key:
            # Jira document: NEVER deduplicate - keep all tickets
            deduplicated.append((doc, score))
            jira_count += 1
        else:
            # Non-Jira document: use content fingerprint for deduplication
            unique_key = f"content:{doc.page_content[:fingerprint_length].strip()}"
            
            if unique_key not in seen_keys:
                seen_keys[unique_key] = (doc, score)
                deduplicated.append((doc, score))
            else:
                # Keep the one with better score (lower distance)
                existing_doc, existing_score = seen_keys[unique_key]
                if score < existing_score:
                    # New one is better, replace
                    seen_keys[unique_key] = (doc, score)
                    deduplicated = [(d, s) for d, s in deduplicated if d != existing_doc]
                    deduplicated.append((doc, score))
                
                content_dedup_count += 1
    
    if content_dedup_count > 0:
        removal_percent = content_dedup_count/len(candidates)*100
        print(f"[DEDUP] Removed {content_dedup_count} content duplicates ({removal_percent:.1f}%)")
        print(f"[DEDUP]   • Kept all {jira_count} Jira tickets (no deduplication)")
        print(f"[DEDUP]   • Content duplicates (by fingerprint): {content_dedup_count}")
    else:
        print(f"[DEDUP] No duplicates found - kept all {len(candidates)} documents")
        if jira_count > 0:
            print(f"[DEDUP]   • Kept all {jira_count} Jira tickets (no deduplication)")
    
    return deduplicated


def merge_source_results(
    results_by_source: Dict[str, List[Tuple[Document, float]]],
    source_priorities: Optional[Dict[str, float]] = None
) -> List[Tuple[Document, float]]:
    """
    Merge results from multiple sources with priority weighting.
    
    Uses SIMPLE boost: only limitations docs get special boost (0.7x score).
    All other sources keep original scores to avoid distortion.
    
    Args:
        results_by_source: Dictionary mapping source names to result lists
        source_priorities: Optional dict (not used in simple version, kept for compatibility)
        
    Returns:
        Merged and sorted list of (document, score) tuples
    """
    merged = []
    
    for source_name, results in results_by_source.items():
        for doc, score in results:
            # SIMPLE BOOST: Only limitations get special treatment
            # Lower score = better, so 0.7x = boost (reduces distance)
            if source_name == "limitations" or doc.metadata.get("source_type") == "sharepoint_limitations":
                adjusted_score = score * 0.7  # Boost limitations docs
            else:
                adjusted_score = score  # Keep original score for all others
            
            merged.append((doc, adjusted_score))
    
    # Sort by adjusted score (lower is better)
    merged.sort(key=lambda x: x[1])
    
    return merged


def normalize_scores(
    candidates: List[Tuple[Document, float]]
) -> List[Tuple[Document, float]]:
    """
    Normalize scores to 0-1 range (similarity, higher=better).
    
    Converts distance scores (lower=better) to similarity scores (higher=better)
    using min-max normalization.
    
    Args:
        candidates: List of (document, distance_score) tuples
        
    Returns:
        List of (document, similarity_score) tuples
    """
    if not candidates:
        return []
    
    scores = [score for _, score in candidates]
    min_score = min(scores)
    max_score = max(scores)
    
    if max_score == min_score:
        # All scores are the same
        return [(doc, 1.0) for doc, _ in candidates]
    
    # Convert distance to similarity: (max - score) / (max - min)
    # Lower distance → higher similarity
    normalized = [
        (doc, (max_score - score) / (max_score - min_score))
        for doc, score in candidates
    ]
    
    return normalized


def intelligent_multi_source_retrieve(
    vectorstore,
    jira_vectorstore,
    query: str,
    routing_plan: Dict,
    enable_deduplication: bool = True,
    always_include_limitations: bool = True  # NEW PARAMETER
) -> List[Tuple[Document, float]]:
    """
    Retrieve documents from multiple sources based on routing plan.
    
    Args:
        vectorstore: Main vectorstore instance
        jira_vectorstore: Jira vectorstore instance
        query: User query
        routing_plan: Routing plan from IntelligentQueryRouter
        enable_deduplication: Whether to deduplicate results
        always_include_limitations: If True, always fetch limitations docs (default: True)
        
    Returns:
        List of (document, score) tuples (score is distance, lower=better)
    """
    
    sources_plan = routing_plan.get("sources", {})
    results_by_source = {}
    
    # Track retrieval statistics
    retrieval_stats = defaultdict(int)
    
    # ============ PINNED LIMITATIONS RETRIEVAL (ALWAYS FIRST) ============
    if always_include_limitations:
        print(f"\n[RETRIEVAL] ━━━ PINNED: Fetching limitations documents (ALWAYS INCLUDED) ━━━")
        limitations_docs = retrieve_limitations_documents(vectorstore, query, k=4)
        if limitations_docs:
            results_by_source["limitations"] = limitations_docs
            retrieval_stats["limitations"] = len(limitations_docs)
            print(f"[RETRIEVAL] ✓ Retrieved {len(limitations_docs)} limitations documents (PINNED)")
        else:
            print(f"[RETRIEVAL] ⚠ No limitations documents found (will continue with other sources)")
    
    # 1. Blog retrieval (from main vectorstore with source_type filter)
    blog_k = sources_plan.get("blog", {}).get("k", 0)
    if blog_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {blog_k} docs from Blog ━━━")
        blog_docs = retrieve_from_source(vectorstore, query, source_type="blog", k=blog_k)
        results_by_source["blog"] = blog_docs
        retrieval_stats["blog"] = len(blog_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(blog_docs)} blog documents")
        if blog_docs and len(blog_docs) > 0:
            # Log sample metadata from first document
            sample_meta = blog_docs[0][0].metadata
            print(f"[RETRIEVAL]   Sample metadata: source_type={sample_meta.get('source_type')}, tag={sample_meta.get('tag')}")
    
    # 2. SharePoint retrieval
    sharepoint_k = sources_plan.get("sharepoint", {}).get("k", 0)
    if sharepoint_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {sharepoint_k} docs from SharePoint ━━━")
        sp_docs = retrieve_from_source(vectorstore, query, source_type="sharepoint", k=sharepoint_k)
        results_by_source["sharepoint"] = sp_docs
        retrieval_stats["sharepoint"] = len(sp_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(sp_docs)} SharePoint documents")
        if sp_docs and len(sp_docs) > 0:
            sample_meta = sp_docs[0][0].metadata
            print(f"[RETRIEVAL]   Sample metadata: source_type={sample_meta.get('source_type')}, tag={sample_meta.get('tag')}")
    
    # 3. Jira retrieval (separate vectorstore)
    jira_k = sources_plan.get("jira", {}).get("k", 0)
    if jira_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {jira_k} docs from Jira ━━━")
        if not jira_vectorstore:
            print(f"[RETRIEVAL] [WARN] Jira vectorstore is None - cannot retrieve tickets")
            jira_docs = []
        else:
            jira_docs = retrieve_from_jira(jira_vectorstore, query, k=jira_k)
        results_by_source["jira"] = jira_docs
        retrieval_stats["jira"] = len(jira_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(jira_docs)} Jira tickets")
        if jira_docs and len(jira_docs) > 0:
            sample_meta = jira_docs[0][0].metadata
            ticket_key = sample_meta.get('ticket_key', 'N/A')
            print(f"[RETRIEVAL]   Sample: ticket_key={ticket_key}, section={sample_meta.get('section')}")
    
    # 4. Transcripts retrieval
    transcripts_k = sources_plan.get("transcripts", {}).get("k", 0)
    if transcripts_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {transcripts_k} docs from Transcripts ━━━")
        transcript_docs = retrieve_from_source(vectorstore, query, source_type="transcript", k=transcripts_k)
        results_by_source["transcripts"] = transcript_docs
        retrieval_stats["transcripts"] = len(transcript_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(transcript_docs)} transcript chunks")
        if transcript_docs and len(transcript_docs) > 0:
            sample_meta = transcript_docs[0][0].metadata
            print(f"[RETRIEVAL]   Sample metadata: kb_tier={sample_meta.get('kb_tier')}, source_type={sample_meta.get('source_type')}")
    
    # 5. PDFs retrieval (PDFs are stored as SharePoint documents)
    pdfs_k = sources_plan.get("pdfs", {}).get("k", 0)
    if pdfs_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {pdfs_k} docs from PDFs ━━━")
        # PDFs are stored as SharePoint documents, so search SharePoint and filter for PDF files
        # Search more SharePoint docs to have enough candidates for filtering
        sp_candidates = retrieve_from_source(vectorstore, query, source_type="sharepoint", k=pdfs_k * 3)
        
        # Filter to only include PDF files
        pdf_docs = []
        for doc, score in sp_candidates:
            metadata = doc.metadata
            file_name = metadata.get('file_name', '').lower()
            tag = metadata.get('tag', '').lower()
            
            # Check if this is a PDF file
            if '.pdf' in file_name or '.pdf' in tag:
                pdf_docs.append((doc, score))
                if len(pdf_docs) >= pdfs_k:
                    break
        
        results_by_source["pdfs"] = pdf_docs
        retrieval_stats["pdfs"] = len(pdf_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(pdf_docs)} PDF documents (filtered from {len(sp_candidates)} SharePoint candidates)")
        if pdf_docs and len(pdf_docs) > 0:
            sample_meta = pdf_docs[0][0].metadata
            print(f"[RETRIEVAL]   Sample metadata: source_type={sample_meta.get('source_type')}, file_name={sample_meta.get('file_name', 'N/A')}")
    
    # 6. Excel retrieval
    excel_k = sources_plan.get("excel", {}).get("k", 0)
    if excel_k > 0:
        print(f"\n[RETRIEVAL] ━━━ Fetching {excel_k} docs from Excel ━━━")
        excel_docs = retrieve_from_source(vectorstore, query, source_type="excel", k=excel_k)
        results_by_source["excel"] = excel_docs
        retrieval_stats["excel"] = len(excel_docs)
        print(f"[RETRIEVAL] ✓ Retrieved {len(excel_docs)} Excel documents")
        if excel_docs and len(excel_docs) > 0:
            sample_meta = excel_docs[0][0].metadata
            print(f"[RETRIEVAL]   Sample metadata: source_type={sample_meta.get('source_type')}, file_name={sample_meta.get('file_name', 'N/A')}")
    
    # Merge all results
    total_retrieved = sum(retrieval_stats.values())
    print(f"\n[RETRIEVAL] 📦 Total candidates from all sources: {total_retrieved}")
    
    # Log statistics
    for source, count in sorted(retrieval_stats.items(), key=lambda x: x[1], reverse=True):
        if count > 0:
            print(f"  • {source}: {count} docs")
    
    # Merge with priority weighting
    all_candidates = merge_source_results(results_by_source)
    
    # Deduplicate if enabled
    if enable_deduplication:
        print(f"\n[DEDUP] Deduplicating {len(all_candidates)} candidates...")
        all_candidates = deduplicate_by_content(all_candidates)
        print(f"[DEDUP] ✓ After deduplication: {len(all_candidates)} unique documents")
    
    return all_candidates
