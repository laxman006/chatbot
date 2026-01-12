# Pages & Routes Documentation

## Overview

All Next.js pages and routes in the CloudFuze Chatbot frontend, organized by feature and access level.

---

## Route Structure

### Public Routes (No Auth Required)

#### `/` - Home Page
**File:** `src/app/page.tsx`

**Purpose:** Redirects to `/chat/new`

**What it does:**
- Immediately redirects to `/chat/new`
- Shows loading spinner during redirect
- Client-side redirect using `useRouter().replace()`

**Code:**
```typescript
useEffect(() => {
  router.replace('/chat/new');
}, [router]);
```

---

#### `/login` - Login Page
**File:** `src/app/login/page.tsx`

**Purpose:** Microsoft OAuth login

**Features:**
- "Sign in with Microsoft" button
- Redirects to Microsoft OAuth
- Handles OAuth callback
- Stores user data in localStorage
- Redirect URL handling (backup in localStorage)

**Flow:**
1. User clicks "Sign in with Microsoft"
2. Redirects to Microsoft OAuth
3. User authenticates
4. Redirects back to `/auth/microsoft/callback`
5. Backend processes callback
6. Frontend receives token/session
7. Redirects to original URL or `/chat/new`

---

#### `/chat/shared/[token]` - Shared Chat
**File:** `src/app/chat/shared/[token]/page.tsx`

**Purpose:** View shared chat (read-only)

**Features:**
- Read-only chat display
- No authentication required
- "Continue in thread" button
- Share token validation
- Expiration check

**Access:** Public (no auth)

---

### Protected Routes (Auth Required)

#### `/chat/new` - New Chat
**File:** `src/app/chat/new/page.tsx`

**Purpose:** Start a new chat session

**Features:**
- Creates new session ID
- Initializes chat interface
- Empty state display
- Suggested questions

**Authentication:** Required (redirects to `/login` if not authenticated)

---

#### `/chat/[sessionId]` - Chat Session
**File:** `src/app/chat/[sessionId]/page.tsx`

**Purpose:** Chat page with specific session

**Features:**
- Loads session from backend
- Displays session messages
- Chat interface with sidebar
- Session management
- Read-only mode detection

**Authentication:** Required

**Session Loading:**
1. Check authentication
2. Load session from backend
3. Initialize chat interface
4. Display messages

---

#### `/chat/others/[sessionId]` - Others' Chat
**File:** `src/app/chat/others/[sessionId]/page.tsx`

**Purpose:** View other users' chats (read-only)

**Features:**
- Read-only mode
- Admin-only access
- "Continue in thread" functionality
- Session loading from backend

**Authentication:** Required (Admin only)

---

#### `/chats` - All Sessions
**File:** `src/app/chats/page.tsx`

**Purpose:** List all user sessions

**Features:**
- Session list display
- Session filtering
- Session deletion
- New chat button

**Authentication:** Required

---

### Admin Routes (Admin Only)

#### `/admin/dashboard` - Analytics Dashboard
**File:** `src/app/admin/dashboard/page.tsx`

**Purpose:** Main analytics dashboard

**Features:**
- User statistics
- Charts and graphs (Recharts)
- Date range filtering
- Developer exclusion filter
- All-time vs date-based stats
- User rankings

**Authentication:** Required (Admin only)

**API Calls:**
- `GET /admin/users/summary` - All-time stats
- `GET /admin/rankers` - Ranked users by date

---

#### `/admin/analytics` - Detailed Analytics
**File:** `src/app/admin/analytics/page.tsx`

**Purpose:** Detailed analytics page

**Features:**
- Langfuse analytics integration
- Detailed metrics
- Advanced filtering

**Authentication:** Required (Admin only)

---

#### `/admin/teams` - Team Leaderboard
**File:** `src/app/admin/teams/page.tsx`

**Purpose:** Team-based leaderboard

**Features:**
- Team rankings
- Team statistics
- Date range filtering
- Team member breakdown
- Team details modal

**Authentication:** Required (Admin only)

**API Calls:**
- `GET /admin/teams` - Team analytics
- `GET /analytics/langfuse/teams/summary` - Teams summary

---

#### `/admin/teams-dashboard` - Team Dashboard
**File:** `src/app/admin/teams-dashboard/page.tsx`

