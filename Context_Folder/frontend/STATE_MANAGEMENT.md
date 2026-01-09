# State Management Documentation

## Overview

How state is managed in the CloudFuze Chatbot frontend using React hooks, localStorage, and session storage.

---

## State Management Approaches

### 1. React Hooks (Local State)

#### `useState`
**Purpose:** Component-level state

**Usage:**
```typescript
const [isLoading, setIsLoading] = useState<boolean>(true);
const [user, setUser] = useState<User | null>(null);
const [sessions, setSessions] = useState<ChatSession[]>([]);
```

**Common State:**
- Loading states
- User data
- Session data
- UI state (modals, dropdowns)
- Form inputs

---

#### `useEffect`
**Purpose:** Side effects and lifecycle

**Usage:**
```typescript
// On mount
useEffect(() => {
  // Initialize
}, []);

// On dependency change
useEffect(() => {
  // Update
}, [dependency]);

// Cleanup
useEffect(() => {
  return () => {
    // Cleanup
  };
}, []);
```

**Common Uses:**
- Authentication checks
- Data fetching
- Event listeners
- localStorage sync

---

#### `useCallback`
**Purpose:** Memoized callbacks

**Usage:**
```typescript
const fetchData = useCallback(async () => {
  // Fetch logic
}, [dependencies]);
```

**Common Uses:**
- API calls
- Event handlers
- Callbacks passed to children

---

#### `useRef`
**Purpose:** Refs for DOM elements and values

**Usage:**
```typescript
const inputRef = useRef<HTMLTextAreaElement>(null);
const authCheckRef = useRef<boolean>(false);
```

**Common Uses:**
- DOM element references
- Prevent duplicate calls
- Store mutable values

---

### 2. localStorage (Persistent State)

#### User Data
**Key:** `user`
**Location:** `src/lib/session-utils.ts`

**Stores:**
```typescript
{
  id: string;
  name: string;
  email: string;
}
```

**Functions:**
- `getCurrentUser()` - Get user from localStorage
- `setCurrentUser()` - Save user to localStorage
- `clearUser()` - Remove user from localStorage

---

#### Sessions
**Key:** `chat_sessions_{userId}`
**Location:** `src/lib/session-utils.ts`

**Stores:**
```typescript
ChatSession[] = [
  {
    id: string;
    title: string;
    timestamp: number;
    createdAt: number;
    messages: Message[];
  }
]
```

**Functions:**
- `getAllSessions()` - Get all sessions
- `saveAllSessions()` - Save all sessions
- `getSessionById()` - Get specific session
- `deleteSession()` - Delete session (soft delete)

---

#### Current Session ID
**Key:** `chatbot_session_id_{userId}`
**Location:** `src/lib/session-utils.ts`

**Stores:** Current active session ID

**Functions:**
- `getCurrentSessionId()` - Get current session ID
- `setCurrentSessionId()` - Set current session ID

---

#### Sidebar State
**Key:** `sidebarOpen`
**Location:** Page components

**Stores:** Boolean (sidebar open/closed)

**Usage:**
```typescript
const [isSidebarOpen, setIsSidebarOpen] = useState<boolean>(() => {
  const saved = localStorage.getItem('sidebarOpen');
  return saved !== null ? saved === 'true' : true;
});

useEffect(() => {
  localStorage.setItem('sidebarOpen', String(isSidebarOpen));
}, [isSidebarOpen]);
```

---

#### Section Collapse State
**Key:** `section_collapsed_{sectionId}`
**Location:** `ChatSidebar.tsx`

**Stores:** Boolean (section collapsed/expanded)

**Usage:**
```typescript
const storedCollapsed = localStorage.getItem(`section_collapsed_${sectionId}`);
const isCollapsed = storedCollapsed !== null ? storedCollapsed === 'true' : defaultCollapsed;
```

---

### 3. URL State (Route Parameters)

#### Route Parameters
**Location:** `useParams()` hook

**Usage:**
```typescript
const params = useParams();
const sessionId = params.sessionId as string;
```

