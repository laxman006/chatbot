import os
import requests
import json
import markdown
from typing import List, Optional
from datetime import datetime
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document
from config import (
    BLOG_POSTS_PER_PAGE, BLOG_MAX_PAGES, BLOG_START_PAGE, BLOG_LAST_POLL_FILE,
    SHAREPOINT_SALES_SITE_URL, SHAREPOINT_SALES_FOLDER_PATH, SHAREPOINT_SALES_MAX_DEPTH,
    SHAREPOINT_PRESALES_SITE_URL, SHAREPOINT_PRESALES_FOLDER_PATH, SHAREPOINT_PRESALES_MAX_DEPTH,
    SHAREPOINT_LIMITATIONS_SITE_URL, SHAREPOINT_LIMITATIONS_FOLDER_PATH, SHAREPOINT_LIMITATIONS_MAX_DEPTH
)
from app.pdf_processor import process_pdf_directory, chunk_pdf_documents
from app.excel_processor import process_excel_directory, chunk_excel_documents
from app.doc_processor import process_doc_directory, chunk_doc_documents
from app.sharepoint_processor import process_sharepoint_content


def fetch_posts(base_url: str, per_page=10, max_pages=6, start_page=1, extra_params: dict | None = None):
    """Fetch posts from WordPress API with pagination support.

    start_page allows continuing from a specific page (e.g., 4 to skip first 3 pages).
    """
    all_posts = []
    page = start_page
    session = requests.Session()
    
    while page <= max_pages:
        # Build query with preserved params + pagination
        params = dict(extra_params or {})
        params["per_page"] = per_page
        params["page"] = page
        url = f"{base_url}?{urlencode(params, doseq=True)}"
        print(f"Fetching: {url}")
        try:
            resp = session.get(url, timeout=60, stream=True)
            resp.raise_for_status()
            posts = json.loads(resp.content.decode("utf-8"))
            if not posts:
                break
            all_posts.extend(posts)
            print(f"Page {page} fetched, total so far: {len(all_posts)}")
        except requests.exceptions.HTTPError as e:
            # If it's a 400 error and we have an 'after' parameter, try without it
            if e.response is not None and e.response.status_code == 400 and "after" in params:
                print(f"Error fetching page {page} with 'after' parameter: {e}")
                print(f"[*] Retrying without 'after' parameter...")
                # Retry without the 'after' parameter
                params_retry = dict(params)
                params_retry.pop("after", None)
                url_retry = f"{base_url}?{urlencode(params_retry, doseq=True)}"
                try:
                    resp_retry = session.get(url_retry, timeout=60, stream=True)
                    resp_retry.raise_for_status()
                    posts = json.loads(resp_retry.content.decode("utf-8"))
                    if not posts:
                        break
                    all_posts.extend(posts)
                    print(f"Page {page} fetched (without 'after' filter), total so far: {len(all_posts)}")
                except Exception as e2:
                    print(f"Error fetching page {page} (retry): {e2}")
                    break
            else:
                print(f"Error fetching page {page}: {e}")
                break
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            break
        page += 1
    
    return all_posts

def load_webpage(url: str):
    """Fetch posts from WordPress API and return raw text."""
    # Check if URL contains pagination parameters to determine if we should use pagination
    if "per_page=" in url and "page=" in url:
        # Single page request - use original method
        response = requests.get(url)
        data = response.json()
    else:
        # Use pagination while preserving existing query params like tags/category
        parsed = urlparse(url)
        base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        base_params = dict(parse_qsl(parsed.query))
        # Remove any explicit page from preserved params (we control it)
        base_params.pop("page", None)
        # Respect configured per_page; remove to avoid duplication
        base_params.pop("per_page", None)
        data = fetch_posts(
            base_url,
            per_page=BLOG_POSTS_PER_PAGE,
            max_pages=BLOG_MAX_PAGES,
            start_page=BLOG_START_PAGE,
            extra_params=base_params,
        )
    
    texts = []
    for post in data:
        if "content" in post and "rendered" in post["content"]:
            texts.append(post["content"]["rendered"])
    return "\n\n".join(texts)

