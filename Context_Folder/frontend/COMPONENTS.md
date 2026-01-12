# Frontend Components Documentation

## Overview

All React components used in the CloudFuze Chatbot frontend, their purposes, props, and usage.

---

## Core Chat Components

### `ChatInterface.tsx`
**Location:** `src/components/ChatInterface.tsx`

**Purpose:** Main chat interface component - handles message display, input, and interaction

**Props:**
```typescript
interface ChatInterfaceProps {
  sessionId?: string;
  onSendMessage?: (message: string) => void;
}
```

**Features:**
- Empty state with welcome message
- Message list display
- Input textarea with character counter
- Suggested questions display
- Scroll to bottom button
- Feedback modal
- Markdown rendering for responses
- Copy message functionality
- Edit message functionality
- Feedback submission (thumbs up/down)

**Key Elements:**
- `#messages` - Messages container
- `#empty-state` - Empty state display
- `#user-input-empty` - Input in empty state
- `#suggested-questions-empty` - Suggested questions container
- `#feedback-modal` - Feedback modal overlay

**Functions (Global Window):**
- `copyMessage()` - Copy message to clipboard
- `submitFeedback()` - Submit feedback
- `editMessage()` - Edit message
- `askRecommendedQuestion()` - Ask suggested question
- `showFeedbackModal()` - Show feedback modal

---

### `ChatHeader.tsx`
**Location:** `src/components/ChatHeader.tsx`

**Purpose:** Chat header with actions (share, continue thread)

**Props:**
```typescript
interface ChatHeaderProps {
  isReadOnly: boolean;
  sessionId?: string;
  onContinueThread?: () => void;
  onShare?: () => void;
}
```

**Features:**
- Read-only badge display
- Continue thread button (for read-only chats)
- Share button (for own chats)
- Share modal

**Usage:**
- Rendered dynamically in chat initialization
- Injected into `#chat-header-container`

---

### `ChatSidebar.tsx`
**Location:** `src/components/ChatSidebar.tsx`

**Purpose:** Sidebar with session list, user info, and navigation

**Props:**
```typescript
interface ChatSidebarProps {
  isOpen: boolean;
  onToggle: () => void;
  onNewChat: () => void;
  onLoadSession?: (session: ChatSession, isReadOnly: boolean) => void;
  activeSessionId?: string;
}
```

**Features:**
- Session history (Today, Yesterday, Older)
- Others' chats section (admin only)
- New chat button
- User profile display
- Admin submenu (Dashboard, Analytics, Teams)
- Logout functionality
- Session deletion
- Collapsible sections
- Active session highlighting

**Key Functions:**
- `renderSessionHistory()` - Render session list
- `renderOthersHistory()` - Render others' chats (admin)
- `handleDeleteSession()` - Delete session
- `handleLogout()` - Logout user

**Storage:**
- Sessions stored in `localStorage` with user-specific keys
- Section collapse state in `localStorage`

---

## Analytics Components

### `DateRangeFilter.tsx`
**Location:** `src/components/DateRangeFilter.tsx`

**Purpose:** Date range filter component for analytics

**Features:**
- Start date picker
- End date picker
- Apply button
- Reset button
- Date validation

---

### `DateRangeFilterDropdown.tsx`
**Location:** `src/components/DateRangeFilterDropdown.tsx`

**Purpose:** Dropdown date range filter

**Props:**
```typescript
interface DateRangeFilterDropdownProps {
  onDateRangeChange: (range: DateRange) => void;
  initialRange?: DateRange;
}
```

**Features:**
- Calendar date picker
- Preset ranges (Today, This Week, This Month)
- Custom date range
- Apply/Reset buttons

**Exports:**
- `DateRange` type
- `DateRangeFilterDropdown` component

---

### `DeveloperExclusionFilter.tsx`
**Location:** `src/components/DeveloperExclusionFilter.tsx`

