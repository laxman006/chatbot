# 🚀 Jira Automation Setup Guide

## Overview
This guide will help you set up automated daily Jira ticket synchronization with alerts for failures.

---

## 📦 **STEP 1: Install Required Packages**

Run these commands in your terminal:

```bash
# Install APScheduler for automated syncing
pip install apscheduler>=3.10.0

# Install cryptography for token encryption (if not already installed)
pip install cryptography>=42.0.0

# Or install all at once from requirements.txt
pip install -r requirements.txt
```

---

## ⚙️ **STEP 2: Update Your .env File**

Replace your current Jira configuration in `.env` with this:

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

# Jira Sync Scheduler Configuration (runs daily at this hour)
JIRA_SYNC_HOUR=2

# Disable Jira from main vectorstore (since it's in separate vectorstore now)
ENABLE_JIRA_SOURCE=false
```

### **Key Changes:**
- ✅ `JIRA_PROJECT_KEYS=PRI,QAB` (was just `PRI`)
- ✅ `JIRA_MAX_ISSUES=10000` (was `300`)
- ✅ `JIRA_SYNC_HOUR=2` (NEW - runs at 2 AM daily)

---

## 🔨 **STEP 3: Initial Manual Build**

Before automation starts, you need to do an initial manual build:

```bash
# This fetches all 9,453 tickets from PRI and QAB boards
python build_jira_vectorstore_all.py
```

**Expected Output:**
```
============================================================
BUILDING SEPARATE JIRA VECTORSTORE
============================================================
[*] Removing existing Jira vectorstore...
[OK] Existing vectorstore removed
[*] Fetching 10000 recent closed/resolved tickets...

Testing PRI Board:
[OK] Total PRI tickets (Resolved/Closed): 9000

Testing QAB Board:
[OK] Total QAB tickets (Resolved/Closed): 453

[OK] Processed 9453 Jira ticket chunks
[OK] Processed into 47265 chunks after enhancement

===== JIRA VECTORSTORE BUILD REPORT =====
Total documents: 47265
Unique tickets: 9453
Projects: PRI (9000), QAB (453)
==========================================

✅ JIRA VECTORSTORE BUILT SUCCESSFULLY!
```

**What This Does:**
- Fetches all 9,453 resolved/closed tickets
- Creates 47,265 document chunks (5 per ticket)
- Stores in `./data/jira_chroma_db/`
- Records initial sync timestamp

---

## ✅ **STEP 4: Verify Initial Build**

```bash
python scripts/sync_jira_status.py
```

**Expected Output:**
```
Jira Sync Status:
  Last Sync: 2025-01-21 15:00:00
  Total Documents: 47265
  Total Tickets: 9453
  
Ticket Breakdown:
  PRI: 9000 tickets
  QAB: 453 tickets
```

---

## 🤖 **STEP 5: Start Server with Automation**

```bash
# Start the FastAPI server
uvicorn server:app --reload --port 8000
```

**You Should See:**
```
[STARTUP] Initializing MongoDB memory storage...
[STARTUP] ✅ MongoDB memory storage initialized successfully
[STARTUP] ✅ Jira sync scheduler started (runs daily at 2:00 AM)
```

**🎉 Automation is now active!**

---

## 📊 **How Automation Works**

### **Daily Scheduled Sync:**
```
┌─────────────────────────────────────────┐
│  Every Day at 2:00 AM                   │
│  (Configurable via JIRA_SYNC_HOUR)      │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  Scheduler triggers:                    │
│  scheduled_jira_sync()                  │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│  1. Fetches tickets updated since       │
│     last successful sync                │
│  2. Checks for duplicates               │
│  3. Adds new/updated tickets            │
│  4. Records result (success/failure)    │
└─────────────────────────────────────────┘
```

### **What Gets Logged:**
```
[SCHEDULER] 🔄 Starting scheduled Jira sync...
[*] Last sync: 2025-01-21 02:00:00
[*] Fetching tickets updated since 2025-01-21...
[OK] Found 15 new/updated tickets
[OK] Added 75 chunks to existing vectorstore
[SCHEDULER] ✅ Sync completed successfully. Total documents: 47340
```

---

## 🚨 **Alert System**

### **When Alerts Trigger:**
- ❌ **2 consecutive failed syncs** → Error alert
- ⚠️ **No successful sync in 48+ hours** → Warning alert

### **Where to See Alerts:**

#### **Option 1: Admin UI (Recommended)**
1. Navigate to: `http://localhost:3000/admin/jira`
2. Click **"Sync & Status"** tab
3. Alerts appear at the top in red/yellow boxes

**Example Alert:**
```
┌─────────────────────────────────────────────────────┐
│ ❌ Jira sync has failed 2 times in a row           │
│ Connection timeout to Jira server                  │
│ Last attempt: 2025-01-21 02:00:00                  │
└─────────────────────────────────────────────────────┘
```

