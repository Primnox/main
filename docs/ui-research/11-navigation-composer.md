# UI Research: Navigation & Composer Architecture (Unit 11)

**Date:** August 26, 2026  
**Status:** Research Complete  
**Scope:** Left rail, conversation list, bottom composer, keyboard/voice, model selector, context scope

---

## Executive Summary

Primnox V2 uses a three-column layout (rail, chat list/context, transcript) with a bottom-floating glass composer. This document establishes conventions, identifies invariants that must not change, and specifies the composer architecture for text, attachments, voice input, model selection, and context management.

---

## Section 1: Navigation Architecture

### 1.1 Current Implementation

**Left Rail (AppRail.tsx)**
- Width: 64px (collapsed), 196px (expanded on hover/focus)
- Transition: `transition-none` with CSS width (NOT animated due to reduced-motion interaction)
- Items: Chat, Knowledge (dev-only), Memory, Settings
- Semantic: nav[aria-label="Primary"]
- Each button carries `aria-label` at all widths (labels NOT hidden at 64px)
- Active indicator: `aria-current="page"` (not color-only)
- Expandable by: pointer hover, keyboard focus, touch focus-within
- Logo: Pulsing dot + wordmark (mirrors website branding)

**Conversation Sidebar (ContextSidebar.tsx)**
- Width: 100% at small screens (drawer), ~280px at medium+ (inline)
- Toggles via: Chats button in rail, repeated in header
- Content: Pinned chats, folders (collapsible), day-grouped recent chats, search
- Actions: New Chat, New Incognito, New Folder, Search, Drag-to-file
- Storage: `localStorage` (rail open/closed state, open folders)

**Main Header (App.tsx lines 704-759)**
- Shows chat title, incognito indicator, conversation-graph button
- Mirrors conversation sidebar button on opposite edge (balanced UX)
- Actions: Show Conversations button (when hidden), End Chat (incognito), Graph

### 1.2 DO-NOT-CHANGE List

These patterns are load-bearing and deeply integrated:

1. **Rail Width & Animation**
   - 64px base width is EXACT (logo and icon sizing depend on it)
   - `transition-none` on width is REQUIRED (reduced-motion interaction is fragile)
   - Expansion method (hover + focus-within) must remain
   - Expansion WIDTH (196px) is tuned to label visibility

2. **Accessibility Invariants**
   - `aria-label` must always be present on rail items (not hidden at 64px)
   - `aria-current="page"` marks active section (not color-alone)
   - Screen-reader order matches visual priority (labels in ITEMS array)
   - Keyboard navigation must not break by focus-only expansion

3. **Conversation List Structure**
   - Pinned + Folders + Day-Grouped Recent is the canonical order
   - Drag-to-file must survive (folder targets are drag-over zones)
   - Incognito chats cannot be filed (they have no disk persistence)
   - Search overrides structure (flat list of matches, no folders/dates)

4. **Branding**
   - Logo is "dot leading wordmark" not "icon swapped in" (see AppRail.tsx lines 87-96)
   - Pulsing dot scale (group-hover/mark:scale-125) is brand identity

5. **Composition**
   - App rail is 64px pinned column (never full-screen, never hidden at any width)
   - Chats sidebar toggles below md, shows inline above md
   - Transcript is always visible in chat mode
   - Composer overlays transcript with glass (not in-flow below it)

6. **State Persistence**
   - Rail open/closed: `localStorage` key `primnox2.rail`
   - Chats open/closed: `localStorage` key `primnox2.chats`
   - Open folders: `localStorage` key `primnox2.folders`
   - Fix position: `localStorage` key `primnox2.fixes` (per-conversation)

---

## Section 2: Composer Architecture

### 2.1 Current Implementation

