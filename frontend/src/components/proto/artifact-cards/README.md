# Artifact Cards Prototype

A unified card system for displaying context-rich results within conversation turns: execution logs, code snippets, errors, files, and tabular data.

## Overview

The artifact card system provides a progressive disclosure interface where:
- **Metadata is always visible** (status, runtime, file count, size)
- **Details are revealed on expand** (output, code, error traces)
- **Actions are hierarchical** (core → common → advanced)
- **Mobile adapts** (desktop hover menus → mobile bottom sheets)

## Components

### 1. ArtifactCard (Base)
The foundational component that all card types extend. Handles:
- Expandable state management
- Action menu rendering (desktop + mobile)
- Status icon display
- Metadata formatting

**Props:**
```tsx
interface ArtifactCardProps {
  id: string;
  type: 'execution' | 'attachment' | 'code' | 'error' | 'table';
  title: string;
  metadata?: CardMetadata;
  children?: React.ReactNode;
  actions?: CardAction[];
  expanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;
  isMobile?: boolean;
  variant?: 'card' | 'plate';
}
```

### 2. ExecutionCard
Displays tool/script execution results with status, runtime, file changes, and retry action.

**Features:**
- Status indicator (success/error/running)
- Runtime duration
- File changes summary (created/modified/deleted)
- Output log (last 20 lines if truncated)
- Artifact count badge
- Retry and Download Log actions

**Example:**
```tsx
<ExecutionCard
  id="exec-1"
  title="Python (process.py)"
  status="success"
  runtime={2300}
  outputLog={logs}
  fileChanges={{
    created: ['result.json'],
    modified: [],
    deleted: [],
  }}
  onRetry={handleRetry}
/>
```

### 3. CodeCard
Shows code snippets with language detection, syntax highlighting, copy, and download.

**Features:**
- Language badge
- Line count metadata
- Copy to clipboard (with visual feedback)
- Download as file
- Monospace display with overflow scroll

**Example:**
```tsx
<CodeCard
  id="code-1"
  title="fibonacci.py"
  code={pythonCode}
  language="python"
  onCopy={handleCopy}
  onDownload={handleDownload}
/>
```

### 4. ErrorCard
Surface error messages with stack traces, context, and recovery options.

**Features:**
- Error type and message
- Stack trace (collapsible)
- Related context (tool, input, timestamp)
- Retry action
- Copy error button
- Recovery suggestions

**Example:**
```tsx
<ErrorCard
  id="err-1"
  title="API Request Failed"
  errorMessage="Request timed out after 30 seconds"
  errorType="TimeoutError"
  stackTrace={trace}
  context={{ tool: 'fetch-data', input: 'GET /api/users' }}
  onRetry={handleRetry}
/>
```

### 5. TableCard
Display tabular data with export options (CSV, JSON).

**Features:**
- Column headers with sticky behavior
- Row preview (first 50 rows)
- Row and column count metadata
- Export to CSV
- Copy JSON to clipboard
- Horizontal scroll on mobile

**Example:**
```tsx
<TableCard
  id="table-1"
  title="Users"
  headers={['Name', 'Email', 'Status']}
  rows={data}
  onExportCSV={handleCSVExport}
/>
```

## Action Disclosure Matrix

| Action Type | Frequency | Visibility | Examples |
|-------------|-----------|------------|----------|
| **Core** | 80%+ | Always visible | Retry, Expand |
| **Common** | 40–80% | In menu | Download, Copy |
| **Advanced** | 10–40% | Deep in menu | View Details, Export |
| **Expert** | <10% | Hidden menu | Raw logs, Debug info |

## Mobile Behavior

### Desktop
- Hover reveals ellipsis menu
- Action buttons inline in header
- Expand/collapse with arrow button
- Full-width content areas

### Mobile (< 640px)
- Tap header to expand/collapse
- Core actions as full-width button
- Common actions in bottom sheet menu
- Single-column layout
- Truncated metadata (abbreviated numbers)

### Responsive Breakpoints
```
Phone:   375px  → 100% width, action sheet
Tablet:  600px  → 90% width, inline buttons
Desktop: 1200px → Fixed width, hover menu
```