def fetch_latest_web_content(url: str, max_posts: int = 50, since_date: str = None):
    """Fetch only the latest blog posts (first page, limited to max_posts).
    
    This is optimized for incremental updates - only fetches newest posts.
    WordPress API returns posts in reverse chronological order (newest first).
    
    Args:
        url: WordPress API URL
        max_posts: Maximum number of latest posts to fetch (default: 50)
        since_date: ISO date string (YYYY-MM-DD) - only fetch posts after this date (optional)
    
    Returns:
        List of Document objects for latest blog posts
    """
    # Fetch only first page (newest posts come first)
    parsed = urlparse(url)
    base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    base_params = dict(parse_qsl(parsed.query))
    
    # Check if per_page is specified in URL
    url_per_page = base_params.get("per_page")
    if url_per_page:
        try:
            url_per_page_int = int(url_per_page)
            # Use the smaller of URL's per_page or max_posts
            effective_per_page = min(url_per_page_int, max_posts, BLOG_POSTS_PER_PAGE)
            print(f"Fetching latest {effective_per_page} blog posts from WordPress API (using per_page={url_per_page} from URL, limited to {max_posts})...")
        except ValueError:
            effective_per_page = min(max_posts, BLOG_POSTS_PER_PAGE)
            print(f"Fetching latest {effective_per_page} blog posts from WordPress API...")
    else:
        effective_per_page = min(max_posts, BLOG_POSTS_PER_PAGE)
        print(f"Fetching latest {effective_per_page} blog posts from WordPress API...")
    
    # Remove page and per_page from params (we'll set them explicitly)
    base_params.pop("page", None)
    base_params.pop("per_page", None)
    
    # Add date filter if provided (WordPress API supports after parameter)
    if since_date:
        # Normalize to YYYY-MM-DD (stored value may be ISO from older runs)
        since_date_ymd = since_date[:10] if len(since_date) >= 10 else since_date
        try:
            date_obj = datetime.strptime(since_date_ymd, "%Y-%m-%d")
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            if date_obj > today:
                print(f"[WARN] Date {since_date_ymd} is in the future. Skipping date filter.")
            else:
                # WordPress API expects ISO 8601 datetime format (YYYY-MM-DDTHH:MM:SS)
                iso_datetime = f"{since_date_ymd}T00:00:00"
                base_params["after"] = iso_datetime
                print(f"[*] Filtering posts after {iso_datetime}...")
        except ValueError:
            # Fail fast: invalid date would cause partial fetch and destructive deletes
            raise ValueError(
                f"Invalid date format for incremental blog fetch: '{since_date}'. "
                "Expected YYYY-MM-DD (or ISO string). Aborting to avoid partial fetch."
            )
    
    # Request embedded author for author_name (WordPress REST API)
    base_params["_embed"] = "author"
    
    # Fetch only first page with limited posts
    data = fetch_posts(
        base_url,
        per_page=effective_per_page,
        max_pages=1,  # Only first page
        start_page=1,
        extra_params=base_params,
    )
    
    # Limit to max_posts if we got more
    if len(data) > max_posts:
        data = data[:max_posts]
    
    all_docs = []
    posts_processed = 0
    
    # Process each blog post separately to preserve metadata
    for post in data:
        if "content" not in post or "rendered" not in post["content"]:
            continue
        
        # Extract post metadata from WordPress API response
        title = post.get("title", {}).get("rendered", "Untitled")
        slug = post.get("slug", "") or post.get("link", "").strip("/").split("/")[-1] or str(post.get("id", ""))
        link = post.get("link", "")  # Full URL to the blog post
        content = post["content"]["rendered"]
        post_date = post.get("date", "")  # ISO date string from WordPress API
        modified = post.get("modified") or post_date
        # Author display name (WordPress _embed=author returns _embedded.author[0].name)
        emb = post.get("_embedded") or {}
        author_list = emb.get("author")
        author_name = ""
        if isinstance(author_list, list) and author_list and isinstance(author_list[0], dict):
            author_name = (author_list[0].get("name") or "").strip()
        
        # Clean HTML tags from blog content
        soup = BeautifulSoup(content, "html.parser")
        clean_text = soup.get_text(separator="\n", strip=True)
        
        if not clean_text.strip():
            continue
        
        # One doc-level summary per post (used for parent-doc expansion / CRAG)
        doc_summary = clean_text[:400].rstrip() + ("..." if len(clean_text) > 400 else "")
        
        # Chunk this post's content
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        
        # Add title to content for better context
        content_with_title = f"# {title}\n\n{clean_text}"
        chunks = splitter.create_documents([content_with_title])
        
        # Stable doc_id for grouping (ingestion pipeline groups by doc_id)
        doc_id = slug or link or str(post.get("id", ""))
        
        # Add canonical blog metadata to each chunk (Weaviate gold path)
        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["source_type"] = "blog"
            chunk.metadata["source"] = "cloudfuze_blog"
            chunk.metadata["tag"] = "blog"
            chunk.metadata["post_title"] = title
            chunk.metadata["post_slug"] = slug
            chunk.metadata["post_url"] = link
            chunk.metadata["is_blog_post"] = True
            # Universal/canonical fields for retrieval and citations
            chunk.metadata["title"] = title
            chunk.metadata["url"] = link
            chunk.metadata["author_name"] = author_name
            chunk.metadata["doc_summary"] = doc_summary
            if post_date:
                chunk.metadata["post_date"] = post_date
                chunk.metadata["created_at"] = post_date
                chunk.metadata["updated_at"] = modified
                chunk.metadata["publish_date"] = post_date
        
        all_docs.extend(chunks)
        posts_processed += 1
    
    print(f"[OK] Loaded {posts_processed} latest blog posts into {len(all_docs)} chunks")
    return all_docs


