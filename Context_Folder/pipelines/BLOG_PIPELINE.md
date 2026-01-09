# Blog Processing Pipeline Documentation

## Overview

Fetches blog posts from CloudFuze WordPress API, processes them, and adds them to the vectorstore.

**Location:** `app/helpers.py` - `fetch_web_content()`

---

## Pipeline Architecture

```
WordPress API
    │
    ├─► Fetch Posts (Pagination)
    │   ├─► Start from BLOG_START_PAGE
    │   ├─► Fetch up to BLOG_MAX_PAGES
    │   ├─► BLOG_POSTS_PER_PAGE posts per page
    │   └─► Total: Up to 1,400 posts
    │
    ├─► Process Each Post
    │   ├─► Extract title, slug, link, content
    │   ├─► Clean HTML tags
    │   ├─► Extract plain text
    │   └─► Add title to content
    │
    ├─► Chunk Each Post
    │   ├─► RecursiveCharacterTextSplitter
    │   ├─► Chunk size: 1500 tokens
    │   ├─► Overlap: 300 tokens
    │   └─► Preserve post metadata
    │
    ├─► Add Metadata to Each Chunk
    │   ├─► source_type: "web"
    │   ├─► tag: "blog"
    │   ├─► post_title, post_slug, post_url
    │   └─► is_blog_post: True
    │
    └─► Return All Chunks
        └─► List[Document]
```

---

## Functions

### `fetch_posts(url, start_page=1, max_pages=14)`
**Location:** `app/helpers.py` (approximate line 150+)

**Purpose:** Fetch blog posts from WordPress API with pagination

**What it does:**
1. Builds WordPress API URL: `{url}/wp-json/wp/v2/posts?per_page=100&page={page}`
2. Fetches posts page by page
3. Preserves existing query parameters
4. Handles pagination automatically
5. Returns all posts from all pages

**Parameters:**
- `url`: WordPress API base URL
- `start_page`: Starting page number (default: 1)
- `max_pages`: Maximum pages to fetch (default: 14)

**Returns:** List of post dictionaries

---

### `fetch_web_content(url)`
**Location:** `app/helpers.py` (line 181+)

**Purpose:** Main function to process blog posts

**What it does:**
1. Fetches posts using `fetch_posts()`
2. For each post:
   - Extracts metadata (title, slug, link)
   - Extracts content HTML
   - Cleans HTML with BeautifulSoup
   - Adds title to content
   - Chunks content
   - Adds metadata to each chunk
3. Returns all chunked documents

**Returns:** List of LangChain Documents

---

### `fetch_latest_web_content(url, max_posts=100)`
**Location:** `app/helpers.py` (approximate line 300+)

**Purpose:** Fetch only latest blog posts (incremental update)

**What it does:**
1. Fetches latest posts (limited to `max_posts`)
2. Processes same as `fetch_web_content()`
3. Used for incremental vectorstore updates

**Returns:** List of LangChain Documents

---

## Post Processing

### HTML Cleaning
```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(content, "html.parser")
clean_text = soup.get_text(separator="\n", strip=True)
```

**What it does:**
- Removes all HTML tags
- Preserves text content
- Uses newline separator
- Strips whitespace

---

### Content Formatting
```python
content_with_title = f"# {title}\n\n{clean_text}"
```

**Format:**
- Markdown title format
- Title followed by content
- Better context for LLM

---

## Chunking

### Text Splitter
```python
RecursiveCharacterTextSplitter(
    chunk_size=1500,
    chunk_overlap=300,
    separators=["\n\n", "\n", ". ", " ", ""]
)
```

**Parameters:**
- Chunk size: 1500 tokens
- Overlap: 300 tokens (larger for blog posts)
- Separators: Paragraph, line, sentence, word

**Note:** Each post chunked separately to preserve metadata

---

## Document Creation

### Document Structure
```python
Document(
    page_content=chunk_content,  # Chunked blog content
    metadata={
        "source_type": "web",
        "source": "cloudfuze_blog",
        "tag": "blog",
        "post_title": "Blog Post Title",
        "post_slug": "blog-post-slug",
        "post_url": "https://cloudfuze.com/blog-post-url/",
        "is_blog_post": True,
        "kb_tier": "primary"
    }
)
```

