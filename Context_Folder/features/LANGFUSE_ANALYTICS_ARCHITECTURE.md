# Langfuse Analytics Dashboard - Architecture

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CHATBOT APPLICATION                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  FRONTEND                                                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │ ChatSidebar.tsx                                           │  │
│  │ ┌─────────────────────────────────────────────────────┐   │  │
│  │ │ Admin Section                                       │   │  │
│  │ ├─ Langfuse Analytics ← NEW                          │   │  │
│  │ ├─ Most Asked Questions                             │   │  │
│  │ └─ Other Admin Features                             │   │  │
│  │ └─────────────────────────────────────────────────────┘   │  │
│  └──────────────────┬──────────────────────────────────────────┘  │
│                     │ Routes to                                   │
│                     ↓                                              │
│  ┌───────────────────────────────────────────────────────────┐   │
│  │ admin/analytics/page.tsx - NEW                           │   │
│  │ ┌──────────────────────────────────────────────────────┐  │   │
│  │ │ 📊 Langfuse Analytics Dashboard                     │  │   │
│  │ │                                                      │  │   │
│  │ │ ┌─ Summary Cards                                  │  │   │
│  │ │ │  [Users] [Questions] [Unique] [Avg/User]       │  │   │
│  │ │ │                                                  │  │   │
│  │ │ ├─ Tab Navigation                                │  │   │
│  │ │ │  📋 Overview | 👥 Users | ❓ Questions         │  │   │
│  │ │ │                                                  │  │   │
│  │ │ ├─ Dynamic Content Area                          │  │   │
│  │ │ │  [Displays data based on selected tab]         │  │   │
│  │ │ │                                                  │  │   │
│  │ │ └─ Refresh Button                                │  │   │
│  │ │    [Calls backend to get latest data]            │  │   │
│  │ └──────────────────────────────────────────────────────┘  │   │
│  └──────────────────┬──────────────────────────────────────────┘   │
│                     │ Calls                                        │
│                     ↓                                               │
└─────────────────────────────────────────────────────────────────┘
                      │
                      │ HTTP Requests (with Bearer Token)
                      │
┌─────────────────────↓──────────────────────────────────────────┐
│                        BACKEND                                 │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  app/endpoints.py - NEW ENDPOINTS                             │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ GET /analytics/langfuse/dashboard-summary              │ │
│  │ ├─ Fetch traces from Langfuse API (paginated)          │ │
│  │ ├─ Aggregate by user_id                                │ │
│  │ ├─ Count questions                                     │ │
│  │ ├─ Find top questions                                  │ │
│  │ └─ Return summary stats                                │ │
│  │                                                          │ │
│  │ GET /analytics/langfuse/users                          │ │
│  │ ├─ Fetch all traces                                    │ │
│  │ ├─ Group by user                                       │ │
│  │ ├─ Calculate top 5 questions per user                  │ │
│  │ ├─ Group by department                                 │ │
│  │ └─ Return complete user analytics                      │ │
│  │                                                          │ │
│  │ GET /analytics/langfuse/users/{user_id}                │ │
│  │ ├─ Fetch traces for specific user                      │ │
│  │ ├─ Top 10 questions                                    │ │
│  │ ├─ Recent questions                                    │ │
│  │ └─ Return user details                                 │ │
│  │                                                          │ │
│  │ GET /analytics/langfuse/top-questions                  │ │
│  │ ├─ Fetch all traces                                    │ │
│  │ ├─ Extract questions                                   │ │
│  │ ├─ Count frequency                                     │ │
│  │ └─ Return top N questions                              │ │
│  └──────────────────────────────────────────────────────────┘ │
│                          ↑                                    │
│                          │ Uses                               │
│                          │                                    │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ app/langfuse_integration.py                            │ │
│  │ ├─ langfuse_client (Initialized)                       │ │
│  │ └─ Trace logging utilities                             │ │
│  └──────────────────────────────────────────────────────────┘ │
└────────────────┬─────────────────────────────────────────────┘
                 │
                 │ HTTP Requests (with API Auth)
                 │
         ┌───────↓────────┐
         │  LANGFUSE API  │
         ├────────────────┤
         │                │
         │ /api/public/   │
         │ traces         │
         │                │
         │ Returns:       │
         │ - Trace ID     │
         │ - Input        │
         │ - Output       │
         │ - userId       │
         │ - Metadata     │
         │ - Timestamp    │
         │                │
         └────────────────┘
