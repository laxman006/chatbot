# Analytics Feature

## Overview

Tracks user activity, questions, sessions, and provides analytics dashboards for admins. Integrates with Langfuse for observability.

---

## Related Files

### Backend Files

#### Analytics Endpoints
- **`app/endpoints.py`**
  - `GET /admin/users/summary` - All-time user statistics (line 3564)
  - `GET /admin/rankers` - Ranked users by date range (line 3602)
  - `GET /admin/questions/top` - Most asked questions (line 3504)
  - `GET /admin/teams` - Team analytics (line 3672)
  - `GET /analytics/langfuse/teams/summary` - Langfuse teams summary (line 3999)
  - `GET /analytics/langfuse/teams/details` - Team details (line 4261)
  - `GET /analytics/langfuse/dashboard-summary` - Dashboard summary (line 4516)
  - `GET /analytics/langfuse/users` - User analytics (line 4748)
  - `GET /analytics/langfuse/users/{user_id}` - User-specific analytics (line 5004)
  - `GET /analytics/langfuse/top-questions` - Top questions (line 5224)

#### MongoDB Analytics
- **`app/mongodb_memory.py`**
  - `get_user_statistics()` - Get user stats (line 1200+)
  - `get_rankers_by_date()` - Get ranked users (line 1300+)
  - `track_message_event()` - Track message event (line 1400+)
  - `track_faq_event()` - Track FAQ event (line 1500+)
  - `get_user_activity()` - Get user activity (line 1600+)

#### Langfuse Integration
- **`app/langfuse_integration.py`**
  - Langfuse client initialization
  - Trace creation and tracking
  - Feedback tracking
  - Analytics aggregation

#### Team Models
- **`app/models/teams.py`**
  - `TEAMS_STRUCTURE` - Team definitions
  - `get_team_by_name()` - Get team info
  - Team member matching

#### User Data
- **`app/user_data.py`**
  - `get_user_job_title()` - Get user job title
  - User profile data

### Frontend Files

#### Analytics Pages
- **`frontend/src/app/admin/dashboard/page.tsx`**
  - Main analytics dashboard
  - User statistics, charts

- **`frontend/src/app/admin/analytics/page.tsx`**
  - Detailed analytics page
  - Langfuse integration

- **`frontend/src/app/admin/top-questions/page.tsx`**
  - Top questions page
  - Most asked questions list

#### Analytics Components
- **`frontend/src/components/DateRangeFilter.tsx`**
  - Date range filter component
  - Start/end date selection

- **`frontend/src/components/DateRangeFilterDropdown.tsx`**
  - Dropdown date filter

- **`frontend/src/components/DeveloperExclusionFilter.tsx`**
  - Exclude developers from stats
  - Toggle filter

- **`frontend/src/components/DeveloperExclusionFilterDropdown.tsx`**
  - Dropdown exclusion filter

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `getUserStats()` - Get user statistics
  - `getRankers()` - Get ranked users
  - `getTopQuestions()` - Get top questions
  - `getTeamsSummary()` - Get teams summary
  - `getLangfuseAnalytics()` - Get Langfuse analytics

---

## Feature Workflow

1. **User asks question** → Message event tracked
2. **Event stored** → Saved to `message_events` collection
3. **User activity updated** → Updates `user_activity` collection
4. **Langfuse trace** → Created for observability
5. **Analytics aggregation** → Queries MongoDB for stats
6. **Dashboard display** → Frontend fetches and displays analytics

---

## Key Functions

### Backend
- `get_admin_users_summary()` - All-time statistics
- `get_admin_rankers()` - Ranked users by date
- `get_most_asked_questions()` - Top questions
- `get_teams_summary_mongodb()` - Team analytics
- `track_message_event()` - Track message
- `get_user_statistics()` - User stats

### Frontend
- `Dashboard` - Main dashboard component
- `DateRangeFilter` - Date filtering
- `getUserStats()` - Fetch statistics

---

## Database Collections

### message_events
```python
{
    "user_id": str,
    "user_email": str,
    "session_id": str,
    "question": str,
    "created_at": datetime,
    "trace_id": str  # Langfuse trace ID
}
```

### user_activity
```python
{
    "user_id": str,
    "total_messages": int,
    "total_sessions": int,
    "first_message_date": datetime,
    "last_active": datetime
}
```

### faq_events
```python
{
    "user_id": str,
    "question": str,
    "question_hash": str,
    "created_at": datetime
}
```

---

## Analytics Metrics

### User Statistics
- Total users
- Total questions
- Unique questions
- Total sessions
- Average questions per user

### User Rankings
- Ranked by question count
- Date range filtering
- Exclude developers option

### Top Questions
- Most asked questions
- Question frequency
- Unique question count

### Team Analytics
- Questions per team
- Active members
- Average questions per member
- Team rankings

---

## Langfuse Integration

### Traces
- Each chat interaction creates a trace
- Includes query, response, metadata
- Tracks feedback and ratings

### Analytics
- Aggregates traces for analytics
- Team-based analytics
- User-specific analytics
- Question analytics

---

## Configuration

**MongoDB Collections:**
- `message_events` - Message tracking
- `user_activity` - User statistics
- `faq_events` - FAQ tracking

**Excluded Developers:**
- `EXCLUDED_DEVELOPER_EMAILS` in `config.py`
- Defaults to admin emails

**Date Filtering:**
- Start date / End date
- Applied to all analytics queries

---

**Last Updated:** 2025-01-09
