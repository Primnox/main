# Mainstream Assistants UI Patterns — Research & Audit

**Date:** August 2026  
**Scope:** ChatGPT, Google Gemini, Microsoft Copilot, Claude  
**Goal:** Identify standard patterns vs. proprietary bets; audit Primnox against findings.

---

## Executive Summary

All four mainstream assistants follow a remarkably consistent layout template:
- **Left sidebar or rail** for navigation and history
- **Center column** for the conversation transcript
- **Bottom input bar** with text field and submit button
- **Light/dark mode toggle** in top-right or settings
- **Model/feature selector** prominently placed

While the overall structure is uniform, each platform makes **distinct proprietary bets** in:
- Navigation paradigm (sidebar tree vs. flat history)
- Message action patterns (where and how users regenerate, delete, or copy)
- Attachment/file handling
- Settings and preferences location
- Visual accent color and typography

---

## Detailed Findings by Category

### 1. Layout & Navigation Paradigm

#### Standard (All Four)
- **Left navigation panel** (collapsed on mobile)
- **Centered conversation area** with message transcript
- **Bottom input field** anchored to viewport
- **Top bar** with title, settings, and user controls

#### Proprietary Variations

| Platform | Approach | Distinctive Feature |
|---|---|---|
| **ChatGPT** | Sidebar tree navigation | Nested folders, organization by topic; recent chats as flat list |
| **Gemini** | Flat recency list | Simple chronological history; no nesting or folders |
| **Copilot** | Web-integrated (Bing) | Integrated into browser search interface; sidebar is secondary |
| **Claude** (web) | Flat recency + project-scoped | Organized by workspace/project; option to switch context |
| **Primnox** | **Dead Reckoning track metaphor** | Unique: treats conversation as plotted legs, not a list |

**Audit Finding:** Primnox's track metaphor is **proprietary and incompatible** with mainstream expectations. Users expect a chronological list or tree of chats, not a navigation model based on surveying/navigation terminology.

---

### 2. Message Display & Interaction

#### Standard Pattern (All Four)

```
User Message (right-aligned, light background)
└─ [avatar] Message text

Assistant Response (left-aligned, dark/accent background)
└─ [avatar] Message text with streaming animation
    └─ [Actions: Copy | Regenerate | ...]
```

#### Standard Actions on Messages

