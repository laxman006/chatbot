# Langfuse Analytics Dashboard - Quick Start Guide

## What's New?

A comprehensive **Langfuse Analytics Dashboard** has been added to the admin console at `/admin/analytics`.

## 🚀 How to Access

1. **Login** to the chatbot
2. Open the **sidebar** (menu icon)
3. Click **"Admin"** section
4. Click **"Langfuse Analytics"** (new button above "Most Asked Questions")

## 📊 Dashboard Overview

The dashboard has **3 main tabs**:

### 1️⃣ **Overview Tab** (Default)
Shows:
- 4 summary cards with key metrics
- Top 10 most active users
- Top 5 most asked questions

### 2️⃣ **All Users Tab**
Shows:
- Complete list of all users who've asked questions
- User email, name, total questions
- First question date and last activity date
- Scroll horizontally if needed

### 3️⃣ **Top Questions Tab**
Shows:
- Ranked list of most frequently asked questions
- How many times each question was asked
- Percentage of total questions

## 📈 Key Metrics Explained

| Metric | What it means |
|--------|---------------|
| **Total Users** | How many unique users have asked questions |
| **Total Questions** | Total number of questions asked by all users |
| **Unique Questions** | How many different questions were asked |
| **Avg Questions/User** | Average questions per user (total ÷ users) |

## 🎯 Use Cases

### Finding Knowledge Gaps
Look at "Top Questions Tab" to find most asked questions. These might indicate:
- Confusing features
- Missing documentation
- Common user pain points

### Identifying Power Users
Check "Overview" tab to see who's asking the most questions:
- Sales team members testing features
- Power users discovering features
- Users needing more training

### User Engagement Tracking
Use "All Users" tab to:
- Track new user adoption
- Monitor active vs inactive users
- Identify users who haven't logged in lately

## 🔄 Refreshing Data

Click the **"Refresh"** button to reload all data from Langfuse:
- Shows latest analytics
- Includes new questions asked since last view
- Updates all charts and tables

## ⚙️ Technical Details

**Backend Endpoints**:
- `/analytics/langfuse/dashboard-summary` - Summary data
- `/analytics/langfuse/users` - All users data
- `/analytics/langfuse/top-questions` - Top questions

**Data Source**: Langfuse traces with metadata
- User ID and email from trace metadata
- Questions from trace input field
- Timestamps from trace creation

## 📋 Admin Access

Only these users can access the dashboard:
- `laxman.kadari@cloudfuze.com`
- `chaitanya.malle@cloudfuze.com`
- `nirosh.reddy@cloudfuze.com`

To add more admins, update: `frontend/src/constants/admins.ts`

## 🐛 Troubleshooting

**Q: I see "Langfuse client not initialized"**
- A: Check that Langfuse credentials are set in `.env`
- Required: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`

**Q: No data is showing**
- A: 
  1. Ask some questions in the chatbot first
  2. Wait a few seconds for traces to process
  3. Click "Refresh" button

**Q: Page is loading slowly**
- A: This is normal for first load with many users. Be patient!

## 📝 What Data is Tracked?

For each question asked, Langfuse captures:
- **User ID** - Unique identifier
- **Email** - User's email address
- **Name** - User's display name
- **Question** - What they asked
- **Answer** - Bot's response
- **Timestamp** - When it was asked
- **Intent** - Type of question (general, specific, etc.)
- **Confidence** - How confident the bot was

## 🎨 UI Features

- **Responsive Design**: Works on desktop and tablet
- **Sortable Tables**: Click headers to sort (future)
- **Color Coded**: Active items highlighted in blue
- **Hover Effects**: Buttons highlight on hover
- **Real-time Refresh**: Click refresh for latest data

## 📱 Mobile Viewing

The dashboard is mostly readable on mobile, but:
- Best viewed on desktop/laptop
- Tables may need horizontal scrolling on small screens
- Use landscape mode for better view

## 🔐 Security

- ✅ Admin-only access (email-based)
- ✅ Requires valid auth token
- ✅ No data is cached locally
- ✅ Real-time fetch from Langfuse

## 📊 Example Dashboard Stats

```
Total Users: 150
Total Questions: 2,500
Unique Questions: 850
Avg Questions/User: 16.67

Top User: john.doe@cloudfuze.com (150 questions)
Top Question: "How to migrate data?" (45 times)
```

## 🚀 Performance Tips

1. **First Load**: May take 10-30 seconds with many users
2. **Refresh**: Usually faster (5-10 seconds)
3. **Large Datasets**: Consider splitting by date in future versions

## 📞 Support

Issues or questions?
- Check `LANGFUSE_ANALYTICS_IMPLEMENTATION.md` for technical details
- Verify `.env` has correct Langfuse credentials
- Ensure you have admin email in `admins.ts`

---

**Ready to explore?** Go to `/admin/analytics` now! 🎉

