# Team Leaderboard - Visual Guide

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│                   Team Analytics Dashboard                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  📅 Dec 13, 2025 → Dec 14, 2025    [Show Calendar] [Apply] [Reset]  │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Total Teams  │ Active Teams │ Total Questions │ Avg Q/Team │   │
│  │      19      │      15      │      2,500      │     132    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                   │
│  🏆 TEAM LEADERBOARD                                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ Rank │ Team Name        │ Questions │ Unique │ Active │Avg│   │
│  ├──────┼──────────────────┼───────────┼────────┼────────┼───┤   │
│  │ 🥇   │ ■ Content        │    450    │  120   │  8/12  │ 56│   │
│  │ 🥈   │ ■ Messaging & Em │    380    │   95   │  9/19  │ 42│   │
│  │ 🥉   │ ■ QA             │    320    │   88   │  7/9   │ 46│   │
│  │  4.  │ ■ Neutara Labs   │    280    │   72   │  6/8   │ 47│   │
│  │  5.  │ ■ CF Manage      │    200    │   55   │  3/5   │ 67│   │
│  │  6.  │ ■ Marketing      │    180    │   50   │  5/10  │ 36│   │
│  │  7.  │ ■ Sales Ops      │    150    │   40   │  2/4   │ 75│   │
│  │  8.  │ ■ M1             │    120    │   35   │  3/5   │ 40│   │
│  │  9.  │ ■ M2             │    100    │   28   │  2/5   │ 50│   │
│  │ 10.  │ ■ Infra          │     85    │   22   │  4/6   │ 21│   │
│  │ 11.  │ ■ M3             │     72    │   18   │  2/6   │ 36│   │
│  │ 12.  │ ■ M4             │     65    │   16   │  3/6   │ 22│   │
│  │ 13.  │ ■ Sales – SMB    │     58    │   14   │  2/7   │ 29│   │
│  │ 14.  │ ■ BD             │     45    │   11   │  2/9   │ 22│   │
│  │ 15.  │ ■ M5             │     38    │    9   │  1/4   │ 38│   │
│  │ 16.  │ ■ Pre-Sales      │     28    │    7   │  2/3   │ 14│   │
│  │ 17.  │ ■ Sales – ENT    │     22    │    5   │  1/3   │ 22│   │
│  │ 18.  │ ■ Sales – AM     │     18    │    4   │  1/7   │ 18│   │
│  │ 19.  │ ■ HR             │      8    │    2   │  1/5   │  8│   │
│  └──────┴──────────────────┴───────────┴────────┴────────┴───┘   │
│                                                                   │
│  Teams Overview                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ Content  │  │Messaging │  │ CF Manage│  │   QA     │         │
│  │          │  │  & Email │  │          │  │          │         │
│  │ ▬▬ 450 ▬▬│  │ ▬▬ 380 ▬▬│  │ ▬▬ 200 ▬▬│  │ ▬▬ 320 ▬▬│         │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘         │
│  [... and 15 more team cards ...]                              │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Leaderboard Color Scheme

### Team Colors
```
🔵 Content           (#3B82F6 - Blue)
🟢 Messaging & Email (#10B981 - Green)
🟡 CF Manage         (#F59E0B - Amber)
🔴 QA                (#EF4444 - Red)
🟣 Neutara Labs      (#8B5CF6 - Purple)
🩷 Infra             (#EC4899 - Pink)
🧿 Marketing         (#06B6D4 - Cyan)
🐚 Pre-Sales         (#14B8A6 - Teal)
💜 M1                (#A78BFA - Light Purple)
🧡 M2                (#F97316 - Orange)
💎 M3                (#06C6D4 - Cyan)
🟣 M4                (#7C3AED - Violet)
🩷 M5                (#EC4899 - Pink)
💙 BD                (#06B6D4 - Cyan)
💜 Sales Ops         (#8B5CF6 - Purple)
🟡 Sales – SMB       (#F59E0B - Amber)
🔴 Sales – ENT       (#EF4444 - Red)
🟢 Sales – AM        (#10B981 - Green)
🔵 HR                (#3B82F6 - Blue)
```

