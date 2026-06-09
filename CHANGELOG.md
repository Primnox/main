# Changelog

## v0.0.10 (2026-06-09)

### 🤖 Automation & System Intelligence
- Expanded `backend/automation.py` and `backend/screen_reader.py` for deeper OS-level system control.
- Upgraded `backend/feed_manager.py` to support more granular real-time event routing.
- Added strict AI prompt boundaries and refined `backend/vad_listener.py`.
- Bumped dependencies in `backend/requirements.txt` to support the new automation framework.

### 📅 Calendar
- New **Calendar** screen: month grid, week strip, day agenda with live "Now / in Nm" badges.
- `CalendarIslandSkill` wired into the Dynamic Island — upcoming events surface as ambient strips with urgency colouring.
- Settings → Calendar tab: add iCal/CalDAV providers by URL, set display colour, remove providers.
- Backend: `GET /api/calendar/events?days=N` powered by `icalendar` + `recurring-ical-events`.

### 🔬 Deep Research Engine
- Full Perplexity-style multi-round research with SSE streaming (`POST /api/research/deep`).
- `DeepResearchEngine`: plan → parallel web fetch → gap analysis → second round → optional third round → LLM synthesis.
- Three depth modes: Fast (1 round), Standard (2 rounds), Deep (3 rounds).
- Structured cited report rendered in-app with `##` headings, `**bold**`, `[n]` citation badges, bullet lists.
- Research log panel streams live status — query issued, pages reading, insights extracted.
- Stop button via `AbortController`.

### 🧠 Memory Compression
- Memories older than 7 days are automatically compressed into weekly LLM-generated summaries.
- Grouped by `(category, ISO-week)` — groups of ≥ 2 get synthesised into one dense paragraph; originals are deleted.
- `compressed` column added to the SQLite `memories` table via `ALTER TABLE` migration.
- **No auto-deletion** — memories are only deleted manually from Data Vault.

### 🎙️ Meetings Manager
- New **Recordings** screen: lists all meeting folders with date, size, file count, media files, and summary preview.
- Expand any recording to preview its summary file and audio/video contents.
- Manual delete with inline confirm/cancel — no auto-deletion until you review.
- `GET /api/meetings` and `DELETE /api/meetings/{folder_name}` backend endpoints.

### 🧹 Data Retention / Cleanup
- `cleanup_manager.py` now enforces real retention: compression pass runs before any deletion.
- Meeting auto-delete defaults to `0` (never) — opt-in only.
- `POST /api/cleanup` returns `memories_compressed`, `meetings_deleted`, `tts_deleted`.
- Settings → Security tab: "Data Retention" section explains compression behaviour, exposes meeting auto-delete control, links to Recordings screen.
- Fixed `cleanup_memories` timestamp bug — was comparing Unix floats against ISO strings, never matching.

### 🎨 UI & Font
- Switched from Inter to **Urbanist** (Google Fonts, SIL OFL) — free to publish, cleaner geometric feel.
- Dashboard redesigned: `max-w-5xl` centred layout, 7/5 column grid, redesigned activity feed rows with icon circles.
- Inline quick-add forms for tasks and reminders directly on the dashboard.
- Calendar and Recordings added to sidebar navigation.

### ⚡ Smart Paste — Global Shortcut Overhaul
- `Ctrl+Shift+P` (Windows/Linux) / `Cmd+Shift+P` (Mac) now registered as a **global shortcut** via Electron's `globalShortcut` API — fires from any app, not just when Primnox has focus.
- Smart Paste now works correctly in **Island Mode**: the island window has `focusable: false` (by design), so keyboard listeners inside React could never fire — the global shortcut bypasses this entirely.
- Clipboard is read and written in the Electron main process using `clipboard.readText()` / `clipboard.writeText()` — no browser clipboard permission needed.
- Result IPC event (`smart-paste-result`) triggers toast notification in the renderer via `preload.js`.

