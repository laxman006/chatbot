# User Activity Verification Guide

## Overview

The dashboard now uses a **single source of truth** architecture with the `user_activity` collection. This ensures accurate statistics without aggregating from chat logs.

## Architecture

### Before (Incorrect - Aggregating from chat logs)
```
Dashboard → Aggregates from chat_sessions → Calculates stats on-the-fly → Wrong results
```

### After (Correct - Single Source of Truth)
```
Dashboard → Reads from user_activity → Pre-calculated metrics → Accurate results
```

## MongoDB Collections

### 1. `user_activity` Collection (Single Source of Truth)

**Document Structure:**
```json
{
  "_id": ObjectId("..."),
  "user_id": "aad-12345",
  "user_email": "user@cloudfuze.com",
  "user_name": "User Name",
  "sessions": [
    {
      "session_id": "sess-uuid-1",
      "started_at": ISODate("2025-12-13T08:00:00Z"),
      "ended_at": ISODate("2025-12-13T08:20:00Z"),
      "message_count": 12
    }
  ],
  "total_messages": 128,
  "total_sessions": 9,
  "avg_messages_per_session": 14.2,
  "last_active": ISODate("2025-12-13T10:12:32Z"),
  "created_at": ISODate("2025-11-01T09:00:00Z")
}
```

**Indexes:**
- `user_id` (unique)
- `last_active`
- `total_messages`
- `total_sessions`

### 2. `chat_sessions` Collection (Still Used for Chat History)

This collection still stores full session data with messages for chat functionality.

## How Data is Written

### 1. When Session is Saved (`save_session`)

Automatically updates `user_activity`:
- Creates/updates user document
- Adds session to sessions array
- Recalculates totals (total_messages, total_sessions, avg_messages_per_session)
- Updates last_active timestamp

### 2. When Message is Sent

The `_increment_user_message_count` method can be called to increment counters (currently handled via session save).

## How to Verify Data is Correct

### Method 1: Use Debug Endpoint

```bash
GET /admin/user-stats/debug
Authorization: Bearer YOUR_TOKEN
```

**Response shows:**
- `chat_sessions` collection stats
- `user_activity` collection stats
- Sample documents from both
- Recommendation to run migration if user_activity is empty

### Method 2: Direct MongoDB Query

```javascript
// Connect to MongoDB
mongosh "mongodb://localhost:27017"

// Switch to database
use slack2teams

// Check user_activity collection
db.user_activity.find().pretty()

// Count users
db.user_activity.countDocuments({})

// Get top users
db.user_activity.find().sort({total_messages: -1}).limit(5).pretty()

// Compare with chat_sessions
db.chat_sessions.aggregate([
  {$group: {_id: "$user_id", count: {$sum: 1}}},
  {$sort: {count: -1}},
  {$limit: 5}
])
```

### Method 3: Check Dashboard API Response

```bash
GET /admin/user-stats?start_date=2025-12-01&end_date=2025-12-13
Authorization: Bearer YOUR_TOKEN
```

**Response includes:**
- `data_source: "user_activity"` - confirms using single source of truth
- `users` array with pre-calculated metrics
- `filters_applied` showing active filters

## Migration (One-Time Setup)

If you have existing data in `chat_sessions`, run the migration endpoint once:

```bash
POST /admin/user-stats/migrate
Authorization: Bearer YOUR_TOKEN
```

**What it does:**
- Reads all sessions from `chat_sessions`
- Groups by `user_id`
- Counts user messages per session
- Creates `user_activity` documents with pre-calculated metrics
- Returns migration summary

**After migration:**
- All future sessions automatically update `user_activity`
- Dashboard reads from `user_activity` (accurate stats)
- No more aggregation from chat logs

## Verification Checklist

- [ ] Run `/admin/user-stats/debug` to see both collections
- [ ] Check `user_activity` collection has documents
- [ ] Verify `total_messages` matches expected count
- [ ] Verify `total_sessions` matches expected count
- [ ] Check `avg_messages_per_session` is calculated correctly
- [ ] Test date filters work correctly
- [ ] Test developer exclusion filter works
- [ ] Verify dashboard shows correct data

## Common Issues & Solutions

### Issue: `user_activity` collection is empty

**Solution:** Run migration endpoint:
```bash
POST /admin/user-stats/migrate
```

### Issue: Statistics don't match expected values

**Check:**
1. Verify migration completed successfully
2. Check `user_activity` documents have correct `total_messages`
3. Verify sessions are being saved (check `chat_sessions` collection)
4. Check logs for `_update_user_activity` errors

### Issue: New sessions not appearing in stats

**Check:**
1. Verify `save_session` is being called
2. Check logs for `Updated user_activity for user` messages
3. Verify `user_activity` collection is being updated

## Data Flow

```
User sends message
    ↓
Frontend saves session with messages
    ↓
POST /chat/sessions/save
    ↓
save_session() in mongodb_memory.py
    ↓
Updates chat_sessions collection
    ↓
Calls _update_user_activity()
    ↓
Updates user_activity collection (single source of truth)
    ↓
Dashboard reads from user_activity
    ↓
Accurate statistics displayed
```

## Key Benefits

✅ **Accurate Statistics** - No aggregation errors
✅ **Fast Queries** - Pre-calculated metrics
✅ **No Duplicates** - Unique user_id index
✅ **Consistent Data** - Single source of truth
✅ **Easy Filtering** - Simple queries on user_activity
✅ **Scalable** - Efficient for large datasets

## Testing

### Test 1: Verify Migration
```bash
# Before migration
GET /admin/user-stats/debug
# Check user_activity.total_documents = 0

# Run migration
POST /admin/user-stats/migrate

# After migration
GET /admin/user-stats/debug
# Check user_activity.total_documents > 0
```

### Test 2: Verify New Sessions Update Activity
```bash
# Create a new chat session
POST /chat/sessions/save
# Send messages

# Check user_activity updated
GET /admin/user-stats/debug
# Verify user's total_messages increased
```

### Test 3: Verify Dashboard Filters
```bash
# Test date filter
GET /admin/user-stats?start_date=2025-12-13&end_date=2025-12-13

# Test exclusion filter
GET /admin/user-stats?exclude_users=dev1@cloudfuze.com,dev2@cloudfuze.com
```