1. **Copy to clipboard** — Always present
2. **Regenerate/Retry** — Always present (regenerate assistant's last response)
3. **Delete** — Often hidden under menu
4. **React/Emoji feedback** — Upvote/Downvote (ChatGPT, Gemini, Claude)
5. **Share/Export** — Hidden in overflow menu

#### Primnox Current Approach
- Uses `TurnBlock` component showing unified "fix/unconfirm" model
- No standard copy/regenerate actions visible
- "Dead Reckoning" status visualization (dashed/solid/struck indicator)
- Focus on internal state (fix, unconfirmed, refusal) rather than user intent

**Audit Finding:** Primnox does **not surface** regenerate or copy buttons at message level. This is a **major deviation** from every mainstream assistant.

---

### 3. Input Field & Submission

#### Standard Pattern (All Four)

```
[TextField: "Message..."] [Submit/Send Button]
                         └─ Microphone icon (Gemini, Copilot)
                         └─ Model selector inline (ChatGPT, Claude)
```

**Features:**
- Placeholder text ("Ask ChatGPT", "Ask Gemini", etc.)
- Grow-on-focus (textarea expands as user types multi-line)
- Character count or token estimate (Claude shows token count)
- Attach file button (paperclip icon, always visible)
- Enter-to-send vs. Shift+Enter-to-newline toggle
- Stop/Cancel button when generating (replaces Send)

#### Primnox Current Input
- Simple `<textarea>` with placeholder
- Attach button visible
- No token count
- No model selector in input area
- No stop button during generation

**Audit Finding:** Primnox input is **bare-bones but functional**. Missing: token estimate, model selector visibility, stop button prominence.

---

### 4. Attachment & File Handling

#### Standard Pattern

| Behavior | ChatGPT | Gemini | Copilot | Claude |
|---|---|---|---|---|
| File button | Paperclip icon in input | Paperclip icon in input | Paperclip in input | Paperclip in input |
| Visual indicator | Attached file chips above input | File chip under input | File previews | Attachment list |
| Supported types | PDF, images, text, docs | Images, PDFs, text | Images, PDFs, documents | PDFs, images, text, archives |
| Size limits | 20MB per file | Varies by type | 20MB total | 20MB per file |
| Preview | Yes (images) | Yes (images and text) | Yes | Yes |

#### Primnox Current
- Paperclip button visible
- Shows attachment list with status
- No file type restrictions surfaced to UI
- Basic file chip display

**Audit Finding:** Primnox follows standard attachment UX. No gap here.

---

### 5. Model Selection & Feature Toggle

#### Standard Pattern

**ChatGPT:**
- Model selector in input area (dropdown showing "GPT-4o", "GPT-4 Turbo", etc.)
- Locked to model choice per conversation
- Feature toggles in top-right (web search, file upload capability)

**Gemini:**
- Model selector near top-left (Flash, Standard dropdown)
- Feature toggles integrated in top bar (Extensions, Add web search)
- Real-time mode toggle (Think/Research modes)

**Copilot:**
- Tone selector (Creative, Balanced, Precise)
- Format selector (hidden in menu)
- Conversation style baked into chat mode

**Claude (web):**
- Model selector in top bar or input (Claude 3.5 Sonnet, Opus, Haiku)
- Project/context selector (separate from model choice)
- Feature flags in settings sidebar

#### Primnox Current
- Provider selector visible in ContextRail
- Model selection via provider picker
- No "tone" or "style" selector
- Settings in separate panel (not inline)

**Audit Finding:** Primnox separates model selection from input (good for power users, bad for discoverability). Mainstream keeps it **front-and-center** in the input area.

---

### 6. Settings & Preferences

#### Standard Location (All Four)
- Top-right corner: Avatar or gear icon
- Dropdown menu or dedicated panel
- Never a separate modal/page (discouraged)

#### Settings Included

| Category | ChatGPT | Gemini | Copilot | Claude |
|---|---|---|---|---|
| Data & Privacy | Yes | Yes | Yes | Yes |
| Model defaults | Yes | Yes | Yes | Yes |
| Theme (Light/Dark) | Yes | Yes | Yes | Yes |
| Billing & Plan | Yes | Yes | Yes | Yes |
| Export/Backup | Yes (ChatGPT+) | Yes | No | Yes |
| Memory/Personality | Yes (GPTs) | Yes (Gems) | No | Yes |

#### Primnox Current
- SettingsPanel component exists
- Accessed via top-right in TitleBar
- Includes data export, auth, model selection
- No theme toggle (dark-only in design spec)

**Audit Finding:** Primnox settings are **comprehensive but discoverable only to power users**. Mainstream puts theme and common settings in the top-right **menu, not a panel**.

---

### 7. Empty State & First-Run UX

#### Standard Pattern

**ChatGPT:**
- Large centered heading: "What are you working on?" (warm, conversational)
- Suggested prompts below (5-6 cards with examples)
- Brief explanation of capabilities

**Gemini:**
- "Meet Gemini, your personal AI assistant" (headline)
- Suggested prompts as chips
- Call-to-action to "Ask Gemini"

**Copilot:**
- Integrated into Bing search or standalone
- "What can I help you with today?" (query-driven framing)
- Quick action buttons (Create, Draft, Summarize, etc.)

**Claude (web):**
- "Start a new conversation" (minimal)
- Suggested prompts or templates (depends on project)
- Project selector visible

#### Primnox Current
- Blank canvas with "Start a conversation" prompt
- No suggested prompts
- Conversation selector visible on left

**Audit Finding:** Primnox **lacks suggested prompts**, which are a **standard UX pattern** to guide new users and demonstrate capabilities.

---

### 8. Dark/Light Mode & Theming

#### Standard Approach (All Four)
- **Light mode default** for new users
- **Dark mode toggle** in settings or top-bar
- **System preference detection** (prefers-color-scheme media query)
- **Accent color** varies by platform (ChatGPT: green, Gemini: blue, Copilot: blue, Claude: orange)
- **Contrast-conscious** design for both modes

#### Primnox Current
- **Dark-only** by design spec (Tactical Telemetry aesthetic)
- No light mode planned
- Single accent: hazard red
- High contrast verified (WCAG AA)

**Audit Finding:** Primnox's dark-only stance is **deliberately proprietary** and stated in design spec. This is a **brand decision, not a gap**.

---

### 9. Error Handling & Recovery

#### Standard Pattern

| State | ChatGPT | Gemini | Copilot | Claude |
|---|---|---|---|---|
| Rate limit | Modal with count-down | Inline error message | Modal with reason | Inline + top banner |
| Network error | Reconnect button | Retry inline | Retry in message | Retry + continue option |
| Model overloaded | Queue message | "Try again" button | Fallback model offer | Retry with backoff |
| Malformed input | Clear error + suggestion | Minimal error message | Context-aware hint | Expanded error block |

#### Primnox Current
- Shows error in turn (via RecoveryBlock)
- "Regenerate" option on failure
- Error details in CollapsibleBlock
- No proactive rate-limit warnings

**Audit Finding:** Primnox error handling is **functional but sparse**. Mainstream provides **recovery paths and suggestions** inline.

---

### 10. Search & History

#### Standard Behavior

**ChatGPT:**
- Sidebar search filters conversations by title/content
- Search is full-text over all chats
- Pinned conversations at top

**Gemini:**
- Recent chats list (no search)
- Delete conversation actions
- Simple chronological order

**Copilot:**
- Integrated into Bing search context
- No separate chat history (state is ephemeral for some modes)
- New chat always available

**Claude (web):**
- Sidebar search by title or content
- Project/context scoping (search within project)
- Pinned conversations and projects

#### Primnox Current
- Conversation list in AppRail
- No full-text search
- Folder-based organization (proprietary dead reckoning track view)

**Audit Finding:** Primnox **lacks search**, which all mainstream assistants provide. This is a **usability gap** for users with many conversations.

---

## Primnox Audit Against Mainstream Standards

### Gaps (Should Address)

| Gap | Impact | Severity | Remediation |
|---|---|---|---|
| No regenerate button on messages | Users can't easily retry failed responses | **High** | Add [Regenerate] button to message action bar |
| No copy-to-clipboard action | Users must triple-click and Ctrl+C | **High** | Add [Copy] button to every message |
| No suggested prompts (empty state) | New users lack guidance | **Medium** | Add prompt suggestions carousel to empty state |
| No search across conversations | Users can't find old chats | **Medium** | Add search bar to sidebar with fuzzy matching |
| No stop/cancel button visible during generation | Users feel like the app is unresponsive | **Medium** | Show prominently when generation is in progress |
| Model selector not in input area | Requires sidebar navigation | **Low** | Consider inline model picker (optional, power-user) |

### Strengths (Maintain)

| Strength | Why It Works | Action |
|---|---|---|
| Dead Reckoning track metaphor | Unique, honest about uncertainty | Keep; document as proprietary innovation |
| WCAG AA compliance | Better accessibility than competitors | Maintain; verify new components |
| Red hazard accent | Clear signal for errors/warnings | Preserve in new patterns |
| Monospace interface typography | Consistent with "telemetry" aesthetic | Extend to all components |
| No decorative animations | Respects motion preferences; clean UX | Continue across prototypes |

### Proprietary Decisions (Defensible)

1. **Dead Reckoning navigation** — Incompatible with mainstream, but honest and differentiated
2. **Dark-only theme** — Brand decision; Tactical Telemetry aesthetic requires it
3. **Terminal-inspired typography** — Distinctive; requires JetBrains Mono and Syne
4. **No light mode** — Intentional; user research should validate if this is acceptable

---

## Mainstream Pattern Summary: "The Standard UI"

Every assistant converges on this layout:

```
┌─────────────────────────────────────────────────────────┐
│ [Menu] Model Selector [Settings] [User] [Dark Mode]     │
├─────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────────────────────────────────┐   │
│ │          │ │ Conversation Transcript (scrollable)│   │
│ │ Sidebar: │ │                                      │   │
│ │          │ │ User Message (right, light bg)       │   │
│ │ ・ Chat  │ │ Asst Response (left, dark bg)        │   │
│ │   1      │ │ └─ [Copy|Regen|▼]                    │   │
│ │ ・ Chat  │ │                                      │   │
│ │   2      │ │ User Message                         │   │
│ │ ・ New   │ │ Asst Response                        │   │
│ │          │ │ └─ [Copy|Regen|▼]                    │   │
│ │ [+] New  │ │                                      │   │
│ │          │ └──────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────┤
│ [Input Field (grow on focus)] [Send] [Attach] [Mic]     │
└─────────────────────────────────────────────────────────┘
```

---

## Recommendations for Primnox

### Phase 1: Critical Gaps (Do First)

1. **Add message actions**: Copy and Regenerate buttons on every message
2. **Add empty-state prompts**: Suggest 3-5 example queries to new users
3. **Add search**: Fuzzy full-text search over conversations
4. **Visible stop button**: Show [Cancel Generation] when model is streaming

### Phase 2: Quality of Life (Do Next)

5. **Token counter in input**: Show estimated tokens in bottom-right of textarea
6. **Model selector inline**: Optional; add picker to input bar for quick switching
7. **Attachment previews**: Show image thumbnails and file type icons in attachment list
8. **Settings menu in top-bar**: Move settings from panel to hamburger menu (or keep both)

### Phase 3: Polish (Optional)

9. **Voice input**: Add microphone icon (Gemini, Copilot do this)
10. **Export conversation**: Add PDF/Markdown export to message menu
11. **Conversation pinning**: Mark favorite chats in sidebar
12. **Suggested follow-ups**: Show [3-4 suggested next questions] after assistant responds

---

## Design Debt

Primnox's commitment to "Dead Reckoning" and "Tactical Telemetry" creates an **intentional divergence** from mainstream. This is defensible only if:

1. **User research validates** that the track metaphor reduces confusion vs. improves it
2. **Onboarding explicitly teaches** the model (not assumed)
3. **Fallback to standard UX** is available for users who want it

Without these, users will find Primnox confusing.

---

## Conclusion

**Standard patterns exist for a reason**: they solve a common problem in a way millions of users expect. Primnox diverges significantly on:

- Navigation model (track vs. list)
- Message interactions (actions not surfaced)
- Empty state guidance (no prompts)
- Search (not provided)

**Before shipping**, validate with users that Primnox's divergences are intentional and understood, not accidental gaps.

The prototype at `/frontend/src/components/proto/mainstream-assistants/` demonstrates what "standard UI" looks like and how it could be adapted to Primnox's aesthetic (Tactical Telemetry).