## Hover State

When you hover over a team row in the leaderboard:

```
Normal State:
┌─────┬────────────────┬──────────┬─────────┬────────┬──────┐
│🥇  │ ■ Content      │   450    │  120    │ 8/12   │ 56   │
└─────┴────────────────┴──────────┴─────────┴────────┴──────┘

Hover State (darker background):
┏━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━┳━━━━━━┓
┃🥇  ┃ ■ Content      ┃   450    ┃  120    ┃ 8/12   ┃ 56   ┃
┗━━━━━┻━━━━━━━━━━━━━━━━┻━━━━━━━━━━┻━━━━━━━━━┻━━━━━━━━┻━━━━━━┛
Cursor changes to pointer, background highlights
```

## Top 3 Teams Highlighting

```
Top 3 teams have subtle background color:

🥇 Team (Top Highlight)
┌──────────────────────────────────┐
│ Background: Team Color @ 8% opacity
└──────────────────────────────────┘

🥈 Team (Second Highlight)
┌──────────────────────────────────┐
│ Background: Team Color @ 8% opacity
└──────────────────────────────────┘

🥉 Team (Third Highlight)
┌──────────────────────────────────┐
│ Background: Team Color @ 8% opacity
└──────────────────────────────────┘

4. Other Teams (No highlight)
┌──────────────────────────────────┐
│ Background: White
└──────────────────────────────────┘
```

## Team Details Modal

When you click on a team row:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  Content Team Details                         [×]  │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                     │
│  ┌───────────────┐  ┌──────────────┐              │
│  │ Lead          │  │ Total        │              │
│  │ Santosh..     │  │ Questions    │              │
│  │               │  │ 450          │              │
│  └───────────────┘  └──────────────┘              │
│  ┌───────────────┐  ┌──────────────┐              │
│  │ Active Members│  │ Unique       │              │
│  │ 8 / 12        │  │ Questions    │              │
│  │               │  │ 120          │              │
│  └───────────────┘  └──────────────┘              │
│                                                     │
│  Team Members                                      │
│  ┌──────────────────────────┐                     │
│  │ Member Name    │ Qs │ Top│                     │
│  ├──────────────────────────┤                     │
│  │ Akhila         │ 42 │ ... │                    │
│  │ Shaikh Adnan   │ 38 │ ... │                    │
│  │ Mayank         │ 35 │ ... │                    │
│  │ Amuda          │ 31 │ ... │                    │
│  │ Praveen        │ 29 │ ... │                    │
│  │ Naved          │ 27 │ ... │                    │
│  │ Srinu G        │ 24 │ ... │                    │
│  │ Ravi S         │ 22 │ ... │                    │
│  └──────────────────────────┘                     │
│                                                     │
└─────────────────────────────────────────────────────┘
```

## Date Range Picker

### Calendar Interface

```
┌─────────────────────────────────────┐
│  Select Start Date                  │
├─────────────────────────────────────┤
│                                     │
│  ← December 2025 →                  │
│                                     │
│  S  M  T  W Th  F  S                │
│           1  2  3  4  5  6          │
│  7  8  9 10 11 12 [13] 14           │
│ 15 16 17 18 19 20 21 22             │
│ 23 24 25 26 27 28 29 30             │
│ 31                                  │
│                                     │
│ [13 is highlighted - selected date] │
│                                     │
└─────────────────────────────────────┘
```

### Preset Filters (if added later)

```
Preset Filters:
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Today       │ │ Yesterday   │ │ This Week   │
└─────────────┘ └─────────────┘ └─────────────┘

┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Last 7 Days │ │ This Month  │ │ All Time    │
└─────────────┘ └─────────────┘ └─────────────┘
```

## Summary Stats Row

```
┌──────────────┬──────────────┬──────────────┬──────────────┐
│  Total Teams │ Active Teams │ Total Quest. │ Avg Q/Team   │
│      19      │      15      │    2,500     │     132      │
└──────────────┴──────────────┴──────────────┴──────────────┘
```

## Key Visual Features

### 1. Medal System
```
🥇 Gold Medal    - Rank 1 (Most questions)
🥈 Silver Medal  - Rank 2 (Second most)
🥉 Bronze Medal  - Rank 3 (Third most)
4., 5., 6.      - Numeric ranks (4th onwards)
```

### 2. Color Indicator
```
Each row has a small colored square before team name:
[■] Content              - Blue square
[■] Messaging & Email    - Green square
[■] QA                   - Red square
etc.
```

### 3. Row Highlighting
```
Normal:      │ 🥇 │ ■ Content │ 450 │ 120 │ 8/12 │ 56 │ (White bg)
Hover:       │ 🥇 │ ■ Content │ 450 │ 120 │ 8/12 │ 56 │ (Blue bg)
Top 3 Row:   │ 🥇 │ ■ Content │ 450 │ 120 │ 8/12 │ 56 │ (Light Blue bg)
Top 3 Hover: │ 🥇 │ ■ Content │ 450 │ 120 │ 8/12 │ 56 │ (Darker Blue bg)
```

## Responsive Design

### Desktop (1920px+)
- Full table with all columns visible
- 16-18px font
- Standard hover effects

### Tablet (768px - 1024px)
- Table scrolls horizontally if needed
- Slightly reduced padding
- Touch-friendly hover states

### Mobile (< 768px)
- Table scrolls horizontally
- Reduced column widths
- Larger touch targets
- Stack some columns if needed

## Performance Indicators

### Cache Status (if visible)
```
✓ Using cached data (loaded 5 minutes ago)
↻ Fetching latest data...
⚠ Data may be outdated
```

### Loading State
```
┌─────────────────────────────┐
│ Fetching team analytics... │
│ ████░░░░░░ 40%             │
└─────────────────────────────┘
```

---

## Interactive Behaviors

### 1. Clicking a Team Row
```
Before:  │ 4. │ ■ Neutara Labs │ 280 │ 72 │ 6/8 │ 47 │
         └─────┴────────────────┴─────┴────┴─────┴────┘

After:   → Opens modal with team details
         → Highlights the selected row
         → Can view individual member stats
```

### 2. Sorting (Automatic)
```
Teams always sorted by Total Questions (descending):
- Highest to lowest questions
- Top performers appear first
- Easy to identify most active teams
```

### 3. Date Range Changes
```
Select dates → Click Apply → Data refreshes → Leaderboard updates
              ↓
        Cache stored for 1 hour
              ↓
        Select same dates again → Instant load from cache
```

---

## Example Data Visualization

### Comparing Teams

```
Team                 Questions  Trend
Content              ████████░  ⬆ (up 15%)
Messaging & Email    ███████░░  ⬆ (up 8%)
QA                   ██████░░░  ⬇ (down 5%)
Neutara Labs         ██████░░░  ➡ (stable)
CF Manage            █████░░░░  ⬇ (down 12%)
```

### Member Activity Distribution

```
Content Team Members Activity:
Akhila:        ███████░░ 42 questions
Shaikh:        ██████░░░ 38 questions
Mayank:        ██████░░░ 35 questions
Amuda:         █████░░░░ 31 questions
...
```

---

## Accessibility Features

- ✓ Color + text indicators (not just color)
- ✓ Keyboard navigation (tab through rows)
- ✓ Screen reader friendly (proper labels)
- ✓ High contrast colors
- ✓ Clear hierarchy and spacing
- ✓ Meaningful icons (medals, color squares)

---

This visual guide helps you understand how the leaderboard appears and behaves in the actual application!