**Examples:**
- `/chat/[sessionId]` - sessionId parameter
- `/chat/shared/[token]` - token parameter

---

#### Query Parameters
**Location:** `useSearchParams()` hook

**Usage:**
```typescript
const searchParams = useSearchParams();
const error = searchParams.get('error');
const redirect = searchParams.get('redirect');
```

**Examples:**
- `/login?error=admin_only`
- `/login?redirect=/chat/new`

---

## State Flow Patterns

### Authentication State
```
1. Page loads
2. Check localStorage for user
3. If no user → Check session cookie
4. If no session → Redirect to /login
5. If session valid → Set user state
```

### Session State
```
1. Page loads
2. Get sessionId from URL or localStorage
3. Fetch session from backend
4. Load messages into state
5. Initialize chat interface
```

### Chat State
```
1. User sends message
2. Add to local messages array
3. Send to backend
4. Stream response
5. Update messages array
6. Save to session
```

---

## State Synchronization

### localStorage Sync
```typescript
// Save to localStorage on state change
useEffect(() => {
  localStorage.setItem('key', JSON.stringify(state));
}, [state]);

// Load from localStorage on mount
useState(() => {
  const saved = localStorage.getItem('key');
  return saved ? JSON.parse(saved) : defaultValue;
});
```

### Backend Sync
```typescript
// Fetch from backend
const fetchData = async () => {
  const response = await apiFetch('/endpoint');
  const data = await response.json();
  setState(data);
};

// Save to backend
const saveData = async () => {
  await apiFetch('/endpoint', {
    method: 'POST',
    body: JSON.stringify(state)
  });
};
```

---

## State Management by Feature

### Chat Feature
- **Messages:** `useState<Message[]>([])`
- **Loading:** `useState<boolean>(false)`
- **Streaming:** `useState<boolean>(false)`
- **Session:** `useState<ChatSession | null>(null)`

### Authentication
- **User:** `useState<User | null>(null)` + localStorage
- **Authenticated:** `useState<boolean>(false)`
- **Loading:** `useState<boolean>(true)`

### Sessions
- **Sessions:** `useState<ChatSession[]>([])` + localStorage
- **Current Session:** `useState<ChatSession | null>(null)`
- **Active Session ID:** localStorage

### Analytics
- **User Stats:** `useState<UserStat[]>([])`
- **Date Range:** `useState<DateRange>({startDate: null, endDate: null})`
- **Excluded Users:** `useState<string[]>([])`
- **Loading:** `useState<boolean>(false)`

---

## State Persistence Strategy

### Persistent (localStorage)
- User data
- Sessions
- UI preferences (sidebar, sections)
- Current session ID

### Temporary (Component State)
- Loading states
- Form inputs
- Modal visibility
- Temporary UI state

### Server State (Backend)
- Session messages
- User statistics
- Analytics data
- Shared chats

---

## State Update Patterns

### Direct Update
```typescript
setState(newValue);
```

### Functional Update
```typescript
setState(prev => prev + 1);
```

### Async Update
```typescript
const updateState = async () => {
  const data = await fetchData();
  setState(data);
};
```

### Batch Update
```typescript
setState1(value1);
setState2(value2);
// React batches updates
```

---

## State Management Files

### Core Files
- **`src/lib/session-utils.ts`** - Session state management
- **`src/lib/api.ts`** - API state (fetching, errors)
- **`src/types/chat.ts`** - Type definitions

### Component Files
- Each component manages its own local state
- Props for parent-child communication
- Callbacks for child-to-parent updates

---

## Best Practices

1. **Minimize State:** Only store necessary state
2. **Single Source of Truth:** One place for each piece of state
3. **Derive State:** Calculate derived values, don't store
4. **Lift State Up:** Share state via props
5. **localStorage Sync:** Sync important state to localStorage
6. **Cleanup:** Clean up effects and listeners

---

**Last Updated:** 2025-01-09  
**Location:** `frontend/src/`
