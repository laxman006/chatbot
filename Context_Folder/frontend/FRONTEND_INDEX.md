# Frontend Documentation Index

## Complete Frontend Documentation

This index provides navigation to all frontend-related documentation.

---

## 📚 Documentation Files

### 1. [Frontend Architecture](./FRONTEND_ARCHITECTURE.md)
**Purpose:** Overall frontend architecture and structure

**Contents:**
- Project structure
- Technologies used
- Architecture patterns
- Routing structure
- Build & deployment
- Environment variables

---

### 2. [Components](./COMPONENTS.md)
**Purpose:** All React components documentation

**Contents:**
- Chat components (ChatInterface, ChatHeader, ChatSidebar)
- Analytics components (DateRangeFilter, DeveloperExclusionFilter)
- Session components (SessionCard)
- Utility components (TokenMonitor, UserOnboardingModal)
- UI components (Button, BackgroundPaths)
- Component patterns and lifecycle

---

### 3. [Pages & Routes](./PAGES_ROUTES.md)
**Purpose:** All Next.js pages and routes

**Contents:**
- Public routes (Home, Login, Shared Chat)
- Protected routes (Chat, Sessions)
- Admin routes (Dashboard, Analytics, Teams)
- API routes (Proxy, Shared Chat API)
- Route protection and guards
- Navigation patterns

---

### 4. [State Management](./STATE_MANAGEMENT.md)
**Purpose:** State management patterns and approaches

**Contents:**
- React hooks (useState, useEffect, useCallback, useRef)
- localStorage usage
- URL state (route parameters, query parameters)
- State flow patterns
- State synchronization
- State persistence strategy

---

### 5. [API Integration](./API_INTEGRATION.md)
**Purpose:** Backend API integration

**Contents:**
- API helper functions (getApiBase, apiFetch)
- All API endpoints used
- Authentication in API calls
- Error handling
- Streaming responses (SSE)
- API proxy (development)
- Production API calls

---

### 6. [Styling & UI Framework](./STYLING_UI.md)
**Purpose:** Styling approach and UI framework

**Contents:**
- Tailwind CSS 4
- Global styles
- UI components (Radix UI, Recharts, Framer Motion)
- Design system (colors, typography, spacing)
- Component styles
- Responsive design
- Animation
- Accessibility

---

## 🗂️ Quick Reference

### By File Type

**Pages:**
- `app/page.tsx` - Home (redirect)
- `app/login/page.tsx` - Login
- `app/chat/*` - Chat pages
- `app/admin/*` - Admin pages

**Components:**
- `components/ChatInterface.tsx` - Main chat
- `components/ChatSidebar.tsx` - Sidebar
- `components/ChatHeader.tsx` - Header
- `components/*Filter*.tsx` - Filter components

**Utilities:**
- `lib/api.ts` - API helpers
- `lib/session-utils.ts` - Session utilities
- `lib/chat-initialization.ts` - Chat init

**Types:**
- `types/chat.ts` - TypeScript types

**Constants:**
- `constants/admins.ts` - Admin emails
- `constants/colors.ts` - Color constants

---

## 🔍 Feature-Specific Files

### Chat Feature
- `app/chat/new/page.tsx` - New chat
- `app/chat/[sessionId]/page.tsx` - Chat session
- `components/ChatInterface.tsx` - Chat UI
- `components/ChatHeader.tsx` - Chat header
- `components/ChatSidebar.tsx` - Sidebar

### Authentication
- `app/login/page.tsx` - Login page
- `lib/session-utils.ts` - Session utilities

### Analytics
- `app/admin/dashboard/page.tsx` - Dashboard
- `app/admin/analytics/page.tsx` - Analytics
- `components/DateRangeFilter.tsx` - Date filter
- `components/DeveloperExclusionFilter.tsx` - Exclusion filter

### Teams
- `app/admin/teams/page.tsx` - Team leaderboard
- `app/admin/teams-dashboard/page.tsx` - Team dashboard

---

## 📖 Documentation Structure

```
Context_Folder/frontend/
├── FRONTEND_ARCHITECTURE.md      # Overall architecture
├── COMPONENTS.md                 # All components
├── PAGES_ROUTES.md               # All pages and routes
├── STATE_MANAGEMENT.md           # State management
├── API_INTEGRATION.md            # API integration
├── STYLING_UI.md                 # Styling and UI
└── FRONTEND_INDEX.md             # This file
```

---

## 🎯 Common Tasks

### Add New Component
1. Create component in `src/components/`
2. Add to `COMPONENTS.md`
3. Use TypeScript types from `types/chat.ts`
4. Follow component patterns

### Add New Page
1. Create page in `app/` directory
2. Add route to `PAGES_ROUTES.md`
3. Implement authentication if needed
4. Add navigation links

### Add API Call
1. Use `apiFetch()` from `lib/api.ts`
2. Add endpoint to `API_INTEGRATION.md`
3. Handle errors appropriately
4. Update types if needed

### Style Component
1. Use Tailwind CSS classes first
2. Add custom styles to `globals.css` if needed
3. Follow design system
4. Ensure responsive design

---

## 🔗 Related Documentation

### Backend
- [Backend API Endpoints](../backend/API_ENDPOINTS.md)
- [Authentication](../backend/AUTHENTICATION_CODE.md)

### Features
- [Chat Feature](../features/CHAT_CONVERSATION_FEATURE.md)
- [Analytics Feature](../features/ANALYTICS_FEATURE.md)
- [Team Leaderboard](../features/TEAM_LEADERBOARD_FEATURE.md)

---

**Last Updated:** 2025-01-09  
**Framework:** Next.js 16, React 19, TypeScript