### 🐛 Bug Fixes & Reliability
- `socket.onmessage` wrapped in `try/catch` — malformed backend messages no longer kill the WebSocket connection.
- All `fetch()` calls in `usePrimnox` now have `AbortSignal.timeout(5000)` — a hanging backend can't freeze the UI.
- `SummariesExpanded` wrapped in `memo()` — stops the entire dashboard re-rendering on every WebSocket message.
- Dashboard polling uses exponential backoff (30s → 60s → 120s) when the backend is unreachable.
- Task and reminder add buttons now flash ✓ on success or ✗ on failure — no more silent failures.
- `handleSend` in chat restores typed text if the send request fails.
- `auto_assign_chat` now validates the LLM's returned folder ID against real IDs; strips accidental quotes; logs mismatches.
- Removed redundant nested `Array.isArray` check in `fetchNotes`.
- Onboarding Step 6 (`scanEnvironment`) now has `.catch()` — backend errors no longer trap the user at 99%.
- Fixed `cleanup_memories` using Unix float timestamps against ISO string DB column.

## v0.0.9 (2026-06-07)

### 🏝️ Native Dynamic Island
- Re-architected the Electron main process to render a transparent, floating desktop overlay window for ambient data.
- Replaces the standard UI with a "Tech-Noir" HUD displaying active tasks, flow state, and system events.
- Minimizing the main app automatically transitions Primnox into Island Mode.

### 🧬 Ambient Data Tracking
- Tracks "Flow State" duration based on app focus.
- Real-time Git Pulse (ahead/behind/uncommitted) monitoring.
- Tracks coding error streaks and resolutions natively.

### ✨ LLM Smart Paste & Error Handling
- `triggerSmartPaste`: Transform clipboard contents via LLM based on the active target application before pasting.
- `/api/error_explain`: Feed clipboard errors directly to the Dynamic Island for real-time explanations and glowing UI fixes.
- Optimized prompt parsing to gracefully handle markdown code fences in JSON responses.

### 🛠️ UX Improvements
- Removed the Groq API key prompt from the Windows `.exe` installer wizard so users can install freely.

## v0.0.8-alpha (2026-06-06)

### 🎛️ Analytical Dashboard Overhaul
- Completely redesigned the main interface into a sleek, grid-based "Tech-Noir" analytical dashboard.
- Replaced the old scrolling broadcast nodes with dedicated UI widgets: System Vitals, Note Library, Memories tracking, Live Activity Feed, Current Focus, and Recent Meetings.
- Built a new backend endpoint (`/api/system/dash/stats`) that dynamically pulls live metrics from the SQLite database.
- Added a dedicated "Dashboard" tab to the main sidebar navigation.
- Fixed a fatal React import crash caused by a missing icon.

## v0.0.6-alpha (2026-06-04)

### 🧠 Persona Overhaul
- Rewrote `system_prompts.py` — Primnox now responds as a fiercely loyal, sarcastic best friend instead of a generic chatbot.
- 6 emotion-specific prompt variants (happy, sad, angry, anxious, excited, neutral) injected dynamically.

### 🎭 Emotion & Behavior Engine
- New `emotion_agent.py` — analyzes chat history to detect user mood with >70% confidence threshold.
- `brain.py` now calls `get_adaptive_system_prompt()` to inject the detected mood into every response.

### 💬 Chat Context Menu (Right-Click)
- Fully functional right-click context menu on chat sessions: Pin, Move to Folder, Auto-assign, Delete.
- Fixed portal rendering so the menu appears at the cursor position (not offset by parent CSS transforms).
- Pin/Delete/Move actions now call the backend and refresh the session list in real-time.

### 🗑️ Memory Wipe on Delete
- Deleting a chat session now also purges all associated memories from the semantic memory store via `delete_memories_by_session()`.

### 🔗 Chat Referencing (`#session_id`)
- Type `#` followed by a 6-char hex session ID in any message to inject that conversation's history into the system prompt.
- Capped at 20 messages per reference to prevent token overflow.

### 📝 Notion-Style Notes Editor
- Redesigned notes editor to match Notion's centered, full-width layout.
- Full black canvas background — no grey container boxes.
- Responsive padding scales gracefully across screen sizes.
- BlockNote editor background forced transparent for seamless integration.
- Content area dynamically expands to fill the entire horizontal space when the right panel is collapsed.

