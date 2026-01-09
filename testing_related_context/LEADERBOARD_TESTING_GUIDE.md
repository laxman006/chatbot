# Team Leaderboard Testing Guide

## Overview

The Team Analytics page now features a **leaderboard** that displays teams ranked by the number of questions asked. This guide will walk you through testing the feature.

## Testing Steps

### 1. **Access the Team Analytics Dashboard**
```
URL: http://localhost:3000/admin/teams
```
- Login with an admin account (see `frontend/src/constants/admins.ts` for valid emails)
- You should see the admin check pass and load the dashboard

### 2. **Calendar Date Range Picker**
- Click on the date range button (shows current date)
- Select a **start date** from the calendar
- Select an **end date** from the calendar
- Click **"Apply"** to fetch data for that date range
- You should see a loading state while data is being fetched

### 3. **Leaderboard Section**
After applying the date filter, you should see:

**Header:** "🏆 Team Leaderboard"

**Table Columns:**
- **Rank** - Shows 🥇 🥈 🥉 for top 3, numeric for others
- **Team Name** - Team name with color indicator square
- **Total Questions** - Total number of questions asked
- **Unique Questions** - Number of unique questions
- **Active Members** - Active members / Total members ratio
- **Avg Questions** - Average questions per active member

### 4. **Visual Features to Verify**

#### Color Coding
- [ ] Top 3 teams have a subtle background color (based on team color)
- [ ] Team name row has a color square indicator
- [ ] Medals are displayed for top 3 teams

#### Hover Effects
- [ ] Hover over any team row
- [ ] Background should highlight (darker shade of team color)
- [ ] Cursor should change to pointer
- [ ] Row should appear interactive

#### Sorting
- [ ] Teams should be sorted by total questions (highest first)
- [ ] 🥇 should be the team with most questions
- [ ] 🥈 should be second highest
- [ ] 🥉 should be third highest

### 5. **Interactive Features**

#### Click on Team Row
- [ ] Click any team row in the leaderboard
- [ ] Should open a modal with team details
- [ ] Modal should show:
  - Team lead name
  - Total questions for the selected date range
  - Active members count
  - Unique questions count
  - List of team members

#### Cache Verification
- [ ] Select a date range and click Apply
- [ ] Wait for data to load
- [ ] Select the **same** date range again and click Apply
- [ ] Should load instantly from cache (no "Fetching..." state)
- [ ] You should see a "Using cached data from X minutes ago" message (if implemented)

### 6. **Data Accuracy Checks**

#### Email Matching
- [ ] Verify that users are assigned to correct teams
- [ ] Check that emails are matched case-insensitively
- [ ] Verify that users not in any team show as "Unassigned"

#### Question Counting
- [ ] Total Questions should match unique user inputs
- [ ] Unique Questions should be less than or equal to Total Questions
- [ ] Active Members should not exceed Total Members

#### Average Calculation
- [ ] Avg Questions should = Total Questions ÷ Active Members
- [ ] Should be rounded to nearest integer
- [ ] Should handle zero active members gracefully

### 7. **Leaderboard-Specific Tests**

#### Example Test Case 1: Single Day
```
Start Date: 2025-12-16
End Date: 2025-12-16
Expected: Shows only data from today
```

#### Example Test Case 2: Full Month
```
Start Date: 2025-12-01
End Date: 2025-12-31
Expected: Shows cumulative data for December
```

#### Example Test Case 3: Custom Range
```
Start Date: 2025-12-10
End Date: 2025-12-16
Expected: Shows data for 7-day period
```

### 8. **Performance Testing**

- [ ] **Load Time:** Leaderboard should load within 5 seconds for most date ranges
- [ ] **Memory:** No memory leaks when switching between date ranges
- [ ] **Rendering:** Table should render smoothly even with 16 teams
- [ ] **Caching:** Selecting same date range again should be instant

### 9. **Error Handling Tests**