**Purpose:** Detailed team dashboard

**Features:**
- Team analytics
- Member statistics
- Performance metrics

**Authentication:** Required (Admin only)

---

#### `/admin/top-questions` - Top Questions
**File:** `src/app/admin/top-questions/page.tsx`

**Purpose:** Most asked questions

**Features:**
- Question list
- Question frequency
- Question analytics

**Authentication:** Required (Admin only)

**API Calls:**
- `GET /admin/questions/top` - Top questions

---

## API Routes

### `/api/proxy/[...path]` - API Proxy
**File:** `src/app/api/proxy/[...path]/route.ts`

**Purpose:** Proxy backend API requests (development)

**Features:**
- Same-origin requests
- Cookie forwarding
- CORS handling
- Request/response proxying

**Usage:** Development only (when `NEXT_PUBLIC_USE_PROXY=true`)

---

### `/api/shared-chat/[token]` - Shared Chat API
**File:** `src/app/api/shared-chat/[token]/route.ts`

**Purpose:** API route for shared chat

**Features:**
- Fetch shared chat data
- Token validation
- Expiration check

---

## Route Protection

### Authentication Check
```typescript
useEffect(() => {
  const checkAuth = async () => {
    const isLoggedIn = await checkSession();
    if (!isLoggedIn) {
      router.replace('/login');
    }
  };
  checkAuth();
}, []);
```

### Admin Check
```typescript
useEffect(() => {
  const user = getCurrentUser();
  if (!isAdminEmail(user?.email)) {
    router.replace('/login?error=admin_only');
  }
}, []);
```

---

## Route Parameters

### Dynamic Routes
- `[sessionId]` - Session ID parameter
- `[token]` - Share token parameter
- `[...path]` - Catch-all for API proxy

### Query Parameters
- `?error=admin_only` - Error message
- `?redirect=/path` - Redirect URL

---

## Navigation

### Programmatic Navigation
```typescript
import { useRouter } from 'next/navigation';

const router = useRouter();
router.push('/path');      // Navigate
router.replace('/path');   // Replace (no history)
router.back();             // Go back
```

### Link Navigation
```typescript
import Link from 'next/link';

<Link href="/chat/new">New Chat</Link>
```

---

## Page Components Structure

### Client Components
All page components are Client Components (`'use client'`) because they:
- Use React hooks
- Handle user interactions
- Access browser APIs
- Manage state

### Server Components
- `layout.tsx` - Can be Server Component
- Static pages (if any)

---

## Page Lifecycle

### Mount
1. Check authentication
2. Load initial data
3. Initialize components
4. Set up event listeners

### Update
1. Re-render on state/prop changes
2. Update data on route change
3. Handle query parameter changes

### Unmount
1. Cleanup event listeners
2. Cancel pending requests
3. Save state if needed

---

## Route Guards

### Authentication Guard
- Checks session via `checkSession()`
- Redirects to `/login` if not authenticated
- Stores redirect URL for post-login redirect

### Admin Guard
- Checks admin email via `isAdminEmail()`
- Redirects to `/login?error=admin_only` if not admin
- Uses `ADMIN_EMAILS` constant

---

## Key Page Files

### Public Pages
- `app/page.tsx` - Home (redirect)
- `app/login/page.tsx` - Login
- `app/chat/shared/[token]/page.tsx` - Shared chat

### Protected Pages
- `app/chat/new/page.tsx` - New chat
- `app/chat/[sessionId]/page.tsx` - Chat session
- `app/chat/others/[sessionId]/page.tsx` - Others' chat
- `app/chats/page.tsx` - All sessions

### Admin Pages
- `app/admin/dashboard/page.tsx` - Dashboard
- `app/admin/analytics/page.tsx` - Analytics
- `app/admin/teams/page.tsx` - Teams
- `app/admin/teams-dashboard/page.tsx` - Team dashboard
- `app/admin/top-questions/page.tsx` - Top questions

### API Routes
- `app/api/proxy/[...path]/route.ts` - API proxy
- `app/api/shared-chat/[token]/route.ts` - Shared chat API

---

**Last Updated:** 2025-01-09  
**Location:** `frontend/src/app/`
