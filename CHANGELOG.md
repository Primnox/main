# Changelog

## v0.0.6-alpha (2026-06-04)

### 📝 Notion-Style Notes Editor
- Redesigned notes editor to match Notion's centered, full-width layout.
- Content column is horizontally centered (max-width 900px) with generous padding.
- Full black canvas background — no grey container boxes.
- Responsive padding scales gracefully across screen sizes.
- BlockNote editor background forced transparent for seamless integration.

### 🐛 Notes System Critical Fix
- Fixed `AttributeError: 'sqlite3.Row' object has no attribute 'get'` crash in `notes_manager.py`.
- This was silently breaking the GET `/notes` endpoint (500 error), which prevented new pages from appearing after creation.

### ⌨️ Keyboard Shortcuts
- Fixed `Ctrl+N` (new page) — was broken due to stale React closure.
- Added `Ctrl+=` / `Ctrl+-` / `Ctrl+0` zoom controls in Electron (frameless window strips default browser zoom).
- Key matching now case-insensitive (works with CapsLock on).

### 🧹 UI Cleanup
- Removed duplicate "View All Archives" link from chat sidebar.
- Cleaned up unused icon imports (`Settings`, `MoreVertical`, `Archive`) from ChatView.
- Removed unused `React` default import from NotesView (uses named imports).

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
