# Testing Guide - Analytics System Improvements

## 🧪 Complete Testing Guide

This guide walks you through testing the new analytics system end-to-end.

---

## 📋 Prerequisites

1. **Backend running** on `http://localhost:8000` (or your configured port)
2. **Frontend running** on `http://localhost:3000` (or your configured port)
3. **MongoDB connected** and accessible
4. **Admin access** - You need to be logged in as an admin user

---

## 🔍 Part 1: Backend API Testing

### Test 1: All-Time User Statistics

**Endpoint**: `GET /admin/users/summary`

**Test Command** (using curl):
```bash
curl -X GET "http://localhost:8000/admin/users/summary?exclude_users=dev1@cloudfuze.com,dev2@cloudfuze.com" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "total_users": 42,
  "users": [
    {
      "user_id": "aad-123",
      "user_email": "user@cloudfuze.com",
      "user_name": "John Doe",
      "total_messages": 128,
      "total_sessions": 9,
      "avg_messages_per_session": 14.22,
      "last_active": "2025-12-13T11:05:00Z"
    }
  ],
  "data_source": "user_activity",
  "time_range": "all_time"
}
```

**✅ What to Verify**:
- [ ] Returns all-time statistics (no date filtering)
- [ ] Includes `total_sessions` and `avg_messages_per_session`
- [ ] Users sorted by `total_messages` (descending)
- [ ] Excluded users are filtered out

---

### Test 2: Date-Based Rankers (Today)

**Endpoint**: `GET /admin/rankers`

**Test Command**:
```bash
# Get today's date in ISO format
TODAY=$(date +%Y-%m-%d)

curl -X GET "http://localhost:8000/admin/rankers?from_date=${TODAY}&to_date=${TODAY}&exclude_users=dev1@cloudfuze.com" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "rankers": [
    {
      "user_id": "aad-123",
      "user_email": "user@cloudfuze.com",
      "user_name": "John Doe",
      "total_messages": 5,
      "last_active": "2025-12-13T15:30:00Z"
    }
  ],
  "total_rankers": 10,
  "data_source": "message_events",
  "time_range": "2025-12-13 to 2025-12-13"
}
```

**✅ What to Verify**:
- [ ] Returns only users active within the date range
- [ ] `total_messages` reflects activity for that period only
- [ ] NO `total_sessions` or `avg_messages_per_session` fields
- [ ] Counts match actual messages sent today

---

### Test 3: Date-Based Rankers (Last 7 Days)

**Test Command**:
```bash
# Calculate dates
END_DATE=$(date +%Y-%m-%d)
START_DATE=$(date -d "7 days ago" +%Y-%m-%d)

curl -X GET "http://localhost:8000/admin/rankers?from_date=${START_DATE}&to_date=${END_DATE}" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**✅ What to Verify**:
- [ ] Returns rankers for the last 7 days
- [ ] Message counts are accurate for that period
- [ ] Users who didn't send messages in that period are excluded

---

### Test 4: FAQs by Date Range

**Endpoint**: `GET /admin/faqs`

**Test Command**:
```bash
TODAY=$(date +%Y-%m-%d)

curl -X GET "http://localhost:8000/admin/faqs?from_date=${TODAY}&to_date=${TODAY}&limit=20" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Expected Response**:
```json
{
  "faqs": [
    {
      "question": "Does CloudFuze preserve metadata?",
      "count": 12,
      "last_asked": "2025-12-13T14:20:00Z"
    }
  ],
  "total_faqs": 5,
  "data_source": "faq_events"
}
```

**✅ What to Verify**:
- [ ] Returns questions asked within date range
- [ ] Questions are deduplicated (same question counted multiple times)
- [ ] Sorted by frequency (most asked first)

---

### Test 5: Legacy Endpoint (Backward Compatibility)

**Endpoint**: `GET /admin/user-stats`

**Test Command** (No dates - should delegate to summary):
```bash
curl -X GET "http://localhost:8000/admin/user-stats" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**Test Command** (With dates - should delegate to rankers):
```bash
TODAY=$(date +%Y-%m-%d)

curl -X GET "http://localhost:8000/admin/user-stats?start_date=${TODAY}&end_date=${TODAY}" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

**✅ What to Verify**:
- [ ] Without dates: Returns all-time stats (same as `/admin/users/summary`)
- [ ] With dates: Returns date-based rankers (same as `/admin/rankers`)
- [ ] Backward compatible with existing code

---

## 🖥️ Part 2: Frontend Dashboard Testing

### Test 6: All-Time View

**Steps**:
1. Navigate to `http://localhost:3000/admin/dashboard`
2. Verify you're logged in as admin
3. Check date filter shows **"All Time"** (default)
4. Verify dashboard loads