### 📋 Note Context Panel
- Added a collapsible right-side context details panel displaying properties (date, project, ID, pin state), real-time document stats (word count, character count, lines, read time), an interactive table of contents/outline, and quick action options (Ask AI, Export, Delete).

### 📌 Notes Pinning & Folder Filtering
- Notes can now be pinned (persisted to database).
- Sidebar filters notes by workspace/project dynamically.
- Research view now correctly filters files by folder.

### 📊 Learning Profiler
- New `profiler.py` — reads `settings.json`, prompts the LLM to analyze user behavior, and updates the `onboarding_profile` field.
- Accessible via `/api/profile/analyze` endpoint.

### 🐛 Critical Fixes
- Fixed `sqlite3.Row.get()` crash in `notes_manager.py` that was silently 500'ing every GET `/notes` call.
- Fixed `Ctrl+N` (new page) shortcut — stale React closure prevented it from firing.
- Fixed duplicate "Archive" buttons appearing in the chat sidebar.
- Fixed auto-save race condition: switches between pages now cancel the active debounced auto-save timer and capture the note ID at edit time to prevent cross-file overrides.
- Fixed auto-updater connection issues: updated GitHub publish configuration in `package.json` to `private: false` to allow token-free queries for public release assets.
- Added developer-mode auto-updater configuration (`dev-app-update.yml`) and detailed main-process logging redirecting to `%APPDATA%/Primnox/updater.log`.

### ⌨️ Keyboard Shortcuts
- Added `Ctrl+=` / `Ctrl+-` / `Ctrl+0` zoom controls in Electron (frameless window strips default browser zoom).
- Key matching now case-insensitive (works with CapsLock on).

### 🎨 UI Polish Pass
- Standardized glassmorphism across all panels (`bg-zinc-950/80 backdrop-blur-2xl`).
- Fixed micro-typography scale (bumped `text-[9px]` → `text-[10px]`, reduced extreme tracking).
- Improved custom scrollbar styling.
- Cleaned up all unused TypeScript imports (zero compile errors).

---

## v0.0.5-alpha (2026-06-04)

### 🔍 Unlimited Web Search
- Replaced Tavily (API key required) with **DuckDuckGo** via the `ddgs` library.
- No API key needed. No rate limits. Unlimited searches out of the box.

### 🎙️ Microphone Disconnected
- Removed the microphone toggle from the header bar and Dynamic Island.
- VAD (Voice Activity Detection) listener is fully disabled — Primnox never touches your mic.

### 🛠️ Onboarding Now Actually Works
- All onboarding steps now **persist your choices** to settings instead of being cosmetic placeholders:
  - Permissions (Step 4)
  - Voice & Interaction Mode (Step 5)
  - User Profile Scan (Step 7)
  - Memory Mode (Step 9)
  - Personalization Options (Step 10)
  - Workspace Names (Step 11)

### 🧹 Code Cleanup
- Fixed all TypeScript compilation errors (zero errors).
- Removed unused imports across `App.tsx`, `DynamicIsland.tsx`, `Layout.tsx`, `TitleBar.tsx`.
- Updated Llama model label from "Llama 3" → "Llama 3.3" in Settings UI.

### 🔄 Auto-Updater
- Fixed target repository name (`primox_extension`) for GitHub releases.
- This is the first release that can be delivered via the built-in auto-updater.

---

## v0.0.4-alpha (2026-06-03)

### Initial Release
- Primnox desktop app with Electron + Python backend.
- AI chat with streaming responses (Groq / OpenAI / Anthropic).
- Dynamic Island UI with status indicators.
- Onboarding flow with Groq API key validation.
- Notes editor with BlockNote integration.
- Research view placeholder.
- Meeting recorder (system audio capture via WASAPI).
- Memory system with semantic search.
- Screen reader and vision tools.
- Feedback loop system.
- Auto-updater infrastructure.