```

## Data Flow Diagram

```
┌──────────────────────┐
│   User Asks Question │
│   in Chatbot Chat    │
└──────────┬───────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ /chat/stream Endpoint                       │
│ (app/endpoints.py - Line 1252)              │
├──────────────────────────────────────────────┤
│                                              │
│ Extract metadata:                            │
│ ├─ user_id                                   │
│ ├─ user_email                                │
│ ├─ user_name                                 │
│ ├─ question (input)                          │
│ ├─ answer (output)                           │
│ └─ timestamp                                 │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ langfuse_tracker.create_trace()              │
│ (app/langfuse_integration.py)                │
├──────────────────────────────────────────────┤
│                                              │
│ Build trace with:                            │
│ ├─ user_id                                   │
│ ├─ metadata (including all extracted data)  │
│ ├─ input (question)                          │
│ ├─ output (answer)                           │
│ └─ tags                                      │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Langfuse Cloud                               │
│ (https://cloud.langfuse.com)                │
├──────────────────────────────────────────────┤
│                                              │
│ Stores trace with complete metadata         │
│                                              │
│ Database Schema:                             │
│ {                                            │
│   id: trace_id,                              │
│   userId: user_id,                           │
│   input: question,                           │
│   output: answer,                            │
│   metadata: {                                │
│     user_id: "...",                          │
│     user_email: "...",                       │
│     user_name: "...",                        │
│     timestamp: "..."                         │
│   },                                         │
│   createdAt: timestamp                       │
│ }                                            │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
       [LATER]
           │
           ↓
┌──────────────────────────────────────────────┐
│ Admin Opens /admin/analytics                │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Frontend: admin/analytics/page.tsx           │
│                                              │
│ useEffect(() => {                            │
│   fetchAnalytics(authUser);                 │
│ })                                           │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ HTTP GET /analytics/langfuse/               │
│ dashboard-summary                            │
│                                              │
│ Headers:                                     │
│ Authorization: Bearer {access_token}         │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Backend Endpoint Handler                    │
│ (app/endpoints.py)                           │
│                                              │
│ 1. Verify admin access                       │
│ 2. Initialize httpx client                   │
│ 3. Build auth with Langfuse credentials      │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Loop: Fetch Traces in Batches                │
│                                              │
│ while True:                                  │
│   response = await client.get(               │
│     f"{LANGFUSE_HOST}/api/public/traces",   │
│     params={ page, limit: 100 }              │
│     auth=(PUBLIC_KEY, SECRET_KEY)            │
│   )                                          │
│                                              │
│   Process traces batch                       │
│   Aggregate data                             │
│                                              │
│   if len(traces) < 100:                      │
│     break                                    │
│                                              │
│   page += 1                                  │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Data Aggregation                             │
│                                              │
│ For each trace:                              │
│ ├─ Extract user_id, user_email, question    │
│ ├─ Track in users_activity dict             │
│ ├─ Append question to all_questions list    │
│                                              │
│ After all traces:                            │
│ ├─ Count questions per user                 │
│ ├─ Find top 10 users                        │
│ ├─ Find top 5 questions                     │
│ ├─ Calculate statistics                     │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ JSON Response                                │
│ {                                            │
│   status: "success",                         │
│   summary: { ... },                          │
│   most_active_users: [ ... ],                │
│   top_questions: [ ... ]                     │
│ }                                            │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Frontend Receives Data                       │
│                                              │
│ setSummary(data.summary)                     │
│ setMostActiveUsers(data.most_active_users)  │
│ setTopQuestions(data.top_questions)         │
│                                              │
└──────────┬───────────────────────────────────┘
           │
           ↓
┌──────────────────────────────────────────────┐
│ Dashboard Renders                            │
│                                              │
│ 📊 Summary Cards                             │
│ 👥 Most Active Users Table                   │
│ ❓ Top Questions List                        │
│ 🔄 Refresh Button                            │
│                                              │
└──────────────────────────────────────────────┘
```

## Component Tree

```
App
├─ Login Page
├─ Chat Pages
│  ├─ New Chat
│  ├─ Existing Chat
│  └─ Shared Chat
├─ ChatSidebar (UPDATED)
│  └─ Admin Section
│     ├─ Langfuse Analytics ← NEW (routes to)
│     └─ Most Asked Questions
└─ Admin Pages
   ├─ admin/top-questions (existing)
   └─ admin/analytics (NEW) ← Currently viewing
      ├─ Summary Cards
      ├─ Tab Navigation
      ├─ Overview Tab
      │  ├─ Most Active Users Table
      │  └─ Top Questions List
      ├─ Users Tab
      │  └─ All Users Table
      └─ Questions Tab
         └─ Top Questions Detail View
```

## Authentication & Authorization Flow

```
┌─────────────────────┐
│   User Logs In      │
└────────┬────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ Gets access_token from Microsoft OAuth  │
└────────┬────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ Stored in localStorage                  │
│ {                                       │
│   user_id: "...",                       │
│   email: "user@cloudfuze.com",          │
│   access_token: "eyJ0eXAi...",          │
│   ...                                   │
│ }                                       │
└────────┬────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ Admin Opens /admin/analytics            │
└────────┬────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ Frontend Check: isAdminEmail(email)     │
│ ✓ YES: Load dashboard                   │
│ ✗ NO: Redirect to /login                │
└────────┬────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ API Request to Backend                  │
│                                         │
│ fetch('/analytics/langfuse/...', {      │
│   headers: {                            │
│     Authorization: `Bearer ${token}`    │
│   }                                     │
│ })                                      │
│                                         │
└────────┬────────────────────────────────┘
         │
         ↓
┌─────────────────────────────────────────┐
│ Backend: @require_restricted_admin      │
│                                         │
│ Check 1: Extract Bearer token           │
│ Check 2: Verify with Microsoft Graph    │
│ Check 3: Validate CloudFuze email       │
│ Check 4: Admin allowlist check          │
│                                         │
│ ✓ All pass → Execute endpoint           │
│ ✗ Any fail → Return 401/403 error       │
│                                         │
└─────────────────────────────────────────┘
```

## Data Structure Diagram

```
Langfuse Trace Object
├─ id: "trace_123abc"
├─ userId: "user_456"
├─ name: "chat_interaction"
├─ input: "How to migrate data?"
├─ output: "To migrate data, follow these steps..."
├─ timestamp: "2024-01-20T15:45:00Z"
├─ metadata: {
│  ├─ user_id: "user_456"
│  ├─ user_email: "john@cloudfuze.com"
│  ├─ user_name: "John Doe"
│  ├─ department: "Sales"
│  ├─ session_id: "session_789"
│  ├─ request: {
│  │  ├─ endpoint: "/chat/stream"
│  │  └─ timestamp: "2024-01-20T15:45:00Z"
│  ├─ intent: {
│  │  ├─ detected: "migration_query"
│  │  └─ confidence: 0.95
│  └─ query: {
│     └─ is_conversational: false
│  }
├─ tags: ["chat", "rag"]
└─ ...
```

## API Response Structure

```
GET /analytics/langfuse/dashboard-summary

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
      "user_id": "user_123",
      "email": "john@cloudfuze.com",
      "name": "John Doe",
      "questions_asked": 150
    },
    { ... }
  ],
  "top_questions": [
    {
      "question": "How to migrate data?",
      "times_asked": 45
    },
    { ... }
  ]
}
```

## Performance & Scalability

```
┌─────────────────────────────────────┐
│ Langfuse API Pagination             │
├─────────────────────────────────────┤
│                                     │
│ Fetches: 100 traces per request     │
│ Repeat: Until no more traces        │
│                                     │
│ Example:                            │
│ Page 1: Traces 1-100                │
│ Page 2: Traces 101-200              │
│ Page 3: Traces 201-300              │
│ ...                                 │
│ Page N: Remaining traces            │
│                                     │
│ Total Requests: ceil(total / 100)   │
│                                     │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│ Time Complexity Analysis            │
├─────────────────────────────────────┤
│                                     │
│ Fetching: O(n) where n = traces     │
│ Aggregating: O(n)                   │
│ Sorting: O(k log k) where k = 10    │
│ Counter ops: O(n)                   │
│                                     │
│ Total: O(n)                         │
│                                     │
│ For 10,000 traces: ~1-2 seconds     │
│ For 50,000 traces: ~5-10 seconds    │
│ For 100,000 traces: ~20-30 seconds  │
│                                     │
└─────────────────────────────────────┘
```

---

This comprehensive architecture ensures:
- ✅ Scalability for growing user bases
- ✅ Security with multi-layer authentication
- ✅ Performance through efficient pagination
- ✅ Maintainability with clear separation of concerns
- ✅ Reliability with error handling and retries