## Status Indicators

Cards display status with icons and colors:
- ✓ **Success** (green) - Operation completed
- ✗ **Error** (red) - Operation failed
- ⟳ **Running** (gray spin) - In progress
- ⚠ **Warning** (orange) - Needs attention
- ∘ **Pending** (gray) - Awaiting action

## Design System Integration

All cards use Primnox's color system:
```
Borders:   border-on-surface/[0.09]
Background: bg-surface-container-lowest
Status:     text-primary (success), text-error, text-warn
Metadata:   text-on-surface/60 (secondary text)
```

## Usage in the App

To integrate artifact cards into the main app:

1. **Import the card types:**
   ```tsx
   import { ExecutionCard, CodeCard, ErrorCard, TableCard } from '@/components/proto/artifact-cards';
   ```

2. **Replace existing blocks:**
   - `ExecutionBlock` → `ExecutionCard`
   - File display → `CodeCard` (if code) or generic attachment
   - Error messages → `ErrorCard`
   - Data results → `TableCard`

3. **Add CSS import:**
   ```tsx
   import '@/components/proto/artifact-cards/artifact-cards.css';
   ```

4. **Handle responsive:**
   ```tsx
   const [isMobile, setIsMobile] = useState(window.innerWidth < 640);
   useEffect(() => {
     const handler = () => setIsMobile(window.innerWidth < 640);
     window.addEventListener('resize', handler);
     return () => window.removeEventListener('resize', handler);
   }, []);

   return <ExecutionCard {...props} isMobile={isMobile} />;
   ```

## Testing the Prototype

### View Showcase
Navigate to `/artifact-cards` to see all card types with sample data.

### Test on Mobile
Use browser DevTools:
1. Open DevTools (F12)
2. Toggle Device Toolbar (Cmd+Shift+M)
3. Select "iPhone 12" or "Pixel 5"
4. Resize to 375px width
5. Observe mobile action sheet layout

### Keyboard Navigation
- **Tab** - Navigate between cards and buttons
- **Enter/Space** - Expand/collapse or trigger action
- **Escape** - Close expanded card (if supported)

## Performance Considerations

- **Lazy loading:** Previews are not fetched until card is expanded
- **Memoization:** Metadata formatting is memoized to avoid re-renders
- **Scroll performance:** Large tables (>1000 rows) show preview only (first 50 rows)
- **CSS containment:** Cards use `overflow: hidden` for rendering optimization

## Accessibility

- Semantic HTML (`<section>`, `<header>`, `<table>`)
- ARIA attributes (`aria-expanded`, `aria-label`)
- Focus management (Tab order preserved)
- Color not sole indicator (icons + text for status)
- Touch targets ≥44px for mobile (WCAG AAA)
- Keyboard navigation support

## Future Enhancements

1. **Syntax highlighting:** Integrate Shiki or Highlight.js for code cards
2. **Table virtualization:** Handle 100k+ rows efficiently
3. **Card versioning:** "Show version history" for documents
4. **Undo/redo:** For destructive actions
5. **Drag and drop:** Rearrange cards in a turn
6. **Keyboard shortcuts:** Cmd+D for download, Cmd+C for copy
7. **Dark mode:** Full CSS variable support for theme switching

## Files

```
artifact-cards/
├── ArtifactCard.tsx       (Base component)
├── ExecutionCard.tsx      (Tool execution results)
├── CodeCard.tsx           (Code snippets)
├── ErrorCard.tsx          (Error messages)
├── TableCard.tsx          (Tabular data)
├── Showcase.tsx           (Demo page)
├── artifact-cards.css     (Styling)
├── index.ts               (Exports)
└── README.md              (This file)
```

## References

- **Research:** `docs/ui-research/05-artifact-cards.md`
- **Framework:** `docs/PROGRESSIVE_DISCLOSURE_FRAMEWORK.md`
- **Design System:** `frontend/tailwind.config.js`
- **Existing:** `frontend/src/components/ExecutionBlock.tsx`, `Attachment.tsx`
