# Image Interleaving Enhancements

## Overview

Enhanced the SharePoint ingestion and RAG system to support interleaved "text → image → text" rendering using positional metadata instead of anchor tags. This approach is more robust and doesn't require re-ingesting all documents.

## Changes Made

### 1. PDF Processor Enhancements (`app/pdf_processor.py`)

#### Added Content-Type Classification
- **New Function**: `classify_image_content(ocr_text, image_bytes)`
- **Purpose**: Classifies images as `diagram`, `ui_screenshot`, or `image_context`
- **Logic**:
  - UI Screenshots: Detects keywords like "DNS", "IP address", "settings", "configuration"
  - Diagrams: Detects minimal text with technical patterns (arrows, boxes, architecture terms)
  - Default: Generic `image_context`

#### Added Positional Metadata
- **Image Chunks**: Added `vertical_position` (top coordinate), `image_width`, `image_height`
- **Text Chunks**: Added `vertical_position` (first word's top coordinate)
- **Purpose**: Enables frontend to interleave images based on their position on the page

#### Enhanced Image Metadata
```python
{
    "chunk_type": "image_context",
    "content_type": "diagram",  # NEW: diagram, ui_screenshot, or image_context
    "vertical_position": 150.5,  # NEW: Position for interleaving
    "image_width": 400.0,        # NEW: Image dimensions
    "image_height": 300.0,       # NEW: Image dimensions
    "page_number": 5,
    "image_index": 0,
    ...
}
```

### 2. Weaviate Retriever Enhancements (`app/weaviate_retriever.py`)

#### New Function: `fetch_images_by_page_proximity()`
- **Purpose**: Fetches images from pages where text chunks were found
- **Parameters**:
  - `doc_id`: Document ID
  - `page_numbers`: List of page numbers where text chunks were found
  - `limit_per_page`: Max images per page (default: 3)
  - `total_limit`: Max total images (default: 20)
- **Returns**: Images sorted by `page_number`, then `image_index`, then `vertical_position`

**Usage**:
```python
# Fetch images from pages 2, 3, 5 where text chunks were found
images = fetch_images_by_page_proximity(
    doc_id="sharepoint:abc123",
    page_numbers=[2, 3, 5],
    limit_per_page=2,
    total_limit=10
)
```

### 3. RAG Node Enhancements (`app/rag/nodes.py`)

#### Enhanced `attach_nearby_images()` Function

**Key Improvements**:
1. **Page-Proximity Attachment**: For conceptual queries, attaches images from pages where text chunks were found
2. **Content-Type Prioritization**: Prefers `diagram` images over `ui_screenshot` for conceptual queries
3. **Positional Metadata**: Includes `vertical_position` in attached images for frontend interleaving
4. **Increased Limits**: Increased `max_conceptual_images` from 3 to 5 for better interleaving

**New Behavior**:
- **Conceptual Queries**: 
  - Tracks page numbers where text chunks were found
  - Fetches images from those specific pages using `fetch_images_by_page_proximity()`
  - Sorts by content_type (diagrams first)
  - Falls back to doc-level fetch if no page-proximity images found

- **Procedural Queries**: 
  - Unchanged: Still uses section-based attachment
  - Attaches up to 2 images per (doc_id, section_title)

**Enhanced Image Metadata**:
```python
{
    "data": "base64...",
    "page_number": 5,
    "image_index": 0,
    "vertical_position": 150.5,  # NEW: For interleaving
    "content_type": "diagram",    # NEW: diagram, ui_screenshot, image_context
    "section": "Architecture",
    ...
}
```

## How It Works

### 1. During Ingestion

1. **PDF Extraction**:
   - Extracts images with `vertical_position` (top coordinate)
   - Classifies images as `diagram`, `ui_screenshot`, or `image_context`
   - Extracts text chunks with `vertical_position` (first word's top)

2. **Storage**:
   - Images stored as separate `image_context` chunks
   - Text stored as `explanation` chunks
   - Both include `page_number` and `vertical_position`

### 2. During Retrieval

1. **Text Retrieval**:
   - Standard vector search retrieves text chunks
   - System tracks which `doc_id` and `page_number` values were found

2. **Image Attachment**:
   - For conceptual queries: Fetches images from pages where text was found
   - Sorts by `page_number`, then `image_index`, then `vertical_position`
   - Prefers diagrams over screenshots

3. **Frontend Interleaving**:
   - Frontend receives text chunks and attached images
   - Groups by `page_number`
   - Sorts text by `vertical_position`
   - Sorts images by `image_index` and `vertical_position`
   - Interleaves: text → image → text based on position

## Frontend Integration Example

```typescript
interface ImageAttachment {
  data: string;  // base64
  page_number: number;
  image_index: number;
  vertical_position?: number;
  content_type: "diagram" | "ui_screenshot" | "image_context";
  section: string;
}

interface TextChunk {
  content: string;
  page_number: number;
  vertical_position?: number;
  section_title: string;
}

function interleaveContent(
  textChunks: TextChunk[],
  images: ImageAttachment[]
): Array<{ type: "text" | "image"; data: any }> {
  // Group by page
  const byPage = new Map<number, { texts: TextChunk[]; images: ImageAttachment[] }>();
  
  for (const text of textChunks) {
    const page = text.page_number;
    if (!byPage.has(page)) {
      byPage.set(page, { texts: [], images: [] });
    }
    byPage.get(page)!.texts.push(text);
  }
  
  for (const img of images) {
    const page = img.page_number;
    if (!byPage.has(page)) {
      byPage.set(page, { texts: [], images: [] });
    }
    byPage.get(page)!.images.push(img);
  }
  
  // Sort and interleave
  const result: Array<{ type: "text" | "image"; data: any }> = [];
  
  for (const [pageNum, { texts, images }] of byPage) {
    // Sort texts by vertical_position
    texts.sort((a, b) => (a.vertical_position || 0) - (b.vertical_position || 0));
    
    // Sort images by image_index, then vertical_position
    images.sort((a, b) => {
      if (a.image_index !== b.image_index) {
        return a.image_index - b.image_index;
      }
      return (a.vertical_position || 0) - (b.vertical_position || 0);
    });
    
    // Interleave: text → image → text
    let imgIdx = 0;
    for (const text of texts) {
      result.push({ type: "text", data: text });
      
      // Insert images that come after this text
      while (imgIdx < images.length && 
             (images[imgIdx].vertical_position || 0) < (text.vertical_position || 0) + 100) {
        result.push({ type: "image", data: images[imgIdx] });
        imgIdx++;
      }
    }
    
    // Add remaining images
    while (imgIdx < images.length) {
      result.push({ type: "image", data: images[imgIdx] });
      imgIdx++;
    }
  }
  
  return result;
}
```

## Benefits Over Anchor Tags

1. **No Re-Ingestion Required**: Works with existing documents
2. **Chunking-Safe**: Positional metadata survives chunking
3. **More Flexible**: Can adjust interleaving logic without changing stored data
4. **Better Performance**: No regex scanning for anchor tags
5. **Content-Aware**: Can prioritize diagrams over screenshots

## Testing

### Test Content-Type Classification

```python
from app.pdf_processor import classify_image_content

# Test UI Screenshot
ocr_text = "DNS Server: 8.8.8.8\nIP Address: 192.168.1.1\nSettings"
assert classify_image_content(ocr_text, None) == "ui_screenshot"

# Test Diagram
ocr_text = "Start → Process → Decision → End"
assert classify_image_content(ocr_text, None) == "diagram"

# Test Generic
ocr_text = "This is a photo of a building"
assert classify_image_content(ocr_text, None) == "image_context"
```

### Test Page-Proximity Retrieval

```python
from app.weaviate_retriever import fetch_images_by_page_proximity

# Fetch images from pages 2, 3, 5
images = fetch_images_by_page_proximity(
    doc_id="sharepoint:architecture.pdf",
    page_numbers=[2, 3, 5],
    limit_per_page=2
)

# Verify images are sorted correctly
assert all(img.metadata["page_number"] in [2, 3, 5] for img in images)
```

## Migration Notes

- **No Breaking Changes**: Existing documents continue to work
- **Backward Compatible**: Old documents without `vertical_position` still work (position defaults to None)
- **Gradual Enhancement**: New documents get positional metadata automatically
- **Optional Re-Ingestion**: Can re-ingest specific documents to get positional metadata for better interleaving

## Future Enhancements

1. **DOCX Positional Metadata**: Add `vertical_position` to DOCX extraction
2. **PPTX Positional Metadata**: Add slide position tracking
3. **Smart Interleaving**: Use LLM to determine optimal image placement
4. **Image Relevance Scoring**: Score images by relevance to query, not just position