**✅ What to Verify**:
- [ ] Dashboard shows all-time statistics
- [ ] **Sessions bar chart is visible**
- [ ] Table shows columns: Rank, Name, Email, Messages, **Sessions**, **Avg/Session**, Last Active
- [ ] Top 5 Rankers show session counts
- [ ] Stats match backend `/admin/users/summary` response

---

### Test 7: Today Filter

**Steps**:
1. Click date filter dropdown
2. Select **"Today"**
3. Wait for dashboard to refresh

**✅ What to Verify**:
- [ ] Dashboard shows rankers for today only
- [ ] **Sessions bar chart is HIDDEN** (not available for date-based)
- [ ] Table shows columns: Rank, Name, Email, Messages, Last Active (no Sessions/Avg)
- [ ] Top 5 Rankers show only message counts (no sessions)
- [ ] Date range indicator shows today's date
- [ ] Stats match backend `/admin/rankers?from_date=...&to_date=...` response

---

### Test 8: Yesterday Filter

**Steps**:
1. Click date filter dropdown
2. Select **"Yesterday"**
3. Verify dashboard updates

**✅ What to Verify**:
- [ ] Shows rankers for yesterday only
- [ ] Message counts reflect yesterday's activity
- [ ] Users who didn't send messages yesterday are excluded

---

### Test 9: Last N Days Filter

**Steps**:
1. Click date filter dropdown
2. Select **"Last N days"**
3. Change number (e.g., 7 days)
4. Verify dashboard updates

**✅ What to Verify**:
- [ ] Shows rankers for the selected period
- [ ] Message counts are accurate for that period
- [ ] Date range indicator shows correct range

---

### Test 10: Custom Date Range

**Steps**:
1. Click date filter dropdown
2. Select **"Custom"**
3. Choose start date and end date
4. Optionally set times
5. Verify dashboard updates

**✅ What to Verify**:
- [ ] Shows rankers for custom date range
- [ ] Respects time boundaries if set
- [ ] Date range indicator shows custom range

---

### Test 11: Developer Exclusion Filter

**Steps**:
1. Click developer exclusion filter dropdown
2. Select/deselect developers to exclude
3. Verify dashboard updates

**✅ What to Verify**:
- [ ] Excluded developers don't appear in rankings
- [ ] Works for both all-time and date-based views
- [ ] Filter persists when switching date ranges

---

### Test 12: Charts and Visualizations

**Steps**:
1. View dashboard with data
2. Check all charts render correctly

**✅ What to Verify**:
- [ ] **Pie Chart**: Message distribution (Top 10) - Always visible
- [ ] **Messages Bar Chart**: Top users by messages - Always visible
- [ ] **Sessions Bar Chart**: Only visible in All-Time view
- [ ] Charts update when filters change
- [ ] Tooltips work correctly
- [ ] Colors are distinct and readable

---

## 🗄️ Part 3: MongoDB Data Verification

### Test 13: Verify Event Collections Exist

**MongoDB Shell Commands**:
```javascript
// Connect to MongoDB
use your_database_name

// Check message_events collection
db.message_events.countDocuments({})
db.message_events.find().limit(5).pretty()

// Check faq_events collection
db.faq_events.countDocuments({})
db.faq_events.find().limit(5).pretty()

// Check indexes
db.message_events.getIndexes()
db.faq_events.getIndexes()
```

**✅ What to Verify**:
- [ ] `message_events` collection exists
- [ ] `faq_events` collection exists
- [ ] Indexes are created:
  - `message_events`: `created_at`, `(user_id, created_at)`, `session_id`
  - `faq_events`: `created_at`, `(user_id, created_at)`, `question_hash`

---

### Test 14: Verify Event Tracking

**Steps**:
1. Send a message via chat interface
2. Check MongoDB for new event

**MongoDB Query**:
```javascript
// Check latest message event
db.message_events.find().sort({created_at: -1}).limit(1).pretty()

// Check latest FAQ event (if informational query)
db.faq_events.find().sort({created_at: -1}).limit(1).pretty()
```

**✅ What to Verify**:
- [ ] Every user message creates a `message_events` document
- [ ] Informational queries create `faq_events` documents
- [ ] Conversational queries (hi, hello) don't create FAQ events
- [ ] Events have correct `user_id`, `session_id`, `created_at`

---

### Test 15: Verify Data Accuracy