def _blog_metadata_path() -> str:
    """Path to file-based blog metadata (replaces legacy vectorstore metadata)."""
    return os.path.join(os.path.dirname(BLOG_LAST_POLL_FILE), "blog_metadata.json")


def load_blog_metadata() -> dict:
    """Load blog metadata from file (last_blog_poll, blog_post_count, last_blog_post_date, etc.)."""
    try:
        path = _blog_metadata_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Could not load blog metadata: {e}")
    return {}


def save_blog_metadata(metadata: dict) -> None:
    """Write blog metadata to file. Creates parent dir if needed."""
    try:
        path = _blog_metadata_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"[WARN] Could not save blog metadata: {e}")


def get_last_blog_post_date() -> Optional[str]:
    """Get the date of the most recent blog post from file-based blog metadata."""
    return load_blog_metadata().get("last_blog_post_date")

def fetch_web_content(url: str):
    """Fetch and chunk web content into LangChain Documents with blog post URLs and metadata.

    Respects BLOG_POSTS_PER_PAGE, BLOG_MAX_PAGES, and BLOG_START_PAGE to allow
    continuing partial fetches without reprocessing earlier pages.
    
    Each blog post chunk will include:
    - post_title: The blog post title
    - post_slug: URL slug
    - post_url: Full URL to the blog post
    - is_blog_post: Flag to identify blog content
    """
    # Get posts from WordPress API (not just text, we need metadata)
    print("Fetching blog posts from WordPress API...")
    # Check if URL has BOTH per_page AND page parameters (for single page fetch)
    # Note: Check for "&page=" or "?page=" to avoid matching "per_page="
    has_page_param = ("&page=" in url or "?page=" in url) and "per_page=" in url
    if has_page_param:
        response = requests.get(url)
        data = response.json()
    else:
        parsed = urlparse(url)
        base_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
        base_params = dict(parse_qsl(parsed.query))
        base_params.pop("page", None)
        base_params.pop("per_page", None)
        base_params["_embed"] = "author"
        data = fetch_posts(
            base_url,
            per_page=BLOG_POSTS_PER_PAGE,
            max_pages=BLOG_MAX_PAGES,
            start_page=BLOG_START_PAGE,
            extra_params=base_params,
        )
    
    all_docs = []
    posts_processed = 0
    
    # Process each blog post separately to preserve metadata
    for post in data:
        if "content" not in post or "rendered" not in post["content"]:
            continue
        
        # Extract post metadata from WordPress API response
        title = post.get("title", {}).get("rendered", "Untitled")
        slug = post.get("slug", "") or (post.get("link", "").strip("/").split("/")[-1] if post.get("link") else "") or str(post.get("id", ""))
        link = post.get("link", "")  # Full URL to the blog post
        content = post["content"]["rendered"]
        post_date = post.get("date", "")  # ISO date string from WordPress API
        modified = post.get("modified") or post_date
        emb = post.get("_embedded") or {}
        author_list = emb.get("author")
        author_name = ""
        if isinstance(author_list, list) and author_list and isinstance(author_list[0], dict):
            author_name = (author_list[0].get("name") or "").strip()
        
        # Clean HTML tags from blog content
        soup = BeautifulSoup(content, "html.parser")
        clean_text = soup.get_text(separator="\n", strip=True)
        
        if not clean_text.strip():
            continue
        
        doc_summary = clean_text[:400].rstrip() + ("..." if len(clean_text) > 400 else "")
        
        # Chunk this post's content
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1500,
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        
        # Add title to content for better context
        content_with_title = f"# {title}\n\n{clean_text}"
        chunks = splitter.create_documents([content_with_title])
        
        doc_id = slug or link or str(post.get("id", ""))
        
        for chunk in chunks:
            chunk.metadata["doc_id"] = doc_id
            chunk.metadata["source_type"] = "blog"
            chunk.metadata["source"] = "cloudfuze_blog"
            chunk.metadata["tag"] = "blog"
            chunk.metadata["post_title"] = title
            chunk.metadata["post_slug"] = slug
            chunk.metadata["post_url"] = link
            chunk.metadata["is_blog_post"] = True
            chunk.metadata["title"] = title
            chunk.metadata["url"] = link
            chunk.metadata["author_name"] = author_name
            chunk.metadata["doc_summary"] = doc_summary
            if post_date:
                chunk.metadata["post_date"] = post_date
                chunk.metadata["created_at"] = post_date
                chunk.metadata["updated_at"] = modified
                chunk.metadata["publish_date"] = post_date
        
        all_docs.extend(chunks)
        posts_processed += 1
    
    print(f"[OK] Loaded {posts_processed} blog posts into {len(all_docs)} chunks with full metadata")
    return all_docs

