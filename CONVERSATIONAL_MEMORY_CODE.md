# Conversational Memory System - Complete Code Reference

## Problem Statement
The conversational memory system uses a "Three-Gate" approach to decide when to inject conversation context:
1. **Gate 1**: Follow-up detection (keyword-based)
2. **Gate 2**: Topic continuity (semantic similarity)
3. **Gate 3**: Default behavior (drop context for new topics)

**Issue**: "Explain it briefly" is not being detected by Gate 1, even though "explain briefly" is in the keyword list.

---

## 1. Configuration (`config.py`)

```python
# Conversational Memory Configuration
ENABLE_SEMANTIC_SIMILARITY_CHECK = os.getenv("ENABLE_SEMANTIC_SIMILARITY_CHECK", "true").lower() == "true"
CONTEXT_SIMILARITY_THRESHOLD = float(os.getenv("CONTEXT_SIMILARITY_THRESHOLD", "0.65"))
```

---

## 2. Gate 1: Follow-up Detection (`app/endpoints.py`)

```python
def is_follow_up_question(question: str) -> bool:
    """
    Gate 1: Detect if a question is a follow-up that explicitly depends on prior context.
    Uses keyword heuristics to catch 80-90% of conversational dependencies.
    
    Returns True if question is a follow-up, False otherwise.
    """
    question_lower = question.lower().strip()
    
    # Follow-up keywords and patterns (ordered by specificity - longer phrases first)
    FOLLOW_UP_KEYWORDS = [
        "explain briefly", "explain more", "explain it", "explain that",
        "tell me more", "what about", "how about",
        "can you elaborate", "can you explain",
        "same thing", "as you said", "earlier", "before",
        "you mentioned", "you said", "according to you",
        "in that", "for that", "about that",
        "the same", "similar", "also",
        "what else", "anything else", "more details",
        "go on", "continue",
        "how does it", "why does it", "when does it",
        "which one", "which of those"
    ]
    
    # Debug: log the question being checked
    print(f"[CONTEXT] Gate 1: Checking question '{question}' (lowercase: '{question_lower}')")
    
    # Check for follow-up keywords (longer phrases first to avoid partial matches)
    for keyword in FOLLOW_UP_KEYWORDS:
        if keyword in question_lower:
            print(f"[CONTEXT] Gate 1: Matched keyword '{keyword}'")
            return True
    
    # Check for pronouns (after checking phrases to avoid false positives)
    if any(word in question_lower for word in ["it", "that", "this", "those", "these", "they", "them"]):
        # Only match if question is short or contains these pronouns
        words = question.split()
        if len(words) <= 5:  # Short questions with pronouns are likely follow-ups
            return True
    
    # Check for very short questions with pronouns (likely follow-ups)
    words = question.split()
    if len(words) <= 3:
        if any(word in question_lower for word in ["it", "that", "this", "they", "them"]):
            return True
    
    return False
```

---

## 3. Gate 2: Semantic Similarity (`app/endpoints.py`)

```python
def _word_overlap_similarity(text1: str, text2: str) -> float:
    """Fallback similarity using word overlap (Jaccard similarity)."""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
    
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union) if union else 0.0

def calculate_semantic_similarity(text1: str, text2: str) -> float:
    """
    Gate 2: Calculate semantic similarity between two texts using embeddings.
    Returns similarity score between 0 and 1. Higher score = more similar.
    
    Uses OpenAI embeddings (same as vectorstore) for consistency.
    Falls back to word overlap if embeddings unavailable.
    """
    try:
        from langchain_openai import OpenAIEmbeddings
        from config import OPENAI_API_KEY
        
        if not OPENAI_API_KEY:
            # Fallback to word overlap
            return _word_overlap_similarity(text1, text2)
        
        # Use OpenAI embeddings (same model as vectorstore)
        embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Get embeddings
        emb1 = embeddings.embed_query(text1)
        emb2 = embeddings.embed_query(text2)
        
        # Calculate cosine similarity
        import numpy as np
        dot_product = np.dot(emb1, emb2)
        norm1 = np.linalg.norm(emb1)
        norm2 = np.linalg.norm(emb2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        similarity = dot_product / (norm1 * norm2)
        return float(similarity)
        
    except Exception as e:
        print(f"[CONTEXT] Semantic similarity calculation failed: {e}, using word overlap")
        return _word_overlap_similarity(text1, text2)
```

---

## 4. Three-Gate Decision Function (`app/endpoints.py`)

