# Primnox 🌌

> A personal AI operating environment for your desktop. Listens, remembers, researches, and acts — without sending your data anywhere it shouldn't go.

**Current Version:** `v0.1.0`

---

## What is Primnox?

Primnox is a desktop-native AI assistant built on Electron + React (frontend) and Python FastAPI (backend). It runs entirely on your machine — no cloud subscriptions required beyond an optional API key. It integrates with your OS at the system level: reads your screen, monitors your clipboard, captures meetings, manages your calendar, and builds a persistent memory of your work over time.

---

## Feature Overview

### 🧠 AI Chat (Synapse Stream)
- Persistent, folder-organised chat sessions with full history.
- Real-time token streaming via WebSocket.
- Right-click context menu on sessions: Pin, Move to Folder, Auto-assign, Delete.
- Chat referencing: type `#<session_id>` in any message to inject another conversation's history as context.
- Deleting a session also purges its associated memories automatically.
- Multi-model support — switch between providers in Settings without restarting.

### ⚡ AI Model Routing (Brain)
Primnox routes inference across multiple providers with automatic fallback:

| Provider | Models |
|---|---|
| **Groq** | `gpt-oss-120b` → `llama-3.3-70b-versatile` → `qwen3-32b` → `llama3-8b-8192` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | `claude-3-5-sonnet`, `claude-3-haiku` |
| **Ollama** | Any locally-running model (configurable URL) |

If a model fails or rate-limits, the next in the chain is tried automatically.

### 🔬 Deep Research
- Perplexity-style multi-round research engine with live SSE streaming.
- Three depth modes: **Fast** (1 round), **Standard** (2 rounds), **Deep** (3 rounds).
- Pipeline: query planning → parallel DuckDuckGo search + page fetch → gap analysis → follow-up round → LLM synthesis.
- Structured cited report rendered in-app: headings, bold, `[n]` citation badges, bullet lists.
- Live research log streams status as it works — queries issued, pages read, insights found.
- Stop button cancels mid-run.

### 📝 Notes (Neural Nodes)
- Notion-style editor powered by BlockNote — full markdown, headings, lists, code blocks.
- Auto-saves with debounce; prevents cross-file overwrites on rapid tab switching.
- Pinning, workspace/folder filtering, full-text search.
- Collapsible context panel: word count, read time, table of contents, quick actions.
- Knowledge Graph view — visualise connections between notes.
- Export all notes to `Documents/Primnox`.

### 🧩 Memory System
- Every conversation and ambient observation can be committed to a persistent SQLite memory store.
- Full-text search via FTS5 (BM25 ranking) — scales to millions of entries.
- **Compression**: memories older than 7 days are automatically synthesised into weekly LLM-generated summaries. Originals are replaced; key facts are preserved.
- **No auto-deletion** — you delete individual memories manually from Data Vault.
- Memory categories: `work`, `personal`, `project`, `session`.
- "remembered: ..." toast appears when something is stored.

### ✅ Tasks
- Add, complete, and delete tasks from the dashboard inline form or via chat.
- Priority levels: `low`, `normal`, `urgent`.
- Urgent tasks displayed with a red badge.

### ⏰ Reminders
- Set a reminder message + delay in minutes from the dashboard.
- Fires as a toast notification + native OS notification when due.
- Notification permission requested automatically.

### 📅 Calendar
- Full calendar screen: month grid, week strip, day agenda.
- Live "Now" and "in Nm" badges on current/upcoming events.
- Connects to any iCal/CalDAV URL (Google Calendar, Outlook, Apple Calendar, etc.).
- **Dynamic Island integration** — upcoming events surface as ambient strips with urgency colouring.
- Add/remove providers in Settings → Calendar tab.

### 🎙️ Meeting Recordings
- Captures system audio during meetings (WASAPI on Windows).
- **Recordings screen**: browse all meeting folders with date, size, file count, audio/video files, and summary preview.
- Expand any recording to preview its transcript or summary.
- Manual delete with confirm/cancel — nothing auto-deletes until you review it.

