# Deployment Scripts Documentation

## Overview

Shell scripts for deploying the CloudFuze Chatbot application to various environments.

---

## Deployment Scripts

### `deploy.sh` (Main Deployment)
**Location:** `deploy.sh`

**Purpose:** Main Docker deployment script

**What it does:**
1. Checks Docker and Docker Compose installation
2. Creates `.env` file if missing
3. Stops existing containers
4. Optionally cleans old images
5. Builds and starts services
6. Waits for services to be ready
7. Checks service health
8. Displays service status

**Usage:**
```bash
# Standard deployment
./deploy.sh

# Clean deployment (remove old images)
./deploy.sh --clean
```

**Features:**
- Colored output (status, success, warning, error)
- Health checks
- Error handling
- Service status display

**Checks:**
- Docker installation
- Docker Compose installation
- `.env` file existence
- Service health endpoints

---

### `deploy-ai.sh` (AI Services Deployment)
**Location:** `deploy-ai.sh`

**Purpose:** Deploy with AI/ML services

**What it does:**
1. Similar to `deploy.sh`
2. Uses `docker-compose.ai.yml`
3. Includes AI service configurations
4. Sets up ML model serving

**Usage:**
```bash
./deploy-ai.sh
```

**Features:**
- AI service integration
- ML model serving
- GPU support (if available)

---

### `deploy-newcf3.sh` (New CF3 Server)
**Location:** `deploy-newcf3.sh`

**Purpose:** Deploy to new CF3 server

**What it does:**
1. Server-specific deployment
2. Custom configuration
3. Environment-specific settings

**Usage:**
```bash
./deploy-newcf3.sh
```

---

### `deploy-ubuntu.sh` (Ubuntu Deployment)
**Location:** `deploy-ubuntu.sh`

**Purpose:** Ubuntu-specific deployment script

**What it does:**
1. Ubuntu-specific package installation
2. System service setup
3. Ubuntu-optimized configuration

**Usage:**
```bash
./deploy-ubuntu.sh
```

**Features:**
- Systemd service setup
- Ubuntu package management
- Service auto-start

---

### `deploy-with-frontend.sh` (Full Stack)
**Location:** `deploy-with-frontend.sh`

**Purpose:** Deploy backend and frontend together

**What it does:**
1. Builds backend Docker image
2. Builds frontend Next.js application
3. Deploys both services
4. Configures reverse proxy

**Usage:**
```bash
./deploy-with-frontend.sh
```

**Features:**
- Full-stack deployment
- Frontend build integration
- Unified configuration

---

### `deploy.bat` (Windows Deployment)
**Location:** `deploy.bat`

**Purpose:** Windows batch script for deployment

**What it does:**
1. Windows-specific deployment
2. PowerShell commands
3. Windows service setup

**Usage:**
```cmd
deploy.bat
```

**Features:**
- Windows compatibility
- Batch script execution
- Windows service management

---

## Service Management Scripts

### `start_server.sh` (Start Services)
**Location:** `start_server.sh`

**Purpose:** Start all services

**Usage:**
```bash
./start_server.sh
```

**What it does:**
- Starts Docker containers
- Waits for services
- Checks health

---

### `restart_services.sh` (Restart Services)
**Location:** `restart_services.sh`

**Purpose:** Restart all services

**Usage:**
```bash
./restart_services.sh
```

**What it does:**
- Stops services
- Starts services
- Health checks

---

### `restart_services.bat` (Windows Restart)
**Location:** `restart_services.bat`

**Purpose:** Windows restart script

**Usage:**
```cmd
restart_services.bat
```

---

### `restart_server.bat` (Windows Server Restart)
**Location:** `restart_server.bat`

**Purpose:** Windows server restart

**Usage:**
```cmd
restart_server.bat
```

---

## Setup Scripts

### `setup_selenium.sh` (Selenium Setup)
**Location:** `setup_selenium.sh`

**Purpose:** Set up Selenium for SharePoint extraction

**What it does:**
1. Installs Chrome/Chromium
2. Installs ChromeDriver
3. Configures Selenium
4. Tests installation

**Usage:**
```bash
./setup_selenium.sh
```

---

### `setup_selenium.bat` (Windows Selenium Setup)
**Location:** `setup_selenium.bat`

**Purpose:** Windows Selenium setup

**Usage:**
```cmd
setup_selenium.bat
```

---

## Quick Start Scripts

### `quick-start.sh` (Quick Start)
**Location:** `quick-start.sh`

**Purpose:** Quick start for development

**What it does:**
1. Checks prerequisites
2. Sets up environment
3. Starts services
4. Opens browser

**Usage:**
```bash
./quick-start.sh
```

---

### `quick-start.bat` (Windows Quick Start)
**Location:** `quick-start.bat`

**Purpose:** Windows quick start

**Usage:**
```cmd
quick-start.bat
```

---

## Auto-Correction Scripts

### `run_auto_correction.sh` (Auto-Correction)
**Location:** `run_auto_correction.sh`

**Purpose:** Run auto-correction script

**Usage:**
```bash
./run_auto_correction.sh
```

**What it does:**
- Runs `scripts/auto_correct_low_scores.py`
- Continuous polling mode
- Logs output

---

### `run_auto_correction.bat` (Windows Auto-Correction)
**Location:** `run_auto_correction.bat`

**Purpose:** Windows auto-correction

**Usage:**
```cmd
run_auto_correction.bat
```

---

## Script Features

### Common Patterns

**Color Output:**
```bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}
```

**Error Handling:**
```bash
if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi
```

**Health Checks:**
```bash
if curl -f http://localhost:8002/health > /dev/null 2>&1; then
    print_success "Backend service is healthy"
else
    print_error "Backend service is not responding"
    exit 1
fi
```

---

## Environment Setup

### `.env` File Creation
```bash
if [ ! -f .env ]; then
    cat > .env << EOF
OPENAI_API_KEY=your_key_here
MICROSOFT_CLIENT_ID=your_id_here
# ... more variables
EOF
fi
```

---

## Best Practices

1. **Check Prerequisites:** Always check Docker/Docker Compose
2. **Health Checks:** Verify services are healthy
3. **Error Handling:** Handle errors gracefully
4. **Colored Output:** Use colors for better UX
5. **Logging:** Log important operations
6. **Dry Run:** Support dry-run mode when possible

---

## Troubleshooting

### Common Issues

**Docker Not Found:**
- Install Docker
- Check PATH
- Verify installation

**Docker Compose Not Found:**
- Install Docker Compose
- Check version compatibility

**Service Not Starting:**
- Check logs: `docker-compose logs`
- Verify environment variables
- Check port availability

**Health Check Failures:**
- Wait longer for startup
- Check service dependencies
- Verify health endpoint

---

## Key Files

- **`deploy.sh`** - Main deployment script
- **`deploy-ai.sh`** - AI services deployment
- **`deploy-newcf3.sh`** - New CF3 server deployment
- **`deploy-ubuntu.sh`** - Ubuntu deployment
- **`deploy-with-frontend.sh`** - Full-stack deployment
- **`deploy.bat`** - Windows deployment
- **`start_server.sh`** - Start services
- **`restart_services.sh`** - Restart services
- **`setup_selenium.sh`** - Selenium setup
- **`quick-start.sh`** - Quick start

---

**Last Updated:** 2025-01-09  
**Location:** Root directory
