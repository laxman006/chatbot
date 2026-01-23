# ⚡ Quick Start - Jira Automation

## 📋 **What You Need to Do**

### **1. Install Package (1 command)**
```bash
pip install apscheduler
```

### **2. Update .env File (copy-paste this)**
```bash
# ============================================================================
# JIRA INTEGRATION CONFIGURATION
# ============================================================================

# Jira Server Connection
JIRA_SERVER=https://cf2020.atlassian.net
JIRA_EMAIL=laxman.kadari@cloudfuze.com
JIRA_API_TOKEN=ATATT3xFfGF0OtL31ZUKrcAmPwD8cueGm63kc9aVExy8oQGkLqsFdPeg3PKp5GblrKF_GS0uWQTMF3-XwTbHdU3LWqtiJYRoH9mIXWUeHT1YUZVlBuywcsCunZsjAIuLNMMaTyY4KwtWnF9SS9IT3Y9YF7yNjG0upyQRjUJM_qtn-Z_AQvgotjs=EE6D58E2

# Jira Query Settings
JIRA_PROJECT_KEYS=PRI,QAB
JIRA_MAX_ISSUES=10000
JIRA_JQL_QUERY=
JIRA_DATE_FILTER=

# Jira Vectorstore Configuration
JIRA_VECTORSTORE_PATH=./data/jira_chroma_db
ENABLE_JIRA_VECTORSTORE=true
INITIALIZE_JIRA_VECTORSTORE=false

# Sync Time (24-hour format: 0-23)
JIRA_SYNC_HOUR=2

# Disable Jira from main vectorstore
ENABLE_JIRA_SOURCE=false
```

### **3. Run Initial Build (1 command, ~10 minutes)**
```bash
python build_jira_vectorstore_all.py
```

### **4. Start Server (1 command)**
```bash
uvicorn server:app --reload
```

**That's it!** Automation is now running.

---

## ✅ **What Was Implemented**

### **Backend Changes:**
- ✅ **APScheduler** added to `server.py` (runs daily at 2 AM)
- ✅ **Error Tracking** added to sync tracker
- ✅ **Alert System** for consecutive failures
- ✅ **Status Tracking** (success/failed/no_updates)
- ✅ **API Endpoints** updated with alert info

### **Frontend Changes:**
- ✅ **Alert Display** at top of Sync panel (red/yellow boxes)
- ✅ **Enhanced History** shows failures with error messages
- ✅ **Status Indicators** (green=success, red=failed, blue=no updates)

### **Configuration:**
- ✅ `JIRA_PROJECT_KEYS=PRI,QAB` (both boards)
- ✅ `JIRA_MAX_ISSUES=10000` (increased from 300)
- ✅ `JIRA_SYNC_HOUR=2` (runs at 2 AM daily)

---

## 🤖 **How It Works**

```
Every Day at 2:00 AM:
  ↓
Scheduler wakes up
  ↓
Fetches tickets updated since last sync
  ↓
Adds new/updated tickets
  ↓
Records result (success/failure)
  ↓
If 2+ failures → Shows alert in Admin UI
```

---

## 📊 **Monitoring**

### **Check Status:**
```bash
# Via CLI
python scripts/sync_jira_status.py

# Via Admin UI
http://localhost:3000/admin/jira → Sync & Status tab
```

### **View Alerts:**
Admin UI shows alerts at the top:
```
┌─────────────────────────────────────────┐
│ ❌ Jira sync has failed 2 times in row │
│ Connection timeout                      │
└─────────────────────────────────────────┘
```

---

## 🎛️ **What's in .env**

| Variable | Value | What It Does |
|----------|-------|--------------|
| `JIRA_PROJECT_KEYS` | `PRI,QAB` | Fetches from both boards |
| `JIRA_MAX_ISSUES` | `10000` | Max tickets to fetch |
| `JIRA_SYNC_HOUR` | `2` | Runs at 2 AM daily |
| `ENABLE_JIRA_VECTORSTORE` | `true` | Enables Jira vectorstore |
| `INITIALIZE_JIRA_VECTORSTORE` | `false` | Don't rebuild on startup |

---

## 📦 **What to Install**

```bash
# Only this:
pip install apscheduler

# Or update all dependencies:
pip install -r requirements.txt
```

---

## 🔄 **Daily Workflow**

**You don't have to do anything!**

The system:
1. Syncs automatically at 2 AM
2. Shows alerts if anything fails
3. Records everything in Admin UI

You only need to:
- Check Admin UI occasionally for alerts
- Fix any issues if alerts appear
- Enjoy automated syncing!

---

## 📁 **Code Files Modified**

```
Backend:
  ✅ server.py                    (added scheduler)
  ✅ app/jira_sync_tracker.py     (added alerts)
  ✅ app/jira_vectorstore.py      (status tracking)
  ✅ app/routes/jira_sync.py      (alert endpoints)
  ✅ requirements.txt             (apscheduler)

Frontend:
  ✅ JiraSyncPanel.tsx            (alert display)

Config:
  ✅ .env                         (updated settings)
```

---

## 🎯 **Next Steps**

1. Install `apscheduler`
2. Update `.env` (copy from above)
3. Run `python build_jira_vectorstore_all.py`
4. Start server
5. Visit `http://localhost:3000/admin/jira` to see it working!

**Full detailed guide:** See `JIRA_AUTOMATION_SETUP_GUIDE.md`
