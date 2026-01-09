# 📚 Master Documentation Index

## Complete Codebase Documentation

This index provides a comprehensive guide to all functionalities, workflows, frameworks, and pipelines in the CloudFuze Chatbot system.

---

## 🗂️ Documentation Structure

### **Backend Core Documentation** (`Context_Folder/backend/`)
- [API Endpoints & Routes](./backend/API_ENDPOINTS.md)
- [Retrieval System](./backend/RETRIEVAL_SYSTEM.md)
- [LLM Integration](./backend/LLM_INTEGRATION.md)
- [Memory & Session Management](./backend/MEMORY_SESSION_MANAGEMENT.md)
- [Authentication & Authorization](./backend/AUTHENTICATION.md)
- [Query Processing Pipeline](./backend/QUERY_PROCESSING.md)
- [Scoring & Reranking](./backend/SCORING_RERANKING.md)

### **Data Processing Pipelines** (`Context_Folder/pipelines/`)
- [SharePoint Processing Pipeline](./pipelines/SHAREPOINT_PIPELINE.md)
- [PDF Processing Pipeline](./pipelines/PDF_PIPELINE.md)
- [PPTX Processing Pipeline](./pipelines/PPTX_PIPELINE.md)
- [Excel Processing Pipeline](./pipelines/EXCEL_PIPELINE.md)
- [Outlook Email Processing Pipeline](./pipelines/OUTLOOK_PIPELINE.md)
- [Transcript Processing Pipeline](./pipelines/TRANSCRIPT_PIPELINE.md)
- [Blog Processing Pipeline](./pipelines/BLOG_PIPELINE.md)

### **Frontend Documentation** (`Context_Folder/frontend/`)
- [Frontend Architecture](./frontend/FRONTEND_ARCHITECTURE.md)
- [Components Documentation](./frontend/COMPONENTS.md)
- [Pages & Routes](./frontend/PAGES_ROUTES.md)
- [State Management](./frontend/STATE_MANAGEMENT.md)
- [API Integration](./frontend/API_INTEGRATION.md)
- [Styling & UI Framework](./frontend/STYLING_UI.md)

### **Infrastructure & Storage** (`Context_Folder/infrastructure/`)
- [Vectorstore System](./infrastructure/VECTORSTORE.md)
- [MongoDB Integration](./infrastructure/MONGODB.md)
- [Langfuse Observability](./infrastructure/LANGFUSE.md)
- [Chunking Strategies](./infrastructure/CHUNKING_STRATEGIES.md)
- [Metadata Schema](./infrastructure/METADATA_SCHEMA.md)

### **Analytics & Features** (`Context_Folder/features/`)
- [Analytics System](./features/ANALYTICS.md)
- [Team Leaderboard](./features/TEAM_LEADERBOARD.md)
- [Shared Chat Sessions](./features/SHARED_CHAT.md)
- [Suggested Questions](./features/SUGGESTED_QUESTIONS.md)
- [Feedback System](./features/FEEDBACK_SYSTEM.md)
- [Auto-Correction System](./features/AUTO_CORRECTION.md)

### **Deployment Documentation** (`deployment_context/`)
- [Docker Configuration](./deployment_context/DOCKER.md)
- [Nginx Configuration](./deployment_context/NGINX.md)
- [Environment Setup](./deployment_context/ENVIRONMENT_SETUP.md)
- [Deployment Scripts](./deployment_context/DEPLOYMENT_SCRIPTS.md)
- [Production Configuration](./deployment_context/PRODUCTION_CONFIG.md)

### **Utility Scripts** (`Context_Folder/scripts/`)
- [Scripts Documentation](./scripts/SCRIPTS_INDEX.md)
- [Maintenance Scripts](./scripts/MAINTENANCE.md)
- [Data Processing Scripts](./scripts/DATA_PROCESSING.md)
- [Analytics Scripts](./scripts/ANALYTICS_SCRIPTS.md)

---

## 🏗️ System Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    USER INTERFACE (Next.js)                 │
│  - Chat Interface  - Dashboard  - Admin Panels              │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              BACKEND API (FastAPI)                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ Authentication│  │ Query Process│  │ Retrieval     │    │
│  │ & Auth        │  │ & Classification│ │ & Reranking  │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │ LLM          │  │ Memory       │  │ Analytics    │    │
│  │ Integration  │  │ Management   │  │ & Tracking   │    │
│  └──────────────┘  └──────────────┘  └──────────────┘    │
└──────┬──────────────┬──────────────┬──────────────┬───────┘
       │              │              │              │
       ▼              ▼              ▼              ▼
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ ChromaDB │  │ MongoDB  │  │ Langfuse │  │ LLM APIs │
│ Vector   │  │ Sessions │  │ Observab │  │ OpenAI/  │
│ Store    │  │ & Data   │  │ ility    │  │ Gemini   │
└──────────┘  └──────────┘  └──────────┘  └──────────┘
```

---

## 🔄 Key Workflows

1. **User Query Workflow** → See [Query Processing Pipeline](./backend/QUERY_PROCESSING.md)
2. **Document Ingestion Workflow** → See [Data Processing Pipelines](./pipelines/)
3. **Session Management Workflow** → See [Memory & Session Management](./backend/MEMORY_SESSION_MANAGEMENT.md)
4. **Analytics Tracking Workflow** → See [Analytics System](./features/ANALYTICS.md)

---

## 📖 Quick Navigation

### For Developers
- Start with [API Endpoints](./backend/API_ENDPOINTS.md)
- Review [Frontend Architecture](./frontend/FRONTEND_ARCHITECTURE.md)
- Understand [Retrieval System](./backend/RETRIEVAL_SYSTEM.md)

### For DevOps
- See [Deployment Documentation](./deployment_context/)
- Review [Docker Configuration](./deployment_context/DOCKER.md)
- Check [Environment Setup](./deployment_context/ENVIRONMENT_SETUP.md)

### For Data Engineers
- Review [Data Processing Pipelines](./pipelines/)
- Understand [Vectorstore System](./infrastructure/VECTORSTORE.md)
- Check [Chunking Strategies](./infrastructure/CHUNKING_STRATEGIES.md)

---

## 📝 Documentation Status

- ✅ Backend Core - Complete
- ✅ Data Pipelines - Complete
- ✅ Frontend - Complete
- ✅ Infrastructure - Complete
- ✅ Features - Complete
- ✅ Deployment - Complete
- ✅ Scripts - Complete

---

**Last Updated:** 2025-01-09
**Maintained By:** Development Team
