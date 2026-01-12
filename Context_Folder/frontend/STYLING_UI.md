# Styling & UI Framework Documentation

## Overview

Styling approach, UI framework, and design system used in the CloudFuze Chatbot frontend.

---

## Styling Technologies

### Tailwind CSS 4
**Purpose:** Utility-first CSS framework

**Configuration:**
- **File:** `tailwind.config.js` or `postcss.config.mjs`
- **Version:** Tailwind CSS 4
- **PostCSS:** `@tailwindcss/postcss`

**Usage:**
```tsx
<div className="flex items-center justify-center p-4 bg-blue-500 text-white">
  Content
</div>
```

---

### Global Styles
**File:** `src/app/globals.css`

**Purpose:** Global CSS, custom styles, animations

**Contents:**
- Tailwind directives (`@tailwind base`, `@tailwind components`, `@tailwind utilities`)
- Custom CSS variables
- Animation definitions
- Component-specific styles

---

## UI Components

### Radix UI
**Purpose:** Accessible component primitives

**Components Used:**
- `@radix-ui/react-slot` - Slot component

**Location:** `src/components/ui/button.tsx`

---

### Recharts
**Purpose:** Chart library for analytics

**Components Used:**
- `PieChart`, `Pie` - Pie charts
- `BarChart`, `Bar` - Bar charts
- `XAxis`, `YAxis` - Axes
- `Tooltip`, `Legend` - Chart elements
- `ResponsiveContainer` - Responsive wrapper

**Usage:**
```tsx
import { PieChart, Pie, Cell } from 'recharts';

<PieChart>
  <Pie data={data}>
    {data.map((entry, index) => (
      <Cell key={index} fill={COLORS[index]} />
    ))}
  </Pie>
</PieChart>
```

**Location:** `src/app/admin/dashboard/page.tsx`

---

### Framer Motion
**Purpose:** Animation library

**Usage:**
- Animations for UI elements
- Page transitions
- Component animations

---

## Design System

### Colors
**Location:** `src/constants/colors.ts` (if exists)

**Primary Colors:**
- Blue: `#0129ac` (CloudFuze blue)
- White: `#ffffff`
- Gray: Various shades

**Chart Colors:**
```typescript
const COLORS = [
  '#3b82f6',  // Blue
  '#8b5cf6',  // Purple
  '#ec4899',  // Pink
  '#f59e0b',  // Orange
  '#10b981',  // Green
  // ... more colors
];
```

---

### Typography
**Font:** System fonts (default)

**Sizes:**
- Headings: Various sizes
- Body: Default size
- Small: `text-sm`

---

### Spacing
**Tailwind Spacing Scale:**
- `p-4` - Padding
- `m-4` - Margin
- `gap-4` - Gap
- `space-y-4` - Vertical spacing

---

## Component Styles

### Chat Interface
**Classes:**
- `.chatgpt-main` - Main container
- `.messages-container` - Messages container
- `.messages-list` - Messages list
- `.chatgpt-textarea` - Input textarea
- `.chatgpt-send-btn` - Send button
- `.empty-state` - Empty state
- `.suggested-questions-container` - Suggested questions

**Location:** `globals.css` and inline styles

---

### Chat Sidebar
**Classes:**
- `.sidebar` - Sidebar container
- `.sidebar-history` - History section
- `.history-item` - Session item
- `.history-section-title` - Section title
- `.section-toggle-btn` - Collapse button

---

### Chat Header
**Classes:**
- `.chat-header` - Header container
- `.chat-header-content` - Header content
- `.read-only-badge` - Read-only badge
- `.header-actions` - Action buttons
- `.header-btn` - Header button

---

### Analytics Dashboard
**Classes:**
- `.dashboard` - Dashboard container
- `.stats-grid` - Statistics grid
- `.chart-container` - Chart wrapper

**Charts:**
- Recharts components
- Custom colors
- Responsive design

---

## Responsive Design

### Breakpoints (Tailwind)
- `sm:` - 640px
- `md:` - 768px
- `lg:` - 1024px
- `xl:` - 1280px
- `2xl:` - 1536px

### Mobile-First
- Base styles for mobile
- Breakpoints for larger screens

**Example:**
```tsx
<div className="flex flex-col md:flex-row">
  {/* Mobile: column, Desktop: row */}
</div>
```

---

## Animation

### CSS Animations
**Location:** `globals.css` or inline styles

**Spinner Animation:**
```css
@keyframes spin {
  0% { transform: rotate(0deg); }
  100% { transform: rotate(360deg); }
}
```

**Usage:**
```tsx
<div style={{ animation: 'spin 1s linear infinite' }}></div>
```

---

### Framer Motion
**Purpose:** Advanced animations

**Usage:**
- Page transitions
- Component animations
- Hover effects

---

## Custom Styles

### Inline Styles
**Usage:** Dynamic styles, conditional styling

**Example:**
```tsx
<div style={{
  display: 'flex',
  alignItems: 'center',
  backgroundColor: isActive ? 'blue' : 'gray'
}}>
```

---

### CSS Classes
**Location:** `globals.css`

**Custom Classes:**
- Component-specific classes
- Utility classes
- Animation classes

---

## UI Patterns

### Buttons
**Styles:**
- Primary button
- Secondary button
- Icon button
- Text button

**States:**
- Default
- Hover
- Active
- Disabled
- Loading

---

### Modals
**Styles:**
- Overlay (backdrop)
- Modal container
- Header
- Content
- Footer
- Close button

**Classes:**
- `.modal-overlay`
- `.modal`
- `.modal-header`
- `.modal-content`
- `.modal-close`

---

### Forms
**Styles:**
- Input fields
- Textareas
- Select dropdowns
- Checkboxes
- Radio buttons

**States:**
- Default
- Focus
- Error
- Disabled

---

## Accessibility

### ARIA Attributes
- `aria-label` - Labels
- `aria-expanded` - Expandable elements
- `aria-hidden` - Hidden elements
- `role` - Element roles

### Keyboard Navigation
- Tab order
- Enter/Space for buttons
- Escape to close modals

### Focus Management
- Focus indicators
- Focus trap in modals
- Focus restoration

---

## Theme Configuration

### Tailwind Config
**File:** `tailwind.config.js` or `postcss.config.mjs`

**Customization:**
- Colors
- Fonts
- Spacing
- Breakpoints
- Plugins

---

## Styling Files

### Core Styles
- **`src/app/globals.css`** - Global styles
- **`tailwind.config.js`** - Tailwind configuration
- **`postcss.config.mjs`** - PostCSS configuration

### Component Styles
- Inline styles in components
- Tailwind classes
- CSS modules (if used)

---

## Best Practices

1. **Use Tailwind First** - Prefer Tailwind utilities
2. **Custom CSS When Needed** - Use custom CSS for complex styles
3. **Responsive Design** - Mobile-first approach
4. **Consistent Spacing** - Use Tailwind spacing scale
5. **Color System** - Use defined color constants
6. **Accessibility** - Include ARIA attributes
7. **Performance** - Minimize custom CSS

---

**Last Updated:** 2025-01-09  
**Framework:** Tailwind CSS 4, React 19, Next.js 16