def fetch_latest_sharepoint_sales(max_items: int = 100) -> List[Document]:
    """
    Fetch SharePoint documents from CFSales Documents library.
    Processes the entire Documents library (all folders and files).
    Similar to fetch_latest_web_content for blogs - optimized for incremental updates.
    
    Args:
        max_items: Maximum number of latest documents to fetch (default: 100)
                  Set to 9999 to get all documents
    
    Returns:
        List of Document objects for SharePoint Sales documents
    """
    from app.sharepoint_graph_extractor import SharePointGraphExtractor
    from config import (
        SHAREPOINT_SALES_SITE_URL,
        SHAREPOINT_SALES_MAX_DEPTH
    )
    
    print(f"[*] Fetching SharePoint documents from CFSales...")
    print(f"   Site: {SHAREPOINT_SALES_SITE_URL}")
    print(f"   Processing: Entire Documents library")
    
    # Extract just the site URL from the full path
    # e.g., https://cloudfuzecom.sharepoint.com/sites/CFSales/Shared%20Documents/Forms/AllItems.aspx
    # becomes: https://cloudfuzecom.sharepoint.com/sites/CFSales
    parsed_url = urlparse(SHAREPOINT_SALES_SITE_URL)
    path_parts = [p for p in parsed_url.path.split('/') if p]
    
    # Find 'sites' in path and extract site URL
    clean_site_url = SHAREPOINT_SALES_SITE_URL  # Default to original
    if 'sites' in path_parts:
        site_idx = path_parts.index('sites')
        if site_idx + 1 < len(path_parts):
            # Build clean site URL: https://hostname/sites/sitename
            clean_site_url = f"{parsed_url.scheme}://{parsed_url.netloc}/sites/{path_parts[site_idx + 1]}"
            print(f"[*] Extracted site URL: {clean_site_url}")
        else:
            print("[ERROR] Could not extract site name from URL")
            return []
    else:
        # If no 'sites' found, use URL as-is (might already be clean)
        print(f"[*] Using site URL as-is: {clean_site_url}")
    
    # Create extractor with cleaned sales site URL
    extractor = SharePointGraphExtractor()
    extractor.site_url = clean_site_url
    # Reset cached IDs so they're fetched for the new site
    extractor.site_id = None
    extractor.drive_id = None
    
    # Get site and drive IDs
    site_id = extractor.get_site_id()
    if not site_id:
        print("[ERROR] Failed to get CFSales site ID")
        return []
    
    drive_id = extractor.get_drive_id()
    if not drive_id:
        print("[ERROR] Failed to get CFSales drive ID")
        return []
    
    # Extract documents from the entire Documents library (root folder)
    print(f"[*] Extracting documents from entire Documents library...")
    documents = extractor.extract_from_folder(
        item_id=None,  # None means root folder (Documents library)
        folder_path=[],  # Empty path means root
        visited_ids=set(),
        depth=0
    )
    
    # Sort by modified date (newest first) and limit
    # Note: SharePoint documents may have 'lastModifiedDateTime' in metadata
    documents.sort(
        key=lambda d: d.metadata.get('modified_at', '') or d.metadata.get('lastModifiedDateTime', ''),
        reverse=True
    )
    documents = documents[:max_items]
    
    # Add priority tag and source type
    for doc in documents:
        doc.metadata['source_type'] = 'sharepoint_sales'
        # Get folder path from metadata if available
        folder_path = doc.metadata.get('folder_tags', '').replace('sharepoint/', '') or 'Documents'
        doc.metadata['tag'] = f"sharepoint_sales/{folder_path}"
        doc.metadata['priority'] = True  # Mark for priority boosting
    
    print(f"[OK] Fetched {len(documents)} SharePoint Sales documents from CFSales")
    return documents

