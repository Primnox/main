# Changelog

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
