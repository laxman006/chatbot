# Feedback & Auto-Correction Feature

## Overview

Allows users to provide feedback (thumbs up/down) on responses. Negative feedback triggers automatic response improvement using LLM.

---

## Related Files

### Backend Files

#### Feedback Endpoints
- **`app/endpoints.py`**
  - `POST /feedback` - Submit feedback (line 3139)
  - `track_feedback_history()` - Track feedback (line 3232)
  - `should_trigger_auto_correction()` - Check if auto-correction needed (line 3278)
  - `trigger_auto_correction()` - Trigger auto-correction (line 3338)
  - `generate_improved_response()` - Generate improved response (line 3379)
  - `save_corrected_response()` - Save corrected response (line 3396)
  - `get_feedback_stats_for_question()` - Get feedback stats (line 3306)

#### Corrected Responses
- **`app/endpoints.py`**
  - `load_corrected_responses()` - Load corrected responses (line 697)
  - `find_similar_corrected_response()` - Find similar corrected response (line 708)
  - `GET /dataset/corrected-responses` - Get corrected responses (line 3959)
  - `DELETE /dataset/corrected-responses` - Clear corrected responses (line 3979)

#### Auto-Correction Workflow
- **`app/endpoints.py`**
  - `trigger_auto_correction_workflow()` - Full auto-correction workflow (line 5599)
  - `generate_improved_response()` - Generate improved response (line 5617)
  - `save_correction_to_dataset()` - Save to dataset (line 5699)
  - `update_langfuse_trace()` - Update Langfuse trace (line 5733)

#### Langfuse Integration
- **`app/langfuse_integration.py`**
  - Feedback tracking in Langfuse
  - Trace updates with corrected responses

### Frontend Files

#### Feedback Components
- **`frontend/src/components/ChatInterface.tsx`**
  - Thumbs up/down buttons
  - Feedback submission
  - Feedback state management

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `submitFeedback()` - Submit feedback API call

---

## Feature Workflow

1. **User receives response** → Response displayed
2. **User provides feedback** → Thumbs up or down
3. **Feedback tracked** → Saved to Langfuse and MongoDB
4. **Negative feedback** → Triggers auto-correction check
5. **Auto-correction triggered** → If threshold met (e.g., 2+ negative)
6. **Improved response generated** → LLM generates better response
7. **Response saved** → Saved to corrected responses dataset
8. **Future queries** → Similar queries use corrected response

---

## Key Functions

### Backend
- `submit_feedback()` - Submit feedback endpoint
- `trigger_auto_correction()` - Trigger auto-correction
- `generate_improved_response()` - Generate improved response
- `save_corrected_response()` - Save corrected response
- `find_similar_corrected_response()` - Find similar corrected response

### Frontend
- Feedback buttons in chat interface
- `submitFeedback()` - Submit feedback API call

---

## Feedback Types

### Thumbs Up
- Positive feedback
- Tracks satisfaction
- No auto-correction triggered

### Thumbs Down
- Negative feedback
- Optional comment
- May trigger auto-correction

---

## Auto-Correction Logic

### Trigger Conditions
1. **Negative feedback count** - 2+ negative feedbacks for same question
2. **User comment** - User provides improvement comment
3. **Similarity threshold** - Question similarity > 0.7

### Correction Process
1. **Extract context** - Get original query, response, feedback
2. **Generate improved response** - LLM generates better answer
3. **Save to dataset** - Store corrected response
4. **Update Langfuse** - Update trace with corrected response
5. **Future use** - Similar queries use corrected response

---

## Corrected Responses Dataset

### Storage
- Stored in memory (loaded at startup)
- Can be persisted to file/database
- Format: `{question: str, corrected_response: str, trace_id: str}`

### Matching
- Uses similarity search (threshold: 0.7)
- Finds most similar question
- Returns corrected response if found

---

## Feedback Statistics

### Per Question
- Total feedback count
- Positive feedback count
- Negative feedback count
- Feedback ratio

### Per User
- Total feedback given
- Feedback breakdown

### Per Session
- Session feedback summary

---

## Configuration

**Auto-Correction Threshold:**
- Minimum negative feedbacks: 2
- Similarity threshold: 0.7

**Feedback Tracking:**
- Langfuse integration
- MongoDB storage (if implemented)

---

## Database Schema

### feedback_events (if exists)
```python
{
    "trace_id": str,
    "user_id": str,
    "rating": "thumbs_up" | "thumbs_down",
    "comment": str,
    "created_at": datetime
}
```

### corrected_responses
```python
{
    "question": str,
    "corrected_response": str,
    "original_response": str,
    "trace_id": str,
    "user_comment": str,
    "created_at": datetime
}
```

---

## Usage Flow

### User Provides Feedback
1. User clicks thumbs up/down
2. Optional comment entered
3. Feedback submitted to backend
4. Backend tracks feedback
5. Checks auto-correction trigger

### Auto-Correction Triggered
1. Negative feedback threshold met
2. LLM generates improved response
3. Response saved to dataset
4. Langfuse trace updated
5. Future similar queries use corrected response

---

**Last Updated:** 2025-01-09