### 🏝️ Dynamic Island
A floating, always-on-top desktop overlay (separate Electron window):
- Shows AI state: idle / listening / thinking / speaking.
- Flow state duration (how long you've been focused in one app).
- Now Playing — live track info from your media player.
- Error streak detection with LLM-generated fix suggestions.
- Productivity score.
- Parallel task pills for background skill runs.
- Proactive alerts with quick-action suggestions.
- **Skill strips** — pluggable ambient data rows (e.g. calendar, git pulse).
- Chord hints panel.
- Minimising the main window transitions Primnox into Island Mode.

### 🛡️ Smart Clipboard
- Monitors clipboard for sensitive data (API keys, passwords, card numbers) and alerts via the Dynamic Island.
- **Smart Paste**: paste clipboard content → LLM rewrites it for the active target application → writes transformed text back to clipboard.

### 📊 Dashboard
- Today's date header, daily brief button.
- 5-card stat row: words heard, notes, memories, open tasks, loaded skills.
- 7/5 column grid: activity feed (left) + tasks, reminders, recent meetings (right).
- Current focus (active process + window title).
- Last backup info.
- Quick-nav to Chat, Notes, Archive, Meetings.
- Polls backend every 30s with exponential backoff when unreachable.

### 🗂️ Data Vault (Archive)
- Full list of all stored memories.
- Delete individual memories manually.
- Search across memories.

### 📈 Logs
- Live system log viewer — all backend events, tool calls, skill runs.
- Tail-style auto-scroll.

### ⚙️ Settings
Five tabs:

| Tab | What you configure |
|---|---|
| **System Core** | Active model, Groq / OpenAI / Anthropic / Ollama API keys, Ollama base URL, test connection |
| **Identity** | Operator alias, AI codename, VAD sensitivity, wake word on/off |
| **Security** | Backup/restore, memory compression info, meeting auto-delete retention, "Run Cleanup Now" button |
| **Calendar** | iCal/CalDAV provider URLs, display colours, remove providers |

### 🧬 Ambient Intelligence
- **Emotion Engine**: analyses chat history to detect mood; injects emotion-specific persona into every response (6 variants: happy, sad, angry, anxious, excited, neutral).
- **Learning Profiler**: analyses behaviour to update `onboarding_profile` — vocabulary, communication style, knowledge areas.
- **Flow State Tracker**: detects when you're deep in focus and shows duration in the island.
- **Error Streak Detector**: notices repeated errors in the same tool and flags them.
- **Git Pulse**: live ahead/behind/uncommitted monitoring (island skill).

### 🔌 Skills System
Background Python skills loaded dynamically from `backend/skills/`:
- Skills run in parallel to the main conversation — shown as coloured pills in the island.
- Each skill can call tools, produce files, or surface data as island strips.
- `BaseIslandSkill` interface: `get_island_data()` → fed to the frontend every poll cycle.
- Calendar skill is the first published island skill.

### 🚀 Onboarding
13-step guided setup:
1. Welcome
2. Privacy architecture (Cloud / Hybrid Ollama / Local)
3. API key connection + test
4. Access permissions
5. Voice & interaction mode
6. Environment scan (reads local projects, detects tech stack)
7. User model construction
8. Profile review
9. Memory preferences
10. Personalisation options
11. Workspace creation
12. Assistant generation
13. Completion

All steps persist their choices to settings. Existing users with an API key are automatically skipped past onboarding on first launch after an update.

### 🔄 Auto-Updater
- Integrated with GitHub Releases via `electron-updater`.
- Silent background checks; prompts to install when an update is ready.
- API key intercepted at install time via NSIS scripting and stored in `%APPDATA%\Primnox\.env`.

---

## Architecture

```
Primnox/
├── frontend/          # Electron + React 18 + Vite + TailwindCSS
│   └── src/
│       ├── app/       # Screens, components, hooks
│       └── hooks/     # usePrimnox (WebSocket + state)
└── backend/           # Python 3.11 + FastAPI + SQLite
    ├── server.py      # All API routes + WebSocket hub
    ├── brain.py       # Multi-provider LLM routing
    ├── memory.py      # SQLite FTS5 memory store
    ├── research_engine.py  # Deep research SSE engine
    ├── cleanup_manager.py  # Compression + retention
    ├── chat_manager.py
    ├── notes_manager.py
    └── skills/        # Pluggable background skills
```

**Communication**: WebSocket (`/ws`) for real-time events; REST for data fetches. All fetch calls carry a 5-second abort timeout.

**Database**: SQLite with WAL mode. Tables: `memories` (FTS5), chat sessions, notes, tasks, folders.

**Build**: PyInstaller bundles the backend into a single `.exe`. React compiled with Terser (obfuscated, source maps stripped). Packaged with Electron Builder → NSIS installer.

---

## Development Setup

### Prerequisites
- Node.js 18+ & npm
- Python 3.11
- (Optional) Ollama for local inference

### Run Locally
```bash
# Install frontend dependencies
cd frontend
npm install

# Install backend dependencies
cd ../backend
pip install -r requirements.txt

# Start everything
cd ../frontend
npm run electron:dev
```

### Production Build
```bash
cd frontend
npm run electron:build:full
```
Installer is output to `frontend/dist-electron/`.

---

## Supported AI Providers

| Provider | Free tier | Needs key |
|---|---|---|
| Groq | ✅ Generous free tier | ✅ |
| OpenAI | ❌ | ✅ |
| Anthropic | ❌ | ✅ |
| Ollama (local) | ✅ Fully free | ❌ |

Get a free Groq key at [console.groq.com](https://console.groq.com).

---

## Roadmap

- [ ] Local vector DB (ChromaDB / FAISS) for semantic note search
- [ ] Real-time OCR + visual desktop understanding
- [ ] Plugin marketplace for community skills
- [ ] macOS / Linux builds (`.dmg`, `.AppImage`)
- [ ] Cythonized backend for stronger obfuscation
- [ ] Voice wake-word detection (`hey primnox`)
- [ ] Mobile companion app
