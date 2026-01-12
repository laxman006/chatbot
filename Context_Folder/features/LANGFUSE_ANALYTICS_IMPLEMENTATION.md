# Langfuse Analytics Dashboard Implementation

## Overview

The Langfuse Analytics Dashboard has been successfully implemented in the admin console. This feature provides comprehensive insights into user engagement and question analytics by aggregating data from Langfuse traces.

## Features

### 1. Dashboard Summary
- **Total Users**: Count of unique users who have asked questions
- **Total Questions**: Total number of questions asked across all users
- **Unique Questions**: Count of distinct/unique questions
- **Average Questions per User**: Mean questions asked per user

### 2. Most Active Users
- Top 10 users by number of questions asked
- Displays: Email, Name, and Questions Count
- Helps identify power users and engagement patterns

### 3. Top Questions
- Most frequently asked questions across the entire platform
- Shows frequency count and percentage of total questions
- Helps identify common pain points and user interests

### 4. All Users View
- Complete list of all users with their analytics
- Shows: Email, Name, Total Questions, First Question Date, Last Activity Date
- Allows admins to track user engagement timeline

### 5. Per-User Deep Dive
- Detailed view of individual user activity (available via API)
- Shows all questions asked by a specific user
- Top 10 questions for that user
- Recent and complete question history

## File Structure

```
app/
├── endpoints.py (NEW ENDPOINTS ADDED)
    ├── /analytics/langfuse/dashboard-summary
    ├── /analytics/langfuse/users
    ├── /analytics/langfuse/users/{user_id}
    └── /analytics/langfuse/top-questions

frontend/src/
├── app/admin/
│   └── analytics/
│       └── page.tsx (NEW PAGE)
└── components/
    └── ChatSidebar.tsx (UPDATED with new nav link)
```

## Backend Endpoints

### 1. Dashboard Summary
**Endpoint**: `GET /analytics/langfuse/dashboard-summary`

**Authentication**: Requires admin access

**Response**:
```json
{
  "status": "success",
  "summary": {
    "total_users": 150,
    "total_questions": 2500,
    "unique_questions": 850,
    "average_questions_per_user": 16.67
  },
  "most_active_users": [
    {
      "user_id": "user123",
      "email": "user@cloudfuze.com",
      "name": "John Doe",
      "questions_asked": 150
    }
  ],
  "top_questions": [
    {
      "question": "How to migrate data?",
      "times_asked": 45
    }
  ]
}
```

### 2. All Users Analytics
**Endpoint**: `GET /analytics/langfuse/users`

**Authentication**: Requires admin access

**Response**:
```json
{
  "status": "success",
  "total_users": 150,
  "total_questions": 2500,
  "users": [
    {
      "user_id": "user123",
      "email": "user@cloudfuze.com",
      "name": "John Doe",
      "total_questions": 150,
      "first_question_at": "2024-01-15T10:30:00Z",
      "last_question_at": "2024-01-20T15:45:00Z",
      "top_questions": [
        {
          "question": "How to migrate?",
          "count": 10
        }
      ]
    }
  ],
  "users_by_department": {
    "Engineering": [
      { ... }
    ],
    "Sales": [
      { ... }
    ]
  },
  "department_summary": {
    "Engineering": {
      "user_count": 25,
      "total_questions": 500
    }
  }
}
```

### 3. Specific User Analytics
**Endpoint**: `GET /analytics/langfuse/users/{user_id}`

**Authentication**: Requires admin access

**Response**:
```json
{
  "status": "success",
  "user_id": "user123",
  "email": "user@cloudfuze.com",
  "name": "John Doe",
  "total_questions": 150,
  "total_traces": 150,
  "top_questions": [
    {
      "question": "How to migrate?",
      "frequency": 10
    }
  ],
  "recent_questions": [
    {
      "question": "Latest question?",
      "answer": "Latest answer...",
      "asked_at": "2024-01-20T15:45:00Z",
      "intent": "general",
      "confidence": 0.95
    }
  ]
}
```

### 4. Top Questions Global
**Endpoint**: `GET /analytics/langfuse/top-questions?limit=20`

**Authentication**: Requires admin access

**Parameters**:
- `limit` (optional): Number of top questions to return (default: 20, max: 100)

**Response**:
```json
{
  "status": "success",
  "total_unique_questions": 850,
  "total_questions_asked": 2500,
  "top_questions": [
    {
      "question": "How to migrate data?",
      "times_asked": 45,
      "percentage": 1.8
    }
  ]
}
```

## Frontend Components

### Admin Analytics Page
**Location**: `/admin/analytics`

**Access**: Admin users only (restricted to emails in `ADMIN_EMAILS`)

**Features**:
1. **Overview Tab**
   - Summary cards showing key metrics
   - Top 10 most active users table
   - Top 5 questions list

