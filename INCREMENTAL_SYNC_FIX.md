# Incremental Sync Fix - Datetime Instead of Date-Only

## Problem Identified

All syncs were showing `"documents_added": 0` because:

1. **Date-only comparison**: The sync was using only the date (`YYYY-MM-DD`) instead of full datetime
2. **Same-day syncs**: Multiple syncs on the same day all queried from the start of that day
3. **Duplicate filtering**: All tickets found were already in the vectorstore (from earlier syncs)
4. **Result**: 0 documents added even when tickets were updated

### Example of the Problem:
- **First sync** at `2026-01-23 00:43:25`: Queries `updated >= '2026-01-23'` → Finds tickets
- **Second sync** at `2026-01-23 14:52:44`: Queries `updated >= '2026-01-23'` → Finds same tickets → Filters as duplicates → 0 added

## Solution Implemented

### Changes Made:

1. **`app/jira_vectorstore.py` (lines 186-196)**:
   - Changed from date-only (`YYYY-MM-DD`) to datetime (`YYYY-MM-DD HH:mm`)
   - Subtracts 1 minute from last sync time to catch tickets updated at exact sync time
   - Format: `YYYY-MM-DD HH:mm` (Jira JQL compatible)

2. **`app/jira_processor.py` (lines 315-355)**:
   - Updated docstrings to reflect datetime support
   - JQL query already supports datetime format, no code changes needed

### Code Changes:

**Before:**
```python
last_sync_dt = datetime.fromisoformat(last_sync)
since_date = last_sync_dt.strftime('%Y-%m-%d')  # Only date!
```

**After:**
```python
last_sync_dt = datetime.fromisoformat(last_sync)
# Subtract 1 minute to catch tickets updated at the exact sync time
since_datetime = last_sync_dt - timedelta(minutes=1)
since_date = since_datetime.strftime('%Y-%m-%d %H:%M')  # Datetime!
```

## How It Works Now

### Example:
- **First sync** at `2026-01-23 00:43:25`: 
  - Queries `updated >= '2026-01-23 00:42'` → Finds tickets → Adds them
  
- **Second sync** at `2026-01-23 14:52:44`: 
  - Queries `updated >= '2026-01-23 14:51'` → Finds NEW tickets updated since 00:43 → Adds them ✅

### Benefits:
1. ✅ **Multiple syncs per day work correctly** - Each sync finds tickets updated since the last sync
2. ✅ **No duplicate filtering** - Only truly new/updated tickets are found
3. ✅ **Catches edge cases** - 1-minute buffer ensures tickets updated at exact sync time are included
4. ✅ **More accurate** - Uses precise timestamp instead of whole day

## Testing

Run the test script to verify:
```bash
python test_incremental_sync_fix.py
```

Expected output:
- ✅ Datetime format is correct
- ✅ Handles midnight correctly
- ✅ JQL query format is valid

## Verification Steps

1. **Check the fix is applied**:
   ```bash
   grep -A 5 "since_datetime" app/jira_vectorstore.py
   ```
   Should show datetime calculation with `timedelta(minutes=1)`

2. **Test manual sync**:
   - Go to `/admin/jira` → "Sync & Status" tab
   - Click "Trigger Manual Sync"
   - Check sync history - should show `documents_added > 0` if there are new tickets

3. **Monitor sync logs**:
   - Look for: `[*] Fetching tickets updated since YYYY-MM-DD HH:mm...`
   - Should show datetime format, not just date

4. **Check sync history**:
   - View `data/jira_last_sync.json`
   - `documents_added` should be > 0 when new tickets are found

## Expected Behavior

### When New Tickets Exist:
- Sync finds tickets updated since last sync time
- Adds them to vectorstore
- Updates `documents_added` count
- Status: `"success"` with count > 0

### When No New Tickets:
- Sync queries correctly (using datetime)
- Finds no tickets updated since last sync
- Status: `"no_updates"` with count = 0
- This is correct behavior!

## Notes

- **1-minute buffer**: Subtracting 1 minute ensures we don't miss tickets updated at the exact sync time
- **Jira JQL format**: Jira supports both `YYYY-MM-DD` and `YYYY-MM-DD HH:mm` formats
- **Backward compatible**: Still works with date-only format if needed
- **Timezone**: Uses server's local timezone (same as sync tracker)

## Summary

✅ **Fixed**: Incremental sync now uses datetime instead of date-only
✅ **Result**: Multiple syncs per day will correctly find new tickets
✅ **Tested**: Datetime format verified and edge cases handled
✅ **Ready**: Can now sync multiple times per day and see actual document counts

The fix ensures that `documents_added` will reflect the actual number of new/updated tickets found and added to the vectorstore.