def find_folder_by_path_helper(extractor, drive_id: str, folder_path: str) -> Optional[str]:
    """
    Find folder ID by path in SharePoint.
    Helper function for SharePoint extraction.
    
    Args:
        extractor: SharePointGraphExtractor instance
        drive_id: SharePoint drive ID
        folder_path: Folder path like "Release 1" or "Folder1/Folder2"
    
    Returns:
        Folder item ID or None
    """
    try:
        from app.sharepoint_auth import sharepoint_auth
        import requests
        
        # Split path into components
        path_parts = [p.strip() for p in folder_path.split('/') if p.strip()]
        
        # Start from root
        current_item_id = None
        
        for folder_name in path_parts:
            # List items in current folder
            if current_item_id:
                graph_url = f"{extractor.graph_base_url}/drives/{drive_id}/items/{current_item_id}/children"
            else:
                graph_url = f"{extractor.graph_base_url}/drives/{drive_id}/root/children"
            
            headers = sharepoint_auth.get_headers()
            response = requests.get(graph_url, headers=headers, timeout=30)
            
            if response.status_code != 200:
                print(f"[ERROR] Failed to list items: {response.status_code}")
                return None
            
            data = response.json()
            items = data.get('value', [])
            
            # Find folder with matching name
            found = False
            for item in items:
                if 'folder' in item and item.get('name', '').strip() == folder_name:
                    current_item_id = item.get('id')
                    found = True
                    break
            
            if not found:
                print(f"[ERROR] Folder not found: {folder_name} in path {folder_path}")
                return None
        
        return current_item_id
        
    except Exception as e:
        print(f"[ERROR] Error finding folder: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_latest_sharepoint_presales(max_items: int = 100) -> List[Document]:
    """
    Fetch SharePoint documents from Presales Training site.
    Extracts from the specified folder path (e.g., "Release 1") or entire Documents library.
    Similar to fetch_latest_sharepoint_sales - optimized for incremental updates.
    
    Args:
        max_items: Maximum number of latest documents to fetch (default: 100)
                  Set to 9999 to get all documents
    
    Returns:
        List of Document objects for Presales SharePoint documents
    """
    from app.sharepoint_graph_extractor import SharePointGraphExtractor
    
    print(f"[*] Fetching SharePoint documents from Presales Training...")
    print(f"   Site: {SHAREPOINT_PRESALES_SITE_URL}")
    
    # Extract just the site URL from the full path if needed
    parsed_url = urlparse(SHAREPOINT_PRESALES_SITE_URL)
    path_parts = [p for p in parsed_url.path.split('/') if p]
    
    # Find 'sites' in path and extract site URL
    clean_site_url = SHAREPOINT_PRESALES_SITE_URL  # Default to original
    if 'sites' in path_parts:
        site_idx = path_parts.index('sites')
        if site_idx + 1 < len(path_parts):
            # Build clean site URL: https://hostname/sites/sitename
            clean_site_url = f"{parsed_url.scheme}://{parsed_url.netloc}/sites/{path_parts[site_idx + 1]}"
            print(f"[*] Extracted site URL: {clean_site_url}")
        else:
            print("[ERROR] Could not extract site name from URL")
            return []
    else:
        # If no 'sites' found, use URL as-is (might already be clean)
        print(f"[*] Using site URL as-is: {clean_site_url}")
    
    # Create extractor with cleaned presales site URL
    extractor = SharePointGraphExtractor()
    extractor.site_url = clean_site_url
    # Reset cached IDs so they're fetched for the new site
    extractor.site_id = None
    extractor.drive_id = None
    
    # Get site and drive IDs
    site_id = extractor.get_site_id()
    if not site_id:
        print("[ERROR] Failed to get Presales Training site ID")
        return []
    
    drive_id = extractor.get_drive_id()
    if not drive_id:
        print("[ERROR] Failed to get Presales Training drive ID")
        return []
    
    # Check if a specific folder path is configured
    folder_id = None
    folder_path_list = []
    
    if SHAREPOINT_PRESALES_FOLDER_PATH:
        print(f"[*] Extracting from specific folder: {SHAREPOINT_PRESALES_FOLDER_PATH}")
        # Find folder by path
        folder_id = find_folder_by_path_helper(extractor, drive_id, SHAREPOINT_PRESALES_FOLDER_PATH)
        if folder_id:
            # Convert folder path string to list for extract_from_folder
            folder_path_list = [p.strip() for p in SHAREPOINT_PRESALES_FOLDER_PATH.split('/') if p.strip()]
            print(f"[OK] Found folder ID: {folder_id[:50]}...")
        else:
            print(f"[WARNING] Folder not found: {SHAREPOINT_PRESALES_FOLDER_PATH}")
            print("[*] Falling back to entire Documents library...")
    else:
        print(f"[*] Extracting from entire Documents library...")
    
    # Extract documents from the folder (or root if no folder specified)
    # This will recursively scan ALL folders, including new ones
    documents = extractor.extract_from_folder(
        item_id=folder_id,  # None means root folder (Documents library)
        folder_path=folder_path_list,  # Empty list means root
        visited_ids=set(),
        depth=0
    )
    
    # Sort by modified date (newest first) and limit
    # Note: SharePoint documents may have 'lastModifiedDateTime' in metadata
    documents.sort(
        key=lambda d: d.metadata.get('modified_at', '') or d.metadata.get('lastModifiedDateTime', ''),
        reverse=True
    )
    documents = documents[:max_items]
    
    # Add tag and source type (works like regular SharePoint - no priority flag)
    for doc in documents:
        doc.metadata['source_type'] = 'sharepoint_presales'
        # Get folder path from metadata if available
        folder_path = doc.metadata.get('folder_tags', '').replace('sharepoint/', '') or 'Documents'
        doc.metadata['tag'] = f"sharepoint_presales/{folder_path}"
        # No priority flag - works like regular SharePoint
    
    print(f"[OK] Fetched {len(documents)} Presales SharePoint documents")
    return documents

def fetch_latest_sharepoint_limitations(max_items: int = 100) -> List[Document]:
    """
    Fetch SharePoint documents from Repository25 Limitations and Features folder.
    Extracts from the specified folder path (e.g., "Neutara Labs/Limitations and features").
    Similar to fetch_latest_sharepoint_presales - optimized for incremental updates.
    
    Args:
        max_items: Maximum number of latest documents to fetch (default: 100)
                  Set to 9999 to get all documents
    
    Returns:
        List of Document objects for SharePoint Limitations documents
    """
    from app.sharepoint_graph_extractor import SharePointGraphExtractor
    from config import (
        SHAREPOINT_LIMITATIONS_SITE_URL,
        SHAREPOINT_LIMITATIONS_FOLDER_PATH,
        SHAREPOINT_LIMITATIONS_MAX_DEPTH
    )
    
    print(f"[*] Fetching SharePoint documents from Limitations and Features...")
    print(f"   Site: {SHAREPOINT_LIMITATIONS_SITE_URL}")
    
    # Extract just the site URL from the full path if needed
    parsed_url = urlparse(SHAREPOINT_LIMITATIONS_SITE_URL)
    path_parts = [p for p in parsed_url.path.split('/') if p]
    
    # Find 'sites' in path and extract site URL
    clean_site_url = SHAREPOINT_LIMITATIONS_SITE_URL  # Default to original
    if 'sites' in path_parts:
        site_idx = path_parts.index('sites')
        if site_idx + 1 < len(path_parts):
            # Build clean site URL: https://hostname/sites/sitename
            clean_site_url = f"{parsed_url.scheme}://{parsed_url.netloc}/sites/{path_parts[site_idx + 1]}"
            print(f"[*] Extracted site URL: {clean_site_url}")
        else:
            print("[ERROR] Could not extract site name from URL")
            return []
    else:
        # If no 'sites' found, use URL as-is (might already be clean)
        print(f"[*] Using site URL as-is: {clean_site_url}")
    
    # Create extractor with cleaned limitations site URL
    extractor = SharePointGraphExtractor()
    extractor.site_url = clean_site_url
    # Reset cached IDs so they're fetched for the new site
    extractor.site_id = None
    extractor.drive_id = None
    
    # Get site and drive IDs
    site_id = extractor.get_site_id()
    if not site_id:
        print("[ERROR] Failed to get Limitations site ID")
        return []
    
    drive_id = extractor.get_drive_id()
    if not drive_id:
        print("[ERROR] Failed to get Limitations drive ID")
        return []
    
    # Check if a specific folder path is configured
    folder_id = None
    folder_path_list = []
    
    if SHAREPOINT_LIMITATIONS_FOLDER_PATH:
        print(f"[*] Extracting from specific folder: {SHAREPOINT_LIMITATIONS_FOLDER_PATH}")
        # Find folder by path
        folder_id = find_folder_by_path_helper(extractor, drive_id, SHAREPOINT_LIMITATIONS_FOLDER_PATH)
        if folder_id:
            # Convert folder path string to list for extract_from_folder
            folder_path_list = [p.strip() for p in SHAREPOINT_LIMITATIONS_FOLDER_PATH.split('/') if p.strip()]
            print(f"[OK] Found folder ID: {folder_id[:50]}...")
        else:
            print(f"[WARNING] Folder not found: {SHAREPOINT_LIMITATIONS_FOLDER_PATH}")
            print("[*] Falling back to entire Documents library...")
    else:
        print(f"[*] Extracting from entire Documents library...")
    
    # Extract documents from the folder (or root if no folder specified)
    documents = extractor.extract_from_folder(
        item_id=folder_id,  # None means root folder (Documents library)
        folder_path=folder_path_list,  # Empty list means root
        visited_ids=set(),
        depth=0
    )
    
    # Sort by modified date (newest first) and limit
    # Note: SharePoint documents may have 'lastModifiedDateTime' in metadata
    documents.sort(
        key=lambda d: d.metadata.get('modified_at', '') or d.metadata.get('lastModifiedDateTime', ''),
        reverse=True
    )
    documents = documents[:max_items]
    
    # Add tag and source type, preserve Excel metadata
    for doc in documents:
        doc.metadata['source_type'] = 'sharepoint_limitations'
        # Get folder path from metadata if available
        folder_path = doc.metadata.get('folder_tags', '').replace('sharepoint/', '') or 'Documents'
        doc.metadata['tag'] = f"sharepoint_limitations/{folder_path}"
        
        # CRITICAL: Add doc_type for easy filtering (PRIMARY FILTER)
        doc.metadata['doc_type'] = 'limitations'
        doc.metadata['is_limitations_doc'] = True  # Explicit flag for fallback filtering
        
        # Preserve and enhance Excel-specific metadata if it's an Excel file
        file_name = doc.metadata.get('file_name', '')
        if file_name and file_name.lower().endswith(('.xlsx', '.xls')):
            doc.metadata['content_type'] = 'excel_data'
            doc.metadata['file_format'] = file_name.rsplit('.', 1)[-1].lower()
            # Add Excel tag for better retrieval
            if 'excel_tag' not in doc.metadata:
                doc.metadata['excel_tag'] = 'excel'
            
            # If filename contains "limitations" or "features", ensure it's marked
            if 'limitations' in file_name.lower() or 'features' in file_name.lower():
                doc.metadata['doc_type'] = 'limitations'
                doc.metadata['is_limitations_doc'] = True
    
    print(f"[OK] Fetched {len(documents)} Limitations SharePoint documents")
    return documents

def strip_markdown(md_text: str) -> str:
    """Convert Markdown/HTML to plain text."""
    html = markdown.markdown(md_text)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text()

def preserve_markdown(md_text: str) -> str:
    """Preserve Markdown formatting for better display."""
    # Clean up any HTML tags that might interfere with Markdown
    soup = BeautifulSoup(md_text, "html.parser")
    clean_text = soup.get_text()
    
    # Return the clean Markdown text (don't convert to HTML)
    return clean_text

def build_vectorstore(url: str):
    """Deprecated. ChromaDB removed. Use Weaviate: python scripts/ingest_to_weaviate.py --source blog"""
    raise NotImplementedError(
        "ChromaDB has been removed. Use Weaviate for ingestion: "
        "python scripts/ingest_to_weaviate.py --source blog"
    )


def build_combined_vectorstore(url: str = None, pdf_directory: str = None, excel_directory: str = None, doc_directory: str = None, sharepoint_enabled: bool = False, outlook_enabled: bool = False):
    """Deprecated. ChromaDB removed. Use Weaviate: python scripts/ingest_to_weaviate.py --source <source>"""
    raise NotImplementedError(
        "ChromaDB has been removed. Use Weaviate for ingestion: "
        "python scripts/ingest_to_weaviate.py --source sharepoint|blog|transcript|excel|email|jira"
    )