---

## WordPress API

### API Endpoint
```
https://cloudfuze.com/wp-json/wp/v2/posts
```

### Query Parameters
- `per_page=100` - Posts per page
- `page={page_number}` - Page number
- Additional parameters preserved (tags, categories, etc.)

### Response Format
```json
[
    {
        "id": 123,
        "title": {"rendered": "Post Title"},
        "slug": "post-slug",
        "link": "https://cloudfuze.com/post-url/",
        "content": {"rendered": "<html>content</html>"},
        "date": "2025-01-09T10:00:00",
        ...
    }
]
```

---

## Configuration

**From `config.py`:**
```python
ENABLE_WEB_SOURCE = True
WEB_SOURCE_URL = "https://cloudfuze.com"
BLOG_START_PAGE = 1
BLOG_MAX_PAGES = 14
BLOG_POSTS_PER_PAGE = 100
```

**Total Posts:**
- Maximum: 1,400 posts (14 pages × 100 posts)
- Configurable via `BLOG_MAX_PAGES` and `BLOG_POSTS_PER_PAGE`

---

## Usage

### Process All Blogs
```python
from app.helpers import fetch_web_content

documents = fetch_web_content("https://cloudfuze.com")
# Returns List[Document]
```

### Process Latest Blogs (Incremental)
```python
from app.helpers import fetch_latest_web_content

documents = fetch_latest_web_content("https://cloudfuze.com", max_posts=100)
# Returns List[Document]
```

---

## Integration

### Vectorstore Integration
```python
from app.helpers import fetch_web_content
from app.enhanced_helpers import EnhancedVectorstoreBuilder

blog_docs = fetch_web_content(WEB_SOURCE_URL)
builder = EnhancedVectorstoreBuilder()
chunks = builder.process_documents(blog_docs, "blog")
```

### Incremental Updates
```python
# In build_enhanced_vectorstore_full()
if existing_vectorstore:
    # INCREMENTAL MODE: Only fetch latest blogs
    web_docs = fetch_latest_web_content(WEB_SOURCE_URL, max_posts=100)
else:
    # FULL BUILD MODE: Fetch all blogs
    web_docs = fetch_web_content(WEB_SOURCE_URL)
```

---

## Processing Statistics

```
[*] Fetching blog posts from https://cloudfuze.com...
[*] Fetching page 1...
[*] Fetching page 2...
...
[OK] Fetched 1,400 blog posts
[OK] Loaded 1,400 blog posts into 5,600 chunks with full metadata
```

---

## Blog Identification

### During Retrieval
Blogs identified by metadata:
```python
if metadata.get("is_blog_post") == True:
    # This is a blog post

if "blog" in metadata.get("tag", "").lower():
    # This is a blog post

if "cloudfuze.com" in metadata.get("post_url", ""):
    # This is a blog post
```

---

## Error Handling

### API Errors
- Network errors → Retry logic, timeout handling
- Invalid response → Log error, skip post
- Rate limiting → Handle 429 errors

### Processing Errors
- HTML parse errors → Log warning, continue
- Empty content → Skip post
- Chunking errors → Log error, continue

---

## Key Files

- **`app/helpers.py`** - Blog fetching functions
- **`app/enhanced_helpers.py`** - Enhanced processing
- **`app/vectorstore.py`** - Vectorstore integration

---

## Best Practices

1. **Incremental Updates:** Use `fetch_latest_web_content()` for updates
2. **Preserve Metadata:** Keep post title, slug, URL in metadata
3. **Chunk Per Post:** Chunk each post separately
4. **HTML Cleaning:** Remove HTML but preserve structure
5. **Title Context:** Add title to content for better retrieval

---

## Dependencies

### Required
- **requests** - HTTP requests
- **beautifulsoup4** - HTML parsing
- **langchain** - Document processing

### Installation
```bash
pip install requests beautifulsoup4 langchain
```

---

**Last Updated:** 2025-01-09  
**File:** `app/helpers.py`
