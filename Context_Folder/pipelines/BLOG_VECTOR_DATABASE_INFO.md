# Blog Posts in Vector Database - Summary

## How Blogs Are Fetched

### 1. **Source Configuration**
Blogs are fetched from the CloudFuze WordPress API:
- **API URL**: `https://cloudfuze.com/wp-json/wp/v2/posts?per_page=100`
- **Configuration File**: `config.py`

### 2. **Pagination Settings**
The system uses pagination to fetch multiple pages of blog posts:
- **Posts per page**: `100` (BLOG_POSTS_PER_PAGE)
- **Maximum pages**: `14` (BLOG_MAX_PAGES)
- **Start page**: `1` (BLOG_START_PAGE, configurable via environment variable)
- **Maximum total posts**: Up to **1,400 posts** (14 pages × 100 posts)

### 3. **Fetching Process**

The blog fetching happens in `app/helpers.py`:

#### Function: `fetch_posts()`
- Fetches posts from WordPress API with pagination support
- Preserves existing query parameters (tags, categories, etc.)
- Handles pagination automatically
- Returns all posts from all pages

#### Function: `fetch_web_content()`
- Main function that processes blog posts
- Fetches posts using `fetch_posts()`
- Processes each blog post separately to preserve metadata
- Cleans HTML tags from content
- Chunks each post into smaller pieces (chunk_size=1500, overlap=300)
- Adds comprehensive metadata to each chunk

### 4. **Blog Metadata Added to Vector Database**

Each blog chunk includes the following metadata:
```python
{
    "source_type": "web",
    "source": "cloudfuze_blog",
    "tag": "blog",
    "post_title": "Blog Post Title",
    "post_slug": "blog-post-slug",
    "post_url": "https://cloudfuze.com/blog-post-url/",
    "is_blog_post": True
}
```

### 5. **How Blogs Are Added to Vector Database**

#### Process Flow:
1. **Fetch**: `fetch_web_content()` fetches blog posts from WordPress API
2. **Process**: Each post is cleaned (HTML removed) and chunked
3. **Metadata**: Blog metadata is added to each chunk
4. **Vectorization**: Chunks are embedded using OpenAI embeddings (`text-embedding-3-small`)
5. **Storage**: Chunks are stored in ChromaDB vector database with HNSW indexing

#### Integration Points:
- **Main ingestion**: `app/vectorstore.py` → `build_enhanced_vectorstore_full()`
- **Helper functions**: `app/helpers.py` → `fetch_web_content()`
- **Enhanced pipeline**: `app/enhanced_helpers.py` → `build_enhanced_vectorstore()`

### 6. **How Blogs Are Retrieved/Fetched from Vector Database**

#### Retrieval Methods:

1. **Similarity Search** (`app/endpoints.py`):
   ```python
   vectorstore.similarity_search_with_score(query, k=100)
   ```
   - Retrieves documents based on semantic similarity
   - Returns top-k most similar documents

2. **Branch Filtering** (`retrieve_with_branch_filter()`):
   - Performs semantic search
   - Filters results by metadata tags (including "blog")
   - Used for intent-based retrieval

3. **Hybrid Retrieval** (Option E - Perplexity-style):
   - **Dense retrieval**: Uses embeddings (ChromaDB)
   - **Sparse retrieval**: Uses BM25
   - **Reranking**: Cross-encoder reranking
   - Merges and normalizes scores

4. **MMR (Maximal Marginal Relevance)**:
   - Primary retriever for diverse results
   - Balances relevance with diversity
   - Prevents redundant results

#### Blog Identification During Retrieval:

Blogs are identified by checking metadata:
```python
# In analyze_retrieved_documents()
if any(blog_indicator in source_type.lower() 
       for blog_indicator in ['blog', 'wordpress', 'cloudfuze.com']):
    blog_count += 1
```

Or by checking specific flags:
```python
if metadata.get("is_blog_post") == True:
    # This is a blog post
```

### 7. **Configuration Control**

Blog fetching can be enabled/disabled via environment variable:
- **ENABLE_WEB_SOURCE**: Set to `"true"` to enable blog fetching
- **INITIALIZE_VECTORSTORE**: Set to `"true"` to rebuild vectorstore

### 8. **Estimated Blog Count**

Based on configuration:
- **Maximum possible**: 1,400 blog posts (14 pages × 100 posts)
- **Actual count**: Depends on how many posts exist in WordPress
- **Chunks per post**: Varies based on post length (typically 1-10 chunks per post)

### 9. **How to Check Actual Blog Count**

To check the actual number of blogs in the vector database:

1. **Use the script**: `scripts/count_blogs.py` (may have ChromaDB compatibility issues)

2. **Query via API**: The system tracks blog counts in retrieval analysis:
   ```python
   doc_analysis = analyze_retrieved_documents(docs_with_scores)
   blog_count = doc_analysis["blog_docs_count"]
   ```

3. **Check vectorstore directly**:
   ```python
   from app.vectorstore import vectorstore
   if vectorstore:
       all_data = vectorstore.get(include=["metadatas"])
       blog_chunks = [m for m in all_data["metadatas"] 
                     if m.get("is_blog_post") == True]
   ```

### 10. **Key Files**

- **Configuration**: `config.py` (lines 199-203, 230, 238)
- **Fetching Logic**: `app/helpers.py` (lines 18-159)
- **Vectorstore Management**: `app/vectorstore.py`
- **Enhanced Pipeline**: `app/enhanced_helpers.py`
- **Retrieval Logic**: `app/endpoints.py` (lines 780-853, 1100-1130)

### 11. **Notes**

- Blogs are chunked, so one blog post may result in multiple chunks in the vector database
- The system uses HNSW (Hierarchical Navigable Small World) graph indexing for efficient similarity search
- Blog posts are embedded using OpenAI's `text-embedding-3-small` model
- The system supports incremental updates - only changed sources are reprocessed

