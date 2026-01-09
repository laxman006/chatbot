# Environment Setup Documentation

## Overview

Environment configuration, variables, and setup instructions for the CloudFuze Chatbot.

---

## Environment Files

### `.env` (Main Environment File)
**Location:** `.env` (not in repository, created from template)

**Purpose:** Main environment configuration file

**Required Variables:**
```bash
# OpenAI API Key
OPENAI_API_KEY=your_openai_api_key_here

# Microsoft OAuth Configuration
MICROSOFT_CLIENT_ID=your_microsoft_client_id_here
MICROSOFT_CLIENT_SECRET=your_microsoft_client_secret_here
MICROSOFT_TENANT=your_microsoft_tenant_id_here

# Langfuse Configuration
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key_here
LANGFUSE_SECRET_KEY=your_langfuse_secret_key_here
LANGFUSE_HOST=http://localhost:3100

# MongoDB Configuration
MONGODB_URL=mongodb://mongodb:27017
MONGODB_DATABASE=slack2teams
MONGODB_CHAT_COLLECTION=chat_histories
```

**Optional Variables:**
```bash
# Feature Flags
ENABLE_WEB_SOURCE=true
ENABLE_PDF_SOURCE=false
ENABLE_EXCEL_SOURCE=false
ENABLE_SHAREPOINT_SOURCE=true
ENABLE_OUTLOOK_SOURCE=false
ENABLE_TRANSCRIPT_PROCESSING=true

# Source Paths
WEB_SOURCE_URL=https://cloudfuze.com/wp-json/wp/v2/posts
PDF_SOURCE_DIR=./data/pdfs
EXCEL_SOURCE_DIR=./data/excel
SHAREPOINT_SITE_URL=https://cloudfuzecom.sharepoint.com/sites/DOC360
SHAREPOINT_START_PAGE=/SitePages/...
OUTLOOK_USER_EMAIL=user@cloudfuze.com
OUTLOOK_FOLDER_NAME=Inbox

# Vectorstore
INITIALIZE_VECTORSTORE=false
CHROMA_DB_PATH=./data/chroma_db
```

---

### `env.ai.example` (AI Services Template)
**Location:** `env.ai.example`

**Purpose:** Template for AI services environment

**Features:**
- AI service configurations
- ML model settings
- GPU configurations (if available)

**Usage:**
```bash
cp env.ai.example .env.ai
# Edit .env.ai with your values
```

---

## Configuration File

### `config.py` (Python Configuration)
**Location:** `config.py`

**Purpose:** Python application configuration

**Sections:**
- API keys and secrets
- Database configurations
- Feature flags
- Source paths
- System prompts
- Scoring weights
- Thresholds

**Environment Variable Loading:**
```python
import os

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
ENABLE_WEB_SOURCE = os.getenv("ENABLE_WEB_SOURCE", "false").lower() == "true"
```

---

## Setup Instructions

### Initial Setup

1. **Clone Repository:**
   ```bash
   git clone <repository-url>
   cd slack2teams-2-confident-chatbot
   ```

2. **Create `.env` File:**
   ```bash
   cp env.ai.example .env
   # Edit .env with your values
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set Up Environment Variables:**
   - Add OpenAI API key
   - Add Microsoft OAuth credentials
   - Add Langfuse keys (if using)
   - Configure MongoDB URL
   - Set feature flags

5. **Initialize Vectorstore (if needed):**
   ```bash
   export INITIALIZE_VECTORSTORE=true
   python -c "from app.vectorstore import build_enhanced_vectorstore_full; build_enhanced_vectorstore_full()"
   ```

---

## Docker Environment

### Docker Compose Environment

**Variables in `docker-compose.yml`:**
```yaml
environment:
  - OPENAI_API_KEY=${OPENAI_API_KEY}
  - MONGODB_URL=${MONGODB_URL}
  # ... more variables
```

**Loading from `.env`:**
- Docker Compose automatically loads `.env` file
- Variables available in containers
- Can override in `docker-compose.yml`

---

## Development Environment

### Local Development Setup

1. **Python Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```

2. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set Environment Variables:**
   - Create `.env` file
   - Or export variables:
     ```bash
     export OPENAI_API_KEY=your_key
     export MONGODB_URL=mongodb://localhost:27017
     ```

4. **Run Application:**
   ```bash
   python server.py
   ```

---

## Production Environment

### Production Setup

1. **Use Production Dockerfile:**
   ```bash
   docker build -f Dockerfile.prod -t slack2teams-backend:prod .
   ```

2. **Production Environment Variables:**
   - Use secrets management (not `.env` file)
   - Set via Docker secrets or environment
   - Use production database URLs
   - Enable only needed features

3. **Deploy:**
   ```bash
   docker-compose -f docker-compose.prod.yml up -d
   ```

---

## Environment Variables Reference

### API Keys

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `OPENAI_API_KEY` | OpenAI API key | Yes | - |
| `MICROSOFT_CLIENT_ID` | Microsoft OAuth client ID | Yes | - |
| `MICROSOFT_CLIENT_SECRET` | Microsoft OAuth secret | Yes | - |
| `MICROSOFT_TENANT` | Microsoft tenant ID | Yes | - |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key | No | - |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key | No | - |
| `LANGFUSE_HOST` | Langfuse host URL | No | `http://localhost:3100` |

### Database

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MONGODB_URL` | MongoDB connection string | Yes | `mongodb://localhost:27017` |
| `MONGODB_DATABASE` | MongoDB database name | No | `slack2teams` |
| `MONGODB_CHAT_COLLECTION` | Chat collection name | No | `chat_histories` |

### Feature Flags

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_WEB_SOURCE` | Enable blog processing | `false` |
| `ENABLE_PDF_SOURCE` | Enable PDF processing | `false` |
| `ENABLE_EXCEL_SOURCE` | Enable Excel processing | `false` |
| `ENABLE_SHAREPOINT_SOURCE` | Enable SharePoint processing | `false` |
| `ENABLE_OUTLOOK_SOURCE` | Enable Outlook processing | `false` |
| `ENABLE_TRANSCRIPT_PROCESSING` | Enable transcript processing | `false` |
| `INITIALIZE_VECTORSTORE` | Initialize vectorstore on startup | `false` |

### Source Paths

| Variable | Description | Default |
|----------|-------------|---------|
| `WEB_SOURCE_URL` | Blog API URL | `https://cloudfuze.com/wp-json/wp/v2/posts` |
| `PDF_SOURCE_DIR` | PDF directory | `./data/pdfs` |
| `EXCEL_SOURCE_DIR` | Excel directory | `./data/excel` |
| `SHAREPOINT_SITE_URL` | SharePoint site URL | - |
| `SHAREPOINT_START_PAGE` | SharePoint start page | - |
| `OUTLOOK_USER_EMAIL` | Outlook user email | - |
| `OUTLOOK_FOLDER_NAME` | Outlook folder name | `Inbox` |

---

## Security Best Practices

1. **Never Commit `.env`:** Add to `.gitignore`
2. **Use Secrets Management:** Use Docker secrets or cloud secrets
3. **Rotate Keys:** Regularly rotate API keys
4. **Limit Access:** Restrict access to environment files
5. **Audit Logs:** Monitor access to sensitive variables

---

## Troubleshooting

### Common Issues

**Variables Not Loading:**
- Check `.env` file exists
- Verify variable names match
- Check file permissions

**Docker Environment:**
- Verify variables in `docker-compose.yml`
- Check container environment: `docker exec container env`
- Restart containers after changes

**Python Environment:**
- Verify `os.getenv()` usage
- Check variable names (case-sensitive)
- Reload application after changes

---

## Key Files

- **`.env`** - Main environment file (not in repo)
- **`env.ai.example`** - AI services template
- **`config.py`** - Python configuration
- **`docker-compose.yml`** - Docker environment

---

**Last Updated:** 2025-01-09  
**Location:** Root directory
