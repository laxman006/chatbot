# Migration Combination Fixes - Teams to Chat Issue Resolution

## Date: January 27, 2026

## Problem Summary

The chatbot was incorrectly referencing "Slack to Teams Migration Guide" SharePoint links when users asked about "Teams to Chat" migration. This occurred due to multiple issues in the migration combination detection and filtering logic.

## Root Causes Identified

1. **Incorrect Pattern Matching**: The pattern `r"^chat\s+to"` incorrectly mapped "chat to teams" to `google_chat` platform
2. **Missing Documentation Links**: No hardcoded links for Teams to Chat or Chat to Teams migrations
3. **Cross-Contamination**: Slack to Teams documents were appearing in Teams to Chat queries
4. **Missing Intent Handling**: No specific intent classification for Teams to Chat or Chat to Teams migrations

## Fixes Implemented

### 1. Fixed Pattern Matching (`app/endpoints.py`)

**Location**: `extract_migration_direction()` function (lines ~1000-1120)

**Changes**:
- Removed ambiguous `r"^chat\s+to"` pattern from `google_chat` platform patterns
- Added explicit early detection for "Teams to Chat" patterns:
  - `teams to chat`
  - `teams to google chat`
  - `microsoft teams to chat`
  - `microsoft teams to google chat`
- Added explicit early detection for "Chat to Teams" patterns:
  - `chat to teams`
  - `google chat to teams`
  - `chat to microsoft teams`
  - `google chat to microsoft teams`
- Added logic to handle ambiguous "chat" text in direction patterns:
  - If target is "chat" and source is "teams" → assume Google Chat
  - If source is "chat" and target is "teams" → assume Google Chat as source

**Result**: The system now correctly identifies:
- Teams to Chat = Microsoft Teams → Google Chat
- Chat to Teams = Google Chat → Microsoft Teams
- Slack to Teams = Slack → Microsoft Teams (unchanged)

### 2. Added Missing Documentation Links (`config.py`)

**Location**: SYSTEM_PROMPT section (line ~238)

**Changes**:
- Added Teams to Chat Migration link: `https://www.cloudfuze.com/teams-to-chat-migration/`
- Added Chat to Teams Migration link: `https://www.cloudfuze.com/chat-to-teams-migration/`
- Added clarifying comments indicating direction (Microsoft Teams to Google Chat / Google Chat to Microsoft Teams)

**Result**: The LLM now has access to correct documentation links for Teams to Chat and Chat to Teams migrations.

### 3. Improved Cross-Contamination Prevention (`app/endpoints.py`)

**Location**: `filter_by_direction()` function (lines ~1200-1225)

**Changes**:
- Added explicit filtering logic to prevent Slack to Teams docs from appearing in Teams to Chat queries
- Added explicit filtering logic to prevent Teams to Chat docs from appearing in Slack to Teams queries
- In strict mode: completely removes mismatched documents
- In non-strict mode: heavily penalizes (80% score reduction) similar but wrong combinations

**Result**: When a user asks about "Teams to Chat", Slack to Teams documents are either removed or heavily penalized, preventing confusion.

### 4. Added Intent Classification (`app/endpoints.py`)

**Location**: `INTENT_BRANCHES` dictionary and intent detection logic (lines ~118-200)

**Changes**:
- Added `teams_chat_migration` intent for Teams to Chat queries
- Added `chat_teams_migration` intent for Chat to Teams queries
- Updated intent detection to check for Teams to Chat/Chat to Teams BEFORE checking for Slack to Teams
- Added filtering logic in `filter_documents_by_intent()` to:
  - Exclude Slack to Teams documents when intent is Teams to Chat
  - Exclude Slack to Teams documents when intent is Chat to Teams
  - Require both "teams" and "chat" keywords for Teams to Chat intent
  - Require both "chat" and "teams" keywords for Chat to Teams intent

**Result**: The system now properly classifies and routes Teams to Chat and Chat to Teams queries to the correct intent branch.

## Testing Recommendations

1. **Test Teams to Chat Queries**:
   - "Teams to Chat migration user mentions"
   - "Microsoft Teams to Google Chat migration"
   - "How to migrate Teams to Chat"

2. **Test Chat to Teams Queries**:
   - "Chat to Teams migration"
   - "Google Chat to Microsoft Teams"
   - "Migrate Chat to Teams"

3. **Verify Cross-Contamination Prevention**:
   - Query: "Teams to Chat migration" should NOT return Slack to Teams documents
   - Query: "Slack to Teams migration" should NOT return Teams to Chat documents

4. **Verify Documentation Links**:
   - Responses about Teams to Chat should reference Teams to Chat migration link
   - Responses about Chat to Teams should reference Chat to Teams migration link
   - Responses should NOT reference Slack to Teams link for Teams to Chat queries

## Files Modified

1. `app/endpoints.py`:
   - Updated `extract_migration_direction()` function
   - Updated `filter_by_direction()` function
   - Added new intent branches: `teams_chat_migration`, `chat_teams_migration`
   - Updated intent detection logic
   - Updated document filtering logic

2. `config.py`:
   - Added Teams to Chat Migration link
   - Added Chat to Teams Migration link

## Impact

- ✅ Users asking about "Teams to Chat" will now get correct responses
- ✅ No more incorrect references to "Slack to Teams Migration Guide"
- ✅ Proper distinction between Teams to Chat, Chat to Teams, and Slack to Teams
- ✅ Better document filtering prevents cross-contamination
- ✅ Correct documentation links are provided for each migration combination

## Notes

- The fixes maintain backward compatibility with existing Slack to Teams functionality
- All changes follow the existing code patterns and conventions
- No breaking changes to the API or response format
