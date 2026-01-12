# Frontend Architecture Documentation

## Overview

The CloudFuze Chatbot frontend is built with **Next.js 16** (App Router), **React 19**, and **TypeScript**. It uses **Tailwind CSS** for styling and integrates with the FastAPI backend.

**Framework:** Next.js 16 with App Router  
**Language:** TypeScript  
**UI Library:** React 19  
**Styling:** Tailwind CSS 4  
**Package Manager:** npm

---

## Project Structure

```
frontend/
├── src/
│   ├── app/                    # Next.js App Router pages
│   │   ├── admin/              # Admin pages
│   │   ├── chat/               # Chat pages
│   │   ├── login/              # Login page
│   │   ├── api/                # API routes
│   │   ├── layout.tsx          # Root layout
│   │   └── page.tsx             # Home page (redirects)
│   ├── components/             # React components
│   │   ├── ChatInterface.tsx   # Main chat component
│   │   ├── ChatHeader.tsx      # Chat header
│   │   ├── ChatSidebar.tsx     # Session sidebar
│   │   ├── DateRangeFilter.tsx # Date filter
│   │   └── ui/                 # UI components
│   ├── lib/                    # Utility libraries
│   │   ├── api.ts              # API helper functions
│   │   ├── session-utils.ts    # Session utilities
│   │   └── chat-initialization.ts # Chat init
│   ├── types/                  # TypeScript types
│   │   └── chat.ts             # Chat types
│   ├── constants/              # Constants
│   │   ├── admins.ts           # Admin emails
│   │   └── colors.ts           # Color constants
│   └── globals.css             # Global styles
├── public/                     # Static assets
├── package.json                # Dependencies
├── next.config.js              # Next.js config
├── tsconfig.json               # TypeScript config
└── tailwind.config.js          # Tailwind config
```

---

## Key Technologies

### Core Framework
- **Next.js 16** - React framework with App Router
- **React 19** - UI library
- **TypeScript** - Type safety

### Styling
- **Tailwind CSS 4** - Utility-first CSS
- **PostCSS** - CSS processing

### UI Components
- **Radix UI** - Accessible component primitives
- **Recharts** - Chart library for analytics
- **Framer Motion** - Animation library
- **Marked** - Markdown rendering

### API & Data
- **Axios** - HTTP client (if used)
- **Fetch API** - Native fetch for API calls

---

## Architecture Patterns

### 1. App Router (Next.js 16)
- File-based routing
- Server and Client Components
- Route handlers for API

### 2. Client Components
- Marked with `'use client'` directive
- Interactive components
- State management with React hooks

### 3. Server Components (Default)
- No `'use client'` directive
- Rendered on server
- No client-side JavaScript

### 4. API Routes
- Next.js API routes in `app/api/`
- Proxy routes for backend API
- Shared chat API routes

---

## File Locations

### Root Layout
- **`src/app/layout.tsx`**
  - Root HTML structure
  - Metadata configuration
  - Google Tag Manager
  - Structured data (JSON-LD)
  - Global scripts (Marked.js)

### Home Page
- **`src/app/page.tsx`**
  - Redirects to `/chat/new`
  - Loading spinner during redirect

### Configuration Files
- **`next.config.js`** - Next.js configuration
- **`tsconfig.json`** - TypeScript configuration
- **`package.json`** - Dependencies and scripts
- **`tailwind.config.js`** - Tailwind CSS configuration

---

## Routing Structure

### Public Routes
- `/` - Home (redirects to `/chat/new`)
- `/login` - Login page
- `/chat/shared/[token]` - Shared chat (read-only)

### Protected Routes (Require Auth)
- `/chat/new` - New chat
- `/chat/[sessionId]` - Chat with session
- `/chat/others/[sessionId]` - View others' chats
- `/chats` - All sessions list

### Admin Routes (Require Admin)
- `/admin/dashboard` - Analytics dashboard
- `/admin/analytics` - Detailed analytics
- `/admin/teams` - Team leaderboard
- `/admin/teams-dashboard` - Team dashboard
- `/admin/top-questions` - Top questions

---

## State Management

### Local State (React Hooks)
- `useState` - Component state
- `useEffect` - Side effects
- `useCallback` - Memoized callbacks
- `useRef` - Refs for DOM elements

### Session Storage
- `localStorage` - User data, sidebar state
- `sessionStorage` - Session data (if used)

### URL State
- `useRouter` - Next.js router
- `useParams` - Route parameters
- `useSearchParams` - Query parameters

---

## Authentication Flow

1. **User visits protected route** → Check session
2. **Session check** → `checkSession()` from `session-utils.ts`
3. **If no session** → Redirect to `/login`
4. **If session valid** → Load page content
5. **Session stored** → `localStorage` for user info

---

## API Integration

### API Helper
- **`src/lib/api.ts`**
  - `getApiBase()` - Get API base URL (proxy or direct)
  - `apiFetch()` - Centralized fetch with credentials

### API Base URL Logic
- **Development:** `/api/proxy` (Next.js proxy)
- **Production:** `NEXT_PUBLIC_BACKEND_URL` or direct backend URL
- **Credentials:** Always included (`credentials: 'include'`)

### API Routes
- **`app/api/proxy/[...path]/route.ts`** - Proxy route for backend
- **`app/api/shared-chat/[token]/route.ts`** - Shared chat API

---

## Component Architecture

### Page Components
- Located in `app/` directory
- Server or Client Components
- Handle routing and data fetching

### UI Components
- Located in `components/` directory
- Reusable components
- Client Components for interactivity

### Layout Components
- `layout.tsx` - Root layout
- Nested layouts for route groups

---

## Styling Approach

### Tailwind CSS
- Utility-first CSS
- Responsive design with breakpoints
- Custom colors and themes

### Global Styles
- **`src/app/globals.css`** - Global CSS
- Custom CSS variables
- Animation definitions

### Component Styles
- Inline styles for dynamic styles
- Tailwind classes for static styles
- CSS modules (if used)

---

## Build & Deployment

### Development
```bash
npm run dev
# Starts dev server on http://localhost:3000
```

### Production Build
```bash
npm run build
# Creates optimized production build
```

### Start Production
```bash
npm start
# Starts production server
```

---

## Environment Variables

### Required
- `NEXT_PUBLIC_BASE_URL` - Base URL for metadata
- `NEXT_PUBLIC_BACKEND_URL` - Backend API URL (production)
- `NEXT_PUBLIC_API_URL` - Alternative API URL
- `NEXT_PUBLIC_USE_PROXY` - Use Next.js proxy (development)

### Optional
- `NEXT_PUBLIC_GTM_ID` - Google Tag Manager ID

---

## Key Features

1. **Server-Side Rendering (SSR)** - Initial page load
2. **Client-Side Navigation** - Fast page transitions
3. **API Proxy** - Same-origin requests in development
4. **Session Management** - Cookie-based authentication
5. **Responsive Design** - Mobile and desktop support
6. **SEO Optimization** - Metadata and structured data

---

## Performance Optimizations

1. **Code Splitting** - Automatic with Next.js
2. **Image Optimization** - Next.js Image component
3. **Lazy Loading** - Dynamic imports
4. **Static Generation** - Pre-rendered pages where possible
5. **Caching** - API response caching

---

## Security Features

1. **Session Validation** - Cookie-based auth
2. **Admin Protection** - Route-level admin checks
3. **CSRF Protection** - Same-origin requests
4. **XSS Prevention** - React's built-in escaping
5. **Secure Headers** - Next.js security headers

---

**Last Updated:** 2025-01-09  
**Framework:** Next.js 16, React 19, TypeScript