**MongoDB Aggregation Test**:
```javascript
// Count messages for a user today
const today = new Date();
today.setHours(0, 0, 0, 0);
const tomorrow = new Date(today);
tomorrow.setDate(tomorrow.getDate() + 1);

db.message_events.aggregate([
  {
    $match: {
      user_id: "YOUR_USER_ID",
      created_at: { $gte: today, $lt: tomorrow }
    }
  },
  {
    $group: {
      _id: "$user_id",
      message_count: { $sum: 1 }
    }
  }
])
```

**✅ What to Verify**:
- [ ] Aggregation matches API response
- [ ] Date filtering works correctly
- [ ] Counts are accurate

---

## 🧪 Part 4: Integration Testing

### Test 16: End-to-End Flow

**Steps**:
1. **Send messages** via chat (5-10 messages)
2. **Check MongoDB** - Verify events are created
3. **Open dashboard** - Check "Today" filter
4. **Verify** - Your user appears in today's rankers
5. **Switch to "All Time"** - Verify lifetime stats include today's messages

**✅ What to Verify**:
- [ ] Events are tracked correctly
- [ ] Dashboard shows accurate data
- [ ] Date filtering works end-to-end
- [ ] All-time stats include new activity

---

### Test 17: Performance Testing

**Steps**:
1. Load dashboard with "All Time" filter
2. Measure load time
3. Switch to "Today" filter
4. Measure load time
5. Compare with previous implementation

**✅ What to Verify**:
- [ ] Dashboard loads quickly (< 2 seconds)
- [ ] Date-based queries are fast (indexed)
- [ ] No performance degradation
- [ ] Smooth UI transitions

---

## 🐛 Troubleshooting

### Issue: No data showing in dashboard

**Check**:
1. Are events being created? (Test 14)
2. Are indexes created? (Test 13)
3. Check browser console for errors
4. Check backend logs for errors

**Solution**:
```bash
# Check backend logs
tail -f logs/backend.log

# Check MongoDB connection
# Verify MONGODB_URL in .env
```

---

### Issue: Date filter not working

**Check**:
1. Are dates in correct format? (ISO format: `YYYY-MM-DD`)
2. Check browser network tab - verify API calls
3. Check API response - verify data_source

**Solution**:
```javascript
// Verify date format in browser console
console.log(dateRange.startDate) // Should be ISO string
```

---

### Issue: Sessions data missing in date-based view

**Expected Behavior**: 
- Sessions data is **only available** in All-Time view
- Date-based rankers show **only messages**

**This is correct** - sessions are lifetime aggregates, not date-scoped.

---

### Issue: Events not being created

**Check**:
1. Is chat endpoint being called?
2. Check backend logs for errors
3. Verify `insert_message_event()` is being called

**Solution**:
```python
# Check backend logs for:
# "Inserted message event for user..."
# "Inserted FAQ event for user..."
```

---

## 📊 Test Checklist Summary

### Backend APIs
- [ ] `/admin/users/summary` - All-time stats
- [ ] `/admin/rankers` - Date-based rankers
- [ ] `/admin/faqs` - FAQ analytics
- [ ] `/admin/user-stats` - Legacy endpoint (backward compatible)

### Frontend Dashboard
- [ ] All-Time view (default)
- [ ] Today filter
- [ ] Yesterday filter
- [ ] Last N days filter
- [ ] Custom date range
- [ ] Developer exclusion filter
- [ ] Charts render correctly
- [ ] Table columns adjust dynamically

### MongoDB
- [ ] Collections exist (`message_events`, `faq_events`)
- [ ] Indexes created
- [ ] Events being tracked
- [ ] Data accuracy verified

### Integration
- [ ] End-to-end flow works
- [ ] Performance acceptable
- [ ] No errors in console/logs

---

## 🎯 Quick Test Script

**Run this to quickly verify everything works**:

```bash
#!/bin/bash

# 1. Test All-Time API
echo "Testing All-Time API..."
curl -X GET "http://localhost:8000/admin/users/summary" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.total_users'

# 2. Test Today's Rankers
TODAY=$(date +%Y-%m-%d)
echo "Testing Today's Rankers..."
curl -X GET "http://localhost:8000/admin/rankers?from_date=${TODAY}&to_date=${TODAY}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.total_rankers'

# 3. Test FAQs
echo "Testing FAQs..."
curl -X GET "http://localhost:8000/admin/faqs?from_date=${TODAY}&to_date=${TODAY}" \
  -H "Authorization: Bearer $ACCESS_TOKEN" | jq '.total_faqs'

echo "✅ All API tests completed!"
```

---

## 📝 Notes

- **First Run**: Event collections will be empty initially - they populate as users send messages
- **Test Data**: You may need to send some test messages to generate events
- **Admin Access**: Make sure you're logged in as an admin user
- **CORS**: If testing from browser console, ensure CORS is configured

---

**Happy Testing! 🚀**