#### Network Error
- [ ] Unplug network connection (if testing offline)
- [ ] Try to apply date filter
- [ ] Should show error message
- [ ] Should allow retry

#### Invalid Date Range
- [ ] Select end date before start date
- [ ] Should show error or auto-correct
- [ ] Should not fetch data

#### No Data Available
- [ ] Select a very old date range with no activity
- [ ] Should show "No team data available" message
- [ ] Leaderboard should be empty but formatted correctly

## Expected Leaderboard Output Example

```
Rank  Team Name           Total Questions  Unique Questions  Active Members  Avg Questions
🥇    Content                 450               120            8/12              56
🥈    Messaging & Email        380               95             9/19              42
🥉    QA                       320               88             7/9               46
4.    Neutara Labs             280               72             6/8               47
5.    CF Manage                200               55             3/5               67
6.    Marketing                180               50             5/10              36
7.    Sales Ops                150               40             2/4               75
8.    M1                       120               35             3/5               40
9.    M2                       100               28             2/5               50
...and so on
```

## Debugging Tips

### If Leaderboard Doesn't Show

1. **Check Admin Status**
   - Verify you're logged in with an admin account
   - Check browser console for auth errors

2. **Check Backend Logs**
   - Look at terminal running `python server.py`
   - Should see API requests to `/analytics/langfuse/teams/summary`
   - Look for any error messages

3. **Check Frontend Console**
   - Open browser DevTools (F12)
   - Check Console tab for JavaScript errors
   - Check Network tab for failed API requests

4. **Verify Teams Data**
   - Run: `python app/models/teams.py` to verify team structure
   - Should output all 16 teams with their structure

### If Teams are "Unassigned"

1. Check the user email format in Langfuse traces
2. Verify email matches a team member email exactly
3. Run a test: 
   ```python
   from app.models.teams import get_team_by_member_email
   print(get_team_by_member_email("santosh@cloudfuze.com"))  # Should return "Content"
   ```

### If Questions Count is Zero

1. Verify there are traces in Langfuse for the selected date range
2. Check that traces have proper metadata with `user_email` field
3. Try a broader date range (e.g., all time)

## Team List for Reference

1. Content (Lead: Santosh Chintalapelli)
2. Messaging & Email (Lead: Ankit Mishra)
3. CF Manage (Lead: Ravi Achakka Chandra)
4. QA (Lead: Kamal Basha)
5. Neutara Labs (Lead: Ravi Poli)
6. Infra (Lead: Pavan Bhagavathula)
7. Marketing (Lead: Arun Jyothi)
8. Pre-Sales (Lead: Nivas)
9. M1 (Lead: Nikhil Patel)
10. M2 (Lead: Maheswari Aram)
11. M3 (Lead: Lakshmi Prasanna)
12. M4 (Lead: Neelima Krotta)
13. M5 (Lead: Abhishikth Yenugula)
14. BD (Lead: Karthik Brahmakal)
15. Sales Ops (Lead: Rahul Gowda)
16. Sales – SMB (Lead: Chitradip Saha)
17. Sales – ENT (Lead: Anthony Raymond)
18. Sales – AM (Lead: Lawrence Lewis)
19. HR (Lead: Gopi Krishna)

## Success Criteria

✅ All of the following should pass:
- [ ] Leaderboard displays all 16 teams
- [ ] Teams are sorted by total questions
- [ ] Top 3 teams show medal emojis
- [ ] Hover effects work smoothly
- [ ] Click to open team details works
- [ ] Cache works for repeated date range selections
- [ ] All team colors display correctly
- [ ] No console errors appear
- [ ] Email matching assigns users to correct teams
- [ ] Performance is responsive (< 5 second load time)

## Next Steps After Testing

1. If all tests pass: Ready to deploy to production
2. If issues found: Debug and fix before deployment
3. Monitor Langfuse data to ensure analytics are accurate
4. Collect user feedback on the leaderboard UX