```python
async def should_use_conversation_context(
    question: str, 
    conversation_id: str
) -> Tuple[bool, str]:
    """
    Three-Gate System: Decide if conversation context should be used.
    
    This is the SINGLE SOURCE OF TRUTH for context injection decisions.
    
    Decision Logic:
    1. Gate 1: If follow-up question → USE context
    2. Gate 2: If semantic similarity >= threshold → USE context (same topic)
    3. Gate 3: Otherwise → DROP context (new topic)
    
    Returns:
        (should_use_context: bool, conversation_context: str)
    """
    from config import ENABLE_SEMANTIC_SIMILARITY_CHECK, CONTEXT_SIMILARITY_THRESHOLD
    
    # Gate 1: Follow-up detection (fast, cheap)
    gate1_result = is_follow_up_question(question)
    if gate1_result:
        print(f"[CONTEXT] ✓ Gate 1 PASSED: Follow-up detected - '{question}'")
        context = await get_conversation_context(conversation_id)
        return (True, context)
    else:
        print(f"[CONTEXT] ✗ Gate 1 FAILED: Not a follow-up - '{question}'")
    
    # Gate 2: Topic continuity check (semantic similarity)
    if ENABLE_SEMANTIC_SIMILARITY_CHECK:
        last_message = await mongodb_memory.get_last_assistant_message(conversation_id)
        
        if not last_message:
            # No previous conversation
            print(f"[CONTEXT] ✗ No previous conversation - treating as new topic")
            return (False, "")
        
        # Calculate semantic similarity
        similarity = calculate_semantic_similarity(question, last_message)
        print(f"[CONTEXT] Gate 2: Semantic similarity = {similarity:.3f} (threshold: {CONTEXT_SIMILARITY_THRESHOLD})")
        
        if similarity >= CONTEXT_SIMILARITY_THRESHOLD:
            print(f"[CONTEXT] ✓ Gate 2 PASSED: Same topic detected - using context")
            context = await get_conversation_context(conversation_id)
            return (True, context)
        else:
            print(f"[CONTEXT] ✗ Gate 2 FAILED: Topic switch detected - dropping context")
            return (False, "")
    else:
        # Semantic check disabled - only use context for explicit follow-ups
        print(f"[CONTEXT] Semantic check disabled - no context for non-follow-ups")
        return (False, "")
```

---

## 5. MongoDB Memory Functions (`app/mongodb_memory.py`)

```python
# In MongoDBMemoryManager class:

async def get_conversation_context(self, user_id: str) -> str:
    """Get formatted conversation context for a user (legacy method)."""
    conversation = await self.get_or_create_user_conversation(user_id)
    
    if not conversation:
        return ""
    
    context = "\n\nPrevious conversation:\n"
    # Get last 5 messages for context
    for msg in conversation[-5:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        context += f"{role}: {msg['content']}\n"
    
    return context

async def get_last_assistant_message(self, user_id: str) -> Optional[str]:
    """
    Get the last assistant message from conversation history.
    Used for topic continuity checking via semantic similarity.
    """
    conversation = await self.get_or_create_user_conversation(user_id)
    
    if not conversation:
        return None
    
    # Find last assistant message (iterate backwards)
    for msg in reversed(conversation):
        if msg.get("role") == "assistant":
            return msg.get("content", "")
    
    return None
```

---

## 6. Usage in Chat Endpoints (`app/endpoints.py`)

### In `/chat` endpoint (non-streaming):
```python
# Handle informational queries with document retrieval
# Use three-gate system for relevance-aware conversation context
should_use_context, conversation_context = await should_use_conversation_context(
    question, 
    conversation_id
)

if should_use_context and conversation_context:
    # Include conversation context in the query
    enhanced_query = f"{conversation_context}\n\nCurrent question: {question}"
else:
    enhanced_query = question
```

### In `/chat/stream` endpoint (streaming):
```python
# Use three-gate system for relevance-aware conversation context
should_use_context, conversation_context_str = await should_use_conversation_context(
    question,
    conversation_id
)

if should_use_context and conversation_context_str:
    enhanced_query = f"{conversation_context_str}\n\nCurrent question: {question}"
    conversation_context = conversation_context_str  # For metadata logging
else:
    enhanced_query = question
    conversation_context = None  # Set to None for metadata logging
```

---

## 7. Expected Behavior

### Test Case: "Explain it briefly"
- **Input**: `"Explain it briefly"`
- **Expected**: Gate 1 should match because:
  1. `"explain briefly"` is in `FOLLOW_UP_KEYWORDS` list
  2. `"explain it"` is also in the list
  3. The question contains `"it"` pronoun and is short (3 words)

### Actual Behavior (from logs):
- Gate 1 is NOT triggering
- Falls through to Gate 2
- Gate 2 shows similarity = 0.559 (below threshold 0.65)
- Context is dropped

---

## 8. Debug Logs Expected

When testing "Explain it briefly", you should see:
```
[CONTEXT] Gate 1: Checking question 'Explain it briefly' (lowercase: 'explain it briefly')
[CONTEXT] Gate 1: Matched keyword 'explain briefly'
[CONTEXT] ✓ Gate 1 PASSED: Follow-up detected - 'Explain it briefly'
```

But currently seeing:
```
[CONTEXT] Gate 2: Semantic similarity = 0.559 (threshold: 0.65)
[CONTEXT] ✗ Gate 2 FAILED: Topic switch detected - dropping context
```

This suggests Gate 1 debug logs are not appearing, meaning `is_follow_up_question()` might not be called, or the function is returning False incorrectly.

---

## 9. Potential Issues to Investigate

1. **String matching issue**: Check if `"explain briefly" in "explain it briefly"` works correctly
2. **Whitespace/encoding**: Check if there are hidden characters
3. **Function not being called**: Verify the function is actually being invoked
4. **Early return**: Check if something is returning False before keyword check
5. **Case sensitivity**: Verify `.lower().strip()` is working correctly

---

## 10. Import Statements Needed

```python
from typing import Tuple
from app.mongodb_memory import mongodb_memory, get_conversation_context
```

---

## Summary

The code structure looks correct, but "Explain it briefly" is not matching Gate 1. The debug logs added should reveal what's happening. Check:
1. Are the Gate 1 debug logs appearing?
2. What exact string is being checked?
3. Why isn't the substring match working?