**Purpose:** Toggle to exclude developers from analytics

**Features:**
- Toggle switch
- Excluded users count display
- Applies to all analytics queries

---

### `DeveloperExclusionFilterDropdown.tsx`
**Location:** `src/components/DeveloperExclusionFilterDropdown.tsx`

**Purpose:** Dropdown for developer exclusion filter

**Features:**
- Toggle exclusion
- List of excluded users
- Count display

---

## Session Components

### `SessionCard.tsx`
**Location:** `src/components/SessionCard.tsx`

**Purpose:** Display session card in lists

**Features:**
- Session title
- Message count
- Last updated time
- Click to load session
- Delete button

---

## Utility Components

### `TokenMonitor.tsx`
**Location:** `src/components/TokenMonitor.tsx`

**Purpose:** Monitor token usage during streaming

**Features:**
- Real-time token count
- Display during streaming
- Token limit warnings

---

### `UserOnboardingModal.tsx`
**Location:** `src/components/UserOnboardingModal.tsx`

**Purpose:** Onboarding modal for new users

**Features:**
- Welcome message
- Feature introduction
- Dismiss functionality

---

## UI Components

### `ui/button.tsx`
**Location:** `src/components/ui/button.tsx`

**Purpose:** Reusable button component (Radix UI)

**Features:**
- Variants (primary, secondary, etc.)
- Sizes (sm, md, lg)
- Disabled state
- Loading state

---

### `ui/background-paths.tsx`
**Location:** `src/components/ui/background-paths.tsx`

**Purpose:** Background decorative paths

**Features:**
- SVG paths for decoration
- Animated backgrounds

---

## Component Patterns

### Client Components
All components are Client Components (`'use client'`) because they:
- Use React hooks (useState, useEffect)
- Handle user interactions
- Manage local state
- Access browser APIs (localStorage, window)

### Props Pattern
- TypeScript interfaces for all props
- Optional props with `?`
- Default values where appropriate

### State Management
- Local state with `useState`
- Side effects with `useEffect`
- Callbacks with `useCallback`
- Refs with `useRef`

---

## Component Communication

### Parent-Child
- Props passed down
- Callbacks for child-to-parent communication

### Global Functions
- Some functions attached to `window` object
- Used for dynamic event handlers
- Example: `window.copyMessage`, `window.submitFeedback`

### Event Handling
- DOM event listeners
- React event handlers
- Custom events

---

## Component Lifecycle

### Mount
- `useEffect(() => {}, [])` - Run on mount
- Initialize state
- Fetch data
- Set up event listeners

### Update
- `useEffect(() => {}, [deps])` - Run on dependency change
- Re-render on prop/state changes
- Update DOM

### Unmount
- Cleanup in `useEffect` return
- Remove event listeners
- Cancel requests

---

## Styling

### Tailwind CSS Classes
- Utility classes for styling
- Responsive classes
- Hover/focus states

### Inline Styles
- Dynamic styles
- Conditional styling
- Animation styles

### CSS Classes
- Custom classes in `globals.css`
- Component-specific classes

---

## Key Component Files

### Chat Components
- `ChatInterface.tsx` - Main chat UI
- `ChatHeader.tsx` - Chat header
- `ChatSidebar.tsx` - Session sidebar

### Analytics Components
- `DateRangeFilter.tsx` - Date filter
- `DateRangeFilterDropdown.tsx` - Date dropdown
- `DeveloperExclusionFilter.tsx` - Exclusion toggle
- `DeveloperExclusionFilterDropdown.tsx` - Exclusion dropdown

### Utility Components
- `SessionCard.tsx` - Session card
- `TokenMonitor.tsx` - Token monitor
- `UserOnboardingModal.tsx` - Onboarding modal

### UI Components
- `ui/button.tsx` - Button component
- `ui/background-paths.tsx` - Background paths

---

**Last Updated:** 2025-01-09  
**Location:** `frontend/src/components/`
