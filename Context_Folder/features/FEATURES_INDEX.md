# Features Index

## Complete Feature Documentation

This index lists all features in the CloudFuze Chatbot and their related files.

---

## 📋 All Features

### 1. [Chat & Conversation Feature](./CHAT_CONVERSATION_FEATURE.md)
**Purpose:** Core chat functionality with RAG-based responses

**Key Files:**
- `app/endpoints.py` - Chat endpoints
- `app/llm.py` - LLM integration
- `app/llm_factory.py` - LLM factory
- `bm25_retriever.py` - Keyword retrieval
- `reranker.py` - Cross-encoder reranking
- `query_expander.py` - Query expansion
- `context_compressor.py` - Context compression
- `frontend/src/components/ChatInterface.tsx` - Chat UI

---

### 2. [Authentication Feature](./AUTHENTICATION_FEATURE.md)
**Purpose:** Microsoft OAuth authentication and authorization

**Key Files:**
- `app/auth.py` - Authentication logic
- `app/session_store.py` - Session storage
- `app/endpoints.py` - OAuth endpoints
- `frontend/src/app/login/page.tsx` - Login page

---

### 3. [Session Management Feature](./SESSION_MANAGEMENT_FEATURE.md)
**Purpose:** Chat session storage and management

**Key Files:**
- `app/mongodb_memory.py` - Session storage
- `app/session_store.py` - Session management
- `app/endpoints.py` - Session endpoints
- `frontend/src/components/ChatSidebar.tsx` - Session sidebar
- `frontend/src/components/SessionCard.tsx` - Session card

---

### 4. [Shared Chat Feature](./SHARED_CHAT_FEATURE.md)
**Purpose:** Share chat sessions with others via tokens

**Key Files:**
- `app/mongodb_memory.py` - Shared chat storage
- `app/endpoints.py` - Share endpoints
- `frontend/src/app/chat/shared/[token]/page.tsx` - Shared chat page

---

### 5. [Analytics Feature](./ANALYTICS_FEATURE.md)
**Purpose:** User activity tracking and analytics dashboards

**Key Files:**
- `app/endpoints.py` - Analytics endpoints
- `app/mongodb_memory.py` - Event tracking
- `app/langfuse_integration.py` - Langfuse integration
- `frontend/src/app/admin/dashboard/page.tsx` - Dashboard
- `frontend/src/app/admin/analytics/page.tsx` - Analytics page

---

### 6. [Team Leaderboard Feature](./TEAM_LEADERBOARD_FEATURE.md)
**Purpose:** Team-based analytics and leaderboard

**Key Files:**
- `app/models/teams.py` - Team definitions
- `app/endpoints.py` - Team endpoints
- `frontend/src/app/admin/teams/page.tsx` - Team leaderboard
- `frontend/src/app/admin/teams-dashboard/page.tsx` - Team dashboard

---

### 7. [Feedback & Auto-Correction Feature](./FEEDBACK_AUTO_CORRECTION_FEATURE.md)
**Purpose:** User feedback and automatic response improvement

**Key Files:**
- `app/endpoints.py` - Feedback endpoints
- `app/langfuse_integration.py` - Feedback tracking
- `frontend/src/components/ChatInterface.tsx` - Feedback buttons

---

### 8. [Suggested Questions Feature](./SUGGESTED_QUESTIONS_FEATURE.md)
**Purpose:** Generate recommended follow-up questions

**Key Files:**
- `app/llm.py` - Question generation
- `app/routes/suggested_questions.py` - Question routes
- `app/models/suggested_question.py` - Question model
- `frontend/src/components/ChatInterface.tsx` - Question display

---

### 9. [Knowledge Base Ingestion Feature](./KNOWLEDGE_BASE_INGESTION_FEATURE.md)
**Purpose:** Process and ingest documents into vectorstore

**Key Files:**
- `app/sharepoint_processor.py` - SharePoint processing
- `app/pdf_processor.py` - PDF processing
- `app/pptx_processor.py` - PowerPoint processing
- `app/excel_processor.py` - Excel processing
- `app/outlook_processor.py` - Email processing
- `app/transcript_processor.py` - Transcript processing
- `app/vectorstore.py` - Vectorstore management
- `app/enhanced_helpers.py` - Enhanced processing

---

## 🔍 Quick Reference

### By File Type

**Backend Core:**
- Chat: `app/endpoints.py`, `app/llm.py`
- Auth: `app/auth.py`, `app/session_store.py`
- Memory: `app/mongodb_memory.py`
- Retrieval: `bm25_retriever.py`, `reranker.py`, `query_expander.py`

**Frontend:**
- Chat UI: `frontend/src/components/ChatInterface.tsx`
- Pages: `frontend/src/app/chat/`, `frontend/src/app/admin/`
- API: `frontend/src/lib/api.ts`

**Processing:**
- SharePoint: `app/sharepoint_processor.py`
- PDF: `app/pdf_processor.py`
- Transcripts: `app/transcript_processor.py`
- Vectorstore: `app/vectorstore.py`

---

## 📊 Feature Dependencies

```
Authentication
    ↓
Session Management
    ↓
Chat & Conversation
    ├─► Retrieval System
    ├─► LLM Integration
    ├─► Suggested Questions
    └─► Feedback & Auto-Correction
        ↓
Analytics
    ├─► Team Leaderboard
    └─► Langfuse Integration

Knowledge Base Ingestion
    └─► Vectorstore
        └─► Retrieval System
```

---

## 🎯 Feature Status

- ✅ Chat & Conversation - Complete
- ✅ Authentication - Complete
- ✅ Session Management - Complete
- ✅ Shared Chat - Complete
- ✅ Analytics - Complete
- ✅ Team Leaderboard - Complete
- ✅ Feedback & Auto-Correction - Complete
- ✅ Suggested Questions - Complete
- ✅ Knowledge Base Ingestion - Complete

---

**Last Updated:** 2025-01-09