2. **All Users Tab**
   - Complete table of all users
   - Columns: Email, Name, Total Questions, First Question Date, Last Active Date
   - Sortable data

3. **Top Questions Tab**
   - Ranked list of most asked questions
   - Shows frequency and percentage
   - Easy-to-read cards format

## Data Flow

```
User asks question in Chat
        ↓
Question logged to Langfuse trace with metadata:
  - user_id
  - user_email
  - user_name
  - department
  - timestamp
  - metadata
        ↓
Admin accesses /admin/analytics
        ↓
Frontend calls /analytics/langfuse/dashboard-summary
        ↓
Backend:
  1. Connects to Langfuse API
  2. Fetches all traces (paginated)
  3. Aggregates data by user_id
  4. Counts questions per user
  5. Identifies top questions
  6. Calculates statistics
        ↓
Response returned to Frontend
        ↓
Dashboard displays aggregated analytics
```

## How Metadata is Captured

When a question is asked, Langfuse logs include:

```python
metadata={
    "user_id": "user123",
    "session_id": "session456",
    "user_name": "John Doe",
    "user_email": "john@cloudfuze.com",
    "request": {
        "endpoint": "/chat/stream",
        "timestamp": "2024-01-20T15:45:00Z"
    },
    "intent": {
        "detected": "general",
        "confidence": 0.95
    }
}
```

This metadata is captured in `/app/endpoints.py` at lines 1892-1943 for the streaming endpoint.

## Admin Access Control

The analytics dashboard is restricted to admin users defined in:

**File**: `frontend/src/constants/admins.ts`

```typescript
export const ADMIN_EMAILS = [
  'laxman.kadari@cloudfuze.com',
  'chaitanya.malle@cloudfuze.com',
  'nirosh.reddy@cloudfuze.com'
];
```

To add new admins, update this file with additional email addresses.

## Performance Considerations

### Data Pagination
- The Langfuse API endpoints use pagination (100 traces per page)
- Large datasets are fetched in batches to avoid timeouts
- All pages are fetched until no more data is available

### Aggregation
- Counter objects efficiently aggregate question frequencies
- O(n) time complexity for most operations
- Data is cached in memory during the request

### Refresh Options
- Manual refresh button available in the UI
- Real-time data fetching on each request
- No caching on the frontend to ensure fresh data

## Troubleshooting

### "Langfuse client not initialized"
**Cause**: LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY not set

**Solution**: 
1. Check `.env` file
2. Ensure Langfuse credentials are correctly set:
   ```
   LANGFUSE_PUBLIC_KEY=pk_...
   LANGFUSE_SECRET_KEY=sk_...
   LANGFUSE_HOST=https://cloud.langfuse.com
   ```

### No users showing up
**Cause**: No traces have been logged to Langfuse yet

**Solution**:
1. Ask questions in the chatbot first
2. Wait for traces to be processed
3. Refresh the dashboard

### Slow loading
**Cause**: Large volume of traces in Langfuse

**Solution**:
1. Be patient during initial load
2. Consider reducing date range in future updates
3. Backend applies pagination automatically

## Future Enhancements

1. **Date Range Filtering**: Filter analytics by date range
2. **Department Grouping**: Better visualization of department-wise analytics
3. **Export Data**: Export analytics as CSV/Excel
4. **Charts & Graphs**: Visual representations of trends
5. **Search Users**: Search for specific users
6. **Drill-down**: Click user to see their detailed history
7. **Sentiment Analysis**: Analyze user satisfaction trends
8. **Response Quality Metrics**: Track answer quality scores

## Testing

To test the analytics dashboard:

1. **Navigate to Admin Console**:
   - Click "Admin" in sidebar
   - Select "Langfuse Analytics"

2. **Verify Data Loads**:
   - Check if Summary cards show data
   - Verify Overview tab shows users and questions
   - Check Users tab for complete list
   - Check Questions tab for top questions

3. **Test Refresh**:
   - Click "Refresh" button
   - Verify data updates

4. **Test Tabs**:
   - Switch between Overview, Users, and Questions tabs
   - Verify correct data in each tab

## API Integration Example

```javascript
// Frontend code to fetch analytics
const user = JSON.parse(localStorage.getItem('user'));

const response = await fetch('/api/analytics/langfuse/dashboard-summary', {
  headers: {
    'Authorization': `Bearer ${user.access_token}`
  }
});

const data = await response.json();
console.log(data.summary); // { total_users, total_questions, ... }
```

## Conclusion

The Langfuse Analytics Dashboard provides comprehensive insights into chatbot usage patterns, user engagement, and frequently asked questions. It enables admins to:

- Monitor user engagement trends
- Identify knowledge gaps (frequently asked questions)
- Track power users
- Make data-driven improvements to the knowledge base
- Understand user behavior and preferences

---

**Implementation Date**: January 2024
**Status**: Complete and Deployed
**Next Review**: Monthly

