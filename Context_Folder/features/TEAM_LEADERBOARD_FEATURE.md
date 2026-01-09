# Team Leaderboard Feature

## Overview

Displays team-based analytics and leaderboard showing which teams ask the most questions. Includes team member breakdowns and rankings.

---

## Related Files

### Backend Files

#### Team Models
- **`app/models/teams.py`**
  - `TEAMS_STRUCTURE` - Team definitions with members
  - `get_team_by_name()` - Get team by name
  - `get_team_by_email()` - Get team by user email
  - `get_all_teams()` - Get all teams
  - Team color assignments
  - Team lead information

#### Team Endpoints
- **`app/endpoints.py`**
  - `GET /teams/list` - Get all teams (line 2911)
  - `GET /admin/teams` - Team analytics (line 3672)
  - `GET /analytics/langfuse/teams/summary` - Teams summary (line 3999)
  - `GET /analytics/langfuse/teams/details` - Team details (line 4261)

#### Analytics Integration
- **`app/mongodb_memory.py`**
  - `get_team_statistics()` - Get team stats (if exists)
  - User activity aggregation by team

- **`app/langfuse_integration.py`**
  - Team analytics from Langfuse

### Frontend Files

#### Team Pages
- **`frontend/src/app/admin/teams/page.tsx`**
  - Team leaderboard page
  - Team rankings and statistics

- **`frontend/src/app/admin/teams-dashboard/page.tsx`**
  - Team dashboard page
  - Detailed team analytics

#### Team Components
- **`frontend/src/components/DateRangeFilter.tsx`**
  - Date range filtering for team stats

- **`frontend/src/components/DeveloperExclusionFilter.tsx`**
  - Exclude developers from team stats

#### API Integration
- **`frontend/src/lib/api.ts`**
  - `getTeamsList()` - Get all teams
  - `getTeamsSummary()` - Get teams summary
  - `getTeamDetails()` - Get team details

---

## Feature Workflow

1. **User activity tracked** → Messages saved with user email
2. **Team matching** → Match user email to team
3. **Team aggregation** → Aggregate questions by team
4. **Ranking calculation** → Rank teams by question count
5. **Leaderboard display** → Show ranked teams with stats
6. **Team details** → Click team to see member breakdown

---

## Key Functions

### Backend
- `get_teams_list()` - Get all teams
- `get_teams_summary_mongodb()` - Get teams summary
- `get_team_details()` - Get team details
- `get_team_by_email()` - Match user to team

### Frontend
- `Teams` - Team leaderboard component
- `getTeamsSummary()` - Fetch teams data
- Date range filtering

---

## Team Structure

### 19 Teams Defined

**Development (6 teams):**
- Content (12 members)
- Messaging & Email (20 members)
- CF Manage (6 members)
- QA (10 members)
- Neutara Labs (9 members)
- Infra (6 members)

**Business (3 teams):**
- Marketing (11 members)
- Pre-Sales (3 members)
- BD (9 members)

**Manufacturing (5 teams):**
- M1, M2, M3, M4, M5 (4-6 members each)

**Sales (4 teams):**
- Sales Ops (5 members)
- Sales SMB (7 members)
- Sales ENT (3 members)
- Sales AM (7 members)

**Support (1 team):**
- HR (5 members)

---

## Team Matching

### Email-Based Matching
- User email matched to team member list
- Case-insensitive matching
- Exact email match required

### Unassigned Users
- Users not in any team → "Unassigned"
- Still tracked in analytics
- Can be assigned later

---

## Leaderboard Metrics

### Team Statistics
- **Total Questions** - Sum of all questions from team members
- **Unique Questions** - Count of unique questions
- **Active Members** - Members who asked questions
- **Average Questions** - Questions per active member
- **Team Rank** - Position in leaderboard

### Member Statistics
- **Questions per Member** - Individual question count
- **Member Rank** - Rank within team
- **Active Status** - Whether member asked questions

---

## Leaderboard Display

### Top 3 Teams
- 🥇 Gold medal for 1st place
- 🥈 Silver medal for 2nd place
- 🥉 Bronze medal for 3rd place

### Team Cards
- Team name and color
- Total questions
- Unique questions
- Active members
- Average questions per member

### Team Details Modal
- Team lead information
- All members with stats
- Member rankings
- Question breakdown

---

## Configuration

**Team Definitions:**
- `app/models/teams.py` - `TEAMS_STRUCTURE`
- 19 teams with 138+ members total

**Team Colors:**
- Each team has assigned color
- Used in UI for visual distinction

**Date Filtering:**
- Filter team stats by date range
- Applied to all team queries

---

## Database Queries

### Team Aggregation
```python
# Aggregate questions by team
for team in TEAMS_STRUCTURE:
    team_questions = 0
    for member in team['members']:
        user_questions = count_questions(member['email'], date_range)
        team_questions += user_questions
```

### Member Matching
```python
def get_team_by_email(email):
    for team in TEAMS_STRUCTURE:
        for member in team['members']:
            if member['email'].lower() == email.lower():
                return team
    return None
```

---

**Last Updated:** 2025-01-09