#### **Option 2: API Endpoint**
```bash
curl http://localhost:8000/api/jira/sync/status \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

**Response with Alert:**
```json
{
  "status": "active",
  "last_sync": "2025-01-20 02:00:00",
  "last_attempt": "2025-01-21 02:00:00",
  "last_status": "failed",
  "consecutive_failures": 2,
  "has_alerts": true,
  "alerts": [
    {
      "type": "error",
      "message": "Jira sync has failed 2 times in a row",
      "details": "Connection timeout to Jira server",
      "last_attempt": "2025-01-21 02:00:00"
    }
  ]
}
```

#### **Option 3: Check Log File**
```bash
# Check data file directly
cat data/jira_last_sync.json
```

---

## 🎛️ **Configuration Options**

### **Change Sync Time:**
```bash
# In .env
JIRA_SYNC_HOUR=2   # Default: 2 AM
JIRA_SYNC_HOUR=14  # Change to 2 PM
JIRA_SYNC_HOUR=0   # Change to midnight
```

### **Manual Sync Anytime:**

#### **Via Admin UI:**
1. Go to `http://localhost:3000/admin/jira`
2. Click "Sync & Status" tab
3. Click **"Trigger Manual Sync"** button

#### **Via CLI:**
```bash
python scripts/sync_jira_incremental.py
```

#### **Via API:**
```bash
curl -X POST "http://localhost:8000/api/jira/sync" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

---

## 📂 **Files Created/Modified**

### **Modified Files:**
```
✅ server.py                          # Added APScheduler
✅ app/jira_sync_tracker.py           # Added error tracking & alerts
✅ app/jira_vectorstore.py            # Updated to record sync status
✅ app/routes/jira_sync.py            # Added alerts to API
✅ frontend/.../JiraSyncPanel.tsx     # Added alert display
✅ requirements.txt                   # Added apscheduler
✅ .env                                # Updated configuration
```

### **Data Files:**
```
./data/
├── jira_chroma_db/              # Vectorstore (47,265 docs)
├── jira_last_sync.json          # Sync tracker with alerts
├── jira_config.json             # Encrypted Jira config
└── .jira_encryption_key         # Encryption key
```

---

## 🧪 **Testing the Setup**

### **Test 1: Verify Scheduler Started**
```bash
# Start server and check logs
uvicorn server:app --reload

# Should see:
# [STARTUP] ✅ Jira sync scheduler started (runs daily at 2:00 AM)
```

### **Test 2: Verify Initial Build**
```bash
python scripts/sync_jira_status.py
```

### **Test 3: Test Manual Sync**
```bash
python scripts/sync_jira_incremental.py
```

### **Test 4: Check Admin UI**
- Navigate to: `http://localhost:3000/admin/jira`
- Should see sync status and history
- No alerts if everything is working

### **Test 5: Simulate Failure (Optional)**
```bash
# Temporarily break Jira connection
# In .env: JIRA_API_TOKEN=INVALID_TOKEN
# Run manual sync - should fail
python scripts/sync_jira_incremental.py

# Check alerts
python scripts/sync_jira_status.py
# Should show 1 failure

# Run again - should show 2 failures and trigger alert
python scripts/sync_jira_incremental.py

# Restore token and run again - should clear alerts
```

---

## 🔍 **Monitoring & Maintenance**

### **Daily Checks:**
1. Visit Admin UI: `http://localhost:3000/admin/jira`
2. Check for alerts (red/yellow boxes)
3. Verify sync history shows daily updates

### **Weekly Checks:**
```bash
# Check sync history
python scripts/sync_jira_status.py

# Expected: 7 successful syncs (one per day)
```

### **Monthly Checks:**
- Verify ticket counts are growing
- Check for any persistent errors
- Review sync timing (is 2 AM still good?)

---

## 🆘 **Troubleshooting**

### **Problem: Scheduler didn't start**
```bash
# Check logs for error
tail -f logs/server.log | grep SCHEDULER

# Solution: Make sure apscheduler is installed
pip install apscheduler
```

### **Problem: Alerts showing failures**
```bash
# Check error details
cat data/jira_last_sync.json | grep error

# Common issues:
# - API token expired
# - Network connectivity
# - Jira server maintenance
```

### **Problem: No new tickets syncing**
```bash
# This is normal if no tickets were updated!
# Check Jira to verify tickets were actually updated

# Force a manual check:
python scripts/sync_jira_incremental.py
```

### **Problem: Want to rebuild from scratch**
```bash
# Delete vectorstore
rm -rf data/jira_chroma_db

# Delete sync tracker
rm data/jira_last_sync.json

# Rebuild
python build_jira_vectorstore_all.py
```

---

## 🎉 **Success Checklist**

- [ ] Installed `apscheduler`
- [ ] Updated `.env` with correct configuration
- [ ] Ran initial manual build (`build_jira_vectorstore_all.py`)
- [ ] Verified 47,265 documents loaded
- [ ] Started server and saw scheduler start message
- [ ] Tested manual sync via CLI
- [ ] Tested manual sync via Admin UI
- [ ] Verified alerts work (optional)
- [ ] Confirmed daily sync time is correct

---

## 📞 **Need Help?**

- Check `JIRA_INTEGRATION_COMPLETE_SUMMARY.md` for detailed docs
- Review sync logs: `cat data/jira_last_sync.json`
- Check server logs for errors
- Visit Admin UI for real-time status

---

**🎯 Bottom Line:**
Once setup is complete, the system will automatically sync new Jira tickets every night at 2 AM, and alert you in the Admin UI if anything goes wrong!
