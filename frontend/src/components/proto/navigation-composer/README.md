# Navigation & Composer Components

Extracted, reusable components for Primnox's three-column layout with bottom glass composer.

**Research Document:** `docs/ui-research/11-navigation-composer.md`

## Components

### `Composer.tsx`

Bottom-floating glass composer with text input, attachments, and controls.

**Key Features:**
- Auto-height textarea (grows up to 160px)
- Attachment chips with status (ingesting, failed, ready)
- Model/status label (dynamic, context-aware)
- Stop button for live turns
- Keyboard shortcuts: Enter to send, Shift+Enter for newline
- IME composition guard (safe for Japanese/Chinese input)

**Props:**
```typescript
interface ComposerProps {
  draft: string;
  onDraftChange: (text: string) => void;
  attachments: Attachment[];
  onRemoveAttachment: (id: string) => void;
  onAttachClick: () => void;
  attachmentDisabled?: boolean;
  onSend: () => void | Promise<void>;
  onStop?: (turnId: string) => void;
  conversationGone?: boolean;
  conversationIncognito?: boolean;
  modelInfo?: ModelInfo;
  connectionStatus?: 'connected' | 'connecting' | 'offline';
  liveTurnId?: string;
}
```

**DO-NOT-CHANGE:**
- Absolute positioning (overlays transcript, not in-flow)
- Max-width 46rem (narrower than transcript's 72rem)
- Gradient scrim heights in px (typography-dependent)
- Textarea max-height 160px
- Enter sends with `isComposing` guard for IME

### `NavigationRail.tsx`

Left navigation rail: 64px collapsed, 196px expanded on hover/focus.

**Key Features:**
- 64px base width (exact, logo sizing depends on it)
- Smooth expansion to 196px on hover/focus-within
- Always-present labels (not hidden at 64px, screen-reader safe)
- Active indicator via `aria-current="page"` (not color-only)
- Pulsing dot logo (brand identity)
- Theme toggle and connection status in footer

**Props:**
```typescript
interface NavigationRailProps {
  section: RailSection;
  onSection: (s: RailSection) => void;
  connected: boolean;
  synced: boolean;
  showKnowledge?: boolean;
}
```

**DO-NOT-CHANGE:**
- 64px base width
- `transition-none` on width (reduced-motion interaction is fragile)
- `aria-label` always present
- `aria-current="page"` for active state
- Logo is dot + wordmark (not icon swap)

### `ConversationList.tsx`

Conversation list sidebar with pinning, folders, day grouping, and search.

**Key Features:**
- Pinned conversations at top
- Collapsible folders
- Day-grouped recent chats (Today, Yesterday, Older)
- Client-side search (overrides structure with flat list)
- Inline editing for rename
- Drag-to-file support (future enhancement)

**Props:**
```typescript
interface ConversationListProps {
  conversations: ConversationListItem[];
  folders: Folder[];
  activeId?: string;
  onOpenConversation: (id: string) => void;
  onRenameConversation?: (id: string, newTitle: string) => void;
  onTogglePinned?: (id: string) => void;
  onMoveToFolder?: (id: string, folderId: string | null) => void;
  onDeleteConversation?: (id: string) => void;
  onCreateFolder?: (name: string) => void;
}
```

**Structure:**
1. Pinned conversations (if any)
2. Folders (collapsible, show count of items)
3. Recent/loose chats grouped by day
4. When searching: flat list of matches only

## Demo

### Running the Demo

1. **Option A: Temporary replacement in main**
   ```bash
   # Edit frontend/src/main.tsx
   # Replace: import App from './App'
   # With: import { ComposerDemo } from './components/proto/navigation-composer'
   npm --prefix frontend run dev
   ```
   Then open http://localhost:5273

2. **Option B: Separate build entry**
   ```bash
   # Build with demo entry point
   npm --prefix frontend run build -- --entry demo-composer.html
   ```

3. **Option C: Direct component import**
   ```typescript
   import { ComposerDemo } from '@/components/proto/navigation-composer';
   
   export default function YourPage() {
     return <ComposerDemo />;
   }
   ```

### Demo Features

The `ComposerDemo` component shows:
- Empty composer (default state)
- Typing (with draft text visible)
- Attachments (chips with loading/ready states)
- Incognito mode (buttons disabled, explain why)
- Offline mode (composer disabled, status updated)
- Sending (stop button visible, send button disabled)

Use the buttons at the top of the demo to switch between states.

## Architecture

### Why These Components Are Separate

1. **Decoupling:** App.tsx state management is independent of component structure
2. **Reusability:** Can be used in different contexts (chat, settings, modals, etc.)
3. **Testing:** Easier to test in isolation with full prop control
4. **Documentation:** Props are explicit contracts, not implicit dependencies

### Integration Path

To use extracted components in App.tsx:

```typescript
import { Composer, NavigationRail, ConversationList } from '@/components/proto/navigation-composer';

// In App.tsx:
<NavigationRail
  section={section}
  onSection={setSection}
  connected={state.connected}
  synced={state.synced}
/>

<ConversationList
  conversations={conversations}
  folders={folders}
  activeId={state.id}
  onOpenConversation={openConversation}
  // ... other handlers
/>

<Composer
  draft={draft}
  onDraftChange={setDraft}
  attachments={attachments}
  onRemoveAttachment={(id) => setAttachments(a => a.filter(x => x.id !== id))}
  onAttachClick={() => fileRef.current?.click()}
  onSend={send}
  onStop={(id) => api.cancel(id)}
  conversationGone={state.gone}
  conversationIncognito={state.incognito}
  modelInfo={health?.model}
  liveTurnId={liveTurn?.id}
/>
```

## DO-NOT-CHANGE List

**Rail:**
- 64px base width (exact measurement)
- `transition-none` on width
- `aria-label` always present
- `aria-current="page"` for active
- Logo is dot + wordmark pattern

**Composer:**
- Absolute positioning (overlay, not in-flow)
- Max-width 46rem
- Gradient scrim in px (not %)
- Textarea max-height 160px
- Enter sends with IME guard

**Conversation List:**
- Order: Pinned → Folders → Recent (day-grouped)
- Incognito chats cannot be filed
- Search flattens structure

**Accessibility:**
- Labels always visible (not hidden at small widths)
- Color never alone (paired with shape, text, or icon)
- WCAG 1.4.1 compliance (color-blind, greyscale safe)

## Future Enhancements

1. **Voice Input** - Microphone button in composer
2. **Model Selector** - Inline dropdown to switch models
3. **Context Toggle** - Choose which files/memory to include
4. **Markdown Toolbar** - Bold, italic, code buttons above textarea
5. **Slash Commands** - Quick actions like `/help`, `/settings`
6. **Drag-to-File** - Fully implement folder targeting

## References

- Research: `docs/ui-research/11-navigation-composer.md`
- Current implementation: `src/App.tsx`, `src/components/AppRail.tsx`
- Design tokens: See `src/styles/tailwind.css` for color/spacing system