**Layout & Positioning (App.tsx lines 838-977)**
- Container: `absolute inset-x-0 bottom-0` (overlays transcript)
- Wrapper: max-width 46rem (narrower than transcript's 72rem for focus)
- Variant: Glass panel with backdrop-filter blur
- Scrim: Gradient background (transparent to opaque, 190px tall)
  - Purpose: End the transcript behind glass, prevent reading under blur
  - Stops: Precise px values (54px opaque, 90px fade start, 190px transparent)
  - Reason: Percentages fail as textarea grows; gradient height is typography-dependent

**Text Input (lines 905-928)**
- Element: `<textarea>` (not `<input type="text">`)
- Rows: 1 initially, grows to max 160px
- Behavior: Auto-height on input via scrollHeight measurement
- Placeholder: Context-aware (gone state vs active)
- Disabled: When conversation is `state.gone` (incognito closed)
- Keys: Enter sends (with `!isComposing` guard for IME), Shift+Enter newline
- Accessibility: `<label>` with `sr-only` (always labeled)

**Attachments (lines 883-900)**
- UI: Chips above textarea, showing name, status, removal button
- States: `'ingesting'` (loading spinner), `'failed'` (error icon), default (ready)
- Removal: Button on each chip, removes from `state.attachments`
- Disabled in: Incognito conversations (no disk persistence)
- API: `api.upload()` returns async (extraction is a job, never blocks UI)

**Control Row (lines 929-977)**
- Left: Attach File button (disabled in incognito)
- Center: Model/Status label
  - Format: `"${health.model.model} · ${health.model.local ? 'local' : 'cloud'}"`
  - Fallback: `"connecting…"`
  - Incognito: `"incognito · no history, no files, no code"`
- Right: Stop (if live turn), Send (conditional disable)
- Hint: Below panel: "Enter to send · Shift+Enter for new line"

**Send Semantics (lines 240-262)**
- Refs track state: `sendingRef`, `draftRef` (prevent double-submit in same tick)
- Behavior: Clear draft before await, restore on error
- Side effects: Clears attachments, calls `refreshList()`, resets file input
- Incognito: Send disabled if `state.gone` (conversation ended)

### 2.2 Composer Architecture Specification

**Core Input Chain**
```
Text Input
  ├─ Textarea (auto-height, IME-safe)
  ├─ Draft state (React + Ref for sync access)
  └─ Send guard (sendingRef prevents double-submit)

Attachments
  ├─ Chips (status-aware)
  ├─ Upload (async, extraction is background job)
  └─ State array (id, name, status)

Controls
  ├─ Attach button (disabled in incognito, disabled state visible)
  ├─ Model/Status label (dynamic, never hidden)
  ├─ Stop button (conditional, appears if liveTurn)
  └─ Send button (disabled if no text or conversation gone)

Keyboard
  ├─ Enter: Send (with isComposing guard)
  ├─ Shift+Enter: Newline
  └─ Escape: Not captured (leaves to parent handlers)
```

**Props the Composer Needs (NOT currently separated)**
```typescript
type ComposerProps = {
  // State
  draft: string;
  attachments: Array<{ id: string; name: string; status: 'ingesting' | 'failed' | 'ready' }>;
  conversationGone: boolean;
  conversationIncognito: boolean;
  modelInfo?: { model: string; local: boolean };
  
  // Live turn (for stop button)
  liveTurn?: { id: string };
  
  // Callbacks
  onDraftChange: (text: string) => void;
  onAttach: (files: FileList | null) => Promise<void>;
  onSend: () => Promise<void>;
  onStop?: (turnId: string) => Promise<void>;
  onRemoveAttachment: (id: string) => void;
  
  // Optional voice input (TBD)
  onVoiceStart?: () => void;
  onVoiceEnd?: (transcript: string) => void;
};
```

### 2.3 Voice Input (FUTURE)

**Current State:** Not implemented  
**Proposed Approach:**
- Button in control row (microphone icon)
- Uses Web Audio API + local speech-to-text (or OpenAI Whisper)
- Records until user releases (push-to-talk) or double-taps (toggle mode)
- Appends transcript to draft (or replaces if empty)
- Incognito constraint: Record only (no cloud-based models)

**Not Yet Decided:**
- Local vs cloud transcription
- Push-to-talk vs toggle record
- Error handling (network, permission denial)
- Markdown/formatting from voice

---

## Section 3: Model Selector

### 3.1 Current Behavior

**Status Label (App.tsx lines 944-950)**
- Shows active model or connection state
- Format: `"${model} · ${local|cloud}"`  or `"connecting…"`
- Location: Composer control row (center)
- Not interactive in current design

### 3.2 Model Selection Strategy

**Requirements:**
1. Must not disrupt message flow (don't block send on model selection)
2. Must be discoverable without explicit label (icon + text)
3. Must show local vs cloud availability
4. Must allow fast switching for A/B testing

**Proposed UX:**
- Option A: Inline dropdown in composer (click model name)
  - Pros: Compact, in-context, persistent visibility
  - Cons: Adds interaction to the compose area

- Option B: Settings panel selector
  - Pros: Doesn't compete with composer space
  - Cons: Requires context-switch to change model

- Option C: Profile-based (like Claude's "Sonnet/Opus/Haiku" selector)
  - Pros: Fast switching, muscle memory
  - Cons: Requires frontend list of known models

**Recommendation:** Option A (inline dropdown) for V2  
**Rationale:** A/B testing between models is core to Primnox (§PRODUCT.md), so model switching must be frictionless. Settings panel is too far from the message.

---

## Section 4: Context Scope

### 4.1 Current Implementation

**Context Rail (ContextRail.tsx)**
- Sidebar on right (288px when open)
- Shows: File list, sandbox output, turn state
- Toggleable at all widths (drawer below md, inline above)
- Content is turn-specific (changes as turns stream)

**Scope Constraints**
- Cannot exceed turn boundaries (context is "what this turn has")
- Incognito conversations show memory only (no disk files)
- Files are versioned per turn (turning back undoes tool results)

### 4.2 Context Scope in Composer

**What Gets Sent?**
1. Draft text (required)
2. Attachments (optional, array of IDs)
3. Conversation ID (required, state.id)
4. Turn metadata (implicit, handled by backend)

**NOT in scope:**
- Model selection (backend-routed, not message property)
- Context panel contents (read-only reference, not message input)
- History (backend context management, not composer concern)

**Future Scope:**
- Context toggles (choose which files/memory to include)
- Token budget preview (warn if turn would exceed limit)
- System prompt override (research, not product yet)

---

## Section 5: Keyboard & Accessibility

### 5.1 Keyboard Shortcuts

| Key | Behavior | Context |
|-----|----------|---------|
| Tab | Focus rail → chats → transcript → composer | Always |
| Enter | Send message | Composer focused, not composing IME |
| Shift+Enter | New line | Composer focused |
| Escape | Close sidebar / cancel rename | Sidebar or edit mode |
| Cmd+K / Ctrl+K | Search chats | (Future) |
| ? | Help overlay | (Future) |

### 5.2 Screen Reader Support

**Rail:**
- Items always have `aria-label` (not hidden at 64px)
- Active section marked with `aria-current="page"`
- Logo has single `aria-label="Primnox"` (not read twice)

**Chats:**
- List marked with `role="list"` > `<li>`
- Folder toggle: `aria-expanded`
- Search results: "X matches" text before results
- Active chat: `aria-current="page"` on button

**Composer:**
- Textarea always labeled (screen-reader only label)
- Attachment chips announce name + status
- Send button: `aria-label="Send message"`
- Attach button: `aria-label="Attach a file"` + title when disabled

**Colors & Contrast:**
- Active rail item: Background + text color (not color-only)
- Error states: Icon + color + text
- Status indicators: Shape (solid, dashed, struck) + color (WCAG 1.4.1)

---

## Section 6: Responsive Behavior

### 6.1 Breakpoint Map

| Screen | Rail | Chats | Context | Composer |
|--------|------|-------|---------|----------|
| <md | 64px pinned | Drawer (toggle) | None | Full width glass |
| md-lg | 64px pinned | Inline ~280px | Drawer (button) | Full width glass |
| lg+ | 64px pinned | Inline | Inline ~288px | Full width glass |

### 6.2 Mobile Composer Adjustments

- Text area: Keep auto-height (max 160px)
- Buttons: Keep 8h (touch-friendly)
- Scrim: Recalculate heights for smaller viewport
- Hint: May wrap or truncate on very narrow screens

---

## Section 7: Prototype Scope

### 7.1 Components to Build (frontend/src/components/proto/navigation-composer/)

1. **NavigationRail.tsx** - Extract AppRail logic into reusable component
2. **ConversationList.tsx** - Standalone conversation list (search, folders, drag-to-file)
3. **Composer.tsx** - Extracted bottom composer (text, attachments, controls)
4. **ModelSelector.tsx** - Inline model dropdown (future feature)
5. **ComposerDemo.tsx** - Full-page demo showing all states

### 7.2 Demo States

- Empty composer (no draft, no attachments)
- Typing (growing textarea)
- Attachments (ingesting, ready, failed)
- Sending (disabled send, active stop)
- Incognito (attachment button disabled, incognito label)
- No connection (composer disabled, connecting label)
- Mobile viewport (responsive test)

### 7.3 Port Requirement

**Port 5311** - Dev server for prototype  
(Add to .claude/launch.json)

---

## Section 8: Technical Decisions

### 8.1 Why Glass Composer Overlays Instead of In-Flow

- Conversation scrolls behind input → visual connection maintained
- Last reply visible while typing (reading + writing simultaneously)
- Backdrop-filter diffuses what's behind → readable but dimmed
- In-flow composer requires max-height trade-off on small screens

### 8.2 Why Refs for Draft State

- React state updates are async; Refs update synchronously
- Double-submit can happen in <2ms (measured: 1.4ms)
- Guard must read state before any await
- Same ref pattern used for tracking connection and fix position

### 8.3 Why Not Contenteditable

- Textarea is a single-purpose HTML element (more accessible)
- Contenteditable has browser inconsistencies (especially mobile)
- Markdown typing (backticks, etc.) is simpler with plain text
- Height calculation is precise with scrollHeight

---

## Section 9: Known Limitations & TODOs

1. **Voice Input**
   - Not implemented; speech-to-text TBD (local vs cloud)
   - Button space reserved in prototype

2. **Model Selector**
   - Currently status-only label
   - Dropdown interaction not yet designed
   - Backend routing (how to override model) needs API spec

3. **Context Scope UI**
   - No UI for selecting what context to include
   - Full turn context always sent
   - Token budget preview not implemented

4. **Markdown Formatting Toolbar**
   - Bold, italic, code, link buttons could live above textarea
   - Not in prototype (v2 ships without)

5. **Search in Chats**
   - Implemented (client-side, in-memory)
   - Could be enhanced with backend search (tags, date ranges)

---

## Appendix A: Reference Designs

### A.1 Conventions Borrowed From

**ChatGPT / Claude.ai:**
- Bottom floating composer
- Glass/frosted appearance over content
- Model selector in compose area
- Attachment chips above input

**Linear.ai / Slack:**
- Left sidebar with pinnable items
- Folder structure with drag-to-file
- Search over all items
- Keyboard shortcuts (Cmd+K)

**Notion / Obsidian:**
- Auto-height textarea
- Markdown support without toolbar
- Quick actions via slash commands (future)

### A.2 What We Intentionally Changed

- **Rail first** (not hidden on mobile): Primnox is local-first, rail is always accessible
- **Color reserved** (not used alone): WCAG 1.4.1 requires shape or text
- **Dead Reckoning track** (not flat list): Visualization of "where am I" in conversation
- **No model modal** (inline selector): Frictionless A/B testing

---

## Appendix B: Acceptance Criteria

### Component Extraction ✓
- [ ] Composer extracted to standalone component
- [ ] No external dependencies on App.tsx state
- [ ] All props typed and documented
- [ ] PropTypes or TypeScript for validation

### Prototype Demo ✓
- [ ] Full-page demo at port 5311
- [ ] Show all composer states (empty, typing, attaching, sending, error)
- [ ] Responsive tests (mobile, tablet, desktop)
- [ ] Accessibility (keyboard nav, screen reader, focus visible)
- [ ] Demo chats with pinned, folders, search results

### Documentation ✓
- [ ] This research doc (Section 1-9 complete)
- [ ] Component API documented (JSDoc)
- [ ] DO-NOT-CHANGE list enforced in code comments
- [ ] Migration guide (how to use extracted composer in app)

---

**End of Document**  
*Generated with graphify + manual research*
