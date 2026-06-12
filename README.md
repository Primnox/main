# Primnox

> A personal AI operating environment for your desktop. Listens, remembers, researches, and acts, without sending your data anywhere it shouldn't go.

**Current Version:** `v0.1.0` | **Windows Beta** | [Download](https://github.com/Cyanexani/primnox_extension/releases)

---

## What is Primnox?

Primnox is a desktop-native AI assistant that runs entirely on your machine. No cloud subscriptions required beyond an optional API key. It integrates with your OS at the system level: reads your screen, monitors your clipboard, captures meetings, manages your calendar, and builds a persistent memory of your work over time.

---

## Features

### 🧠 AI Chat
- Persistent, folder-organised chat sessions with full history.
- Real-time streaming responses.
- Right-click context menu on sessions: Pin, Move to Folder, Auto-assign, Delete.
- Reference any previous conversation as context within a new message.
- Multi-model support — switch between providers in Settings without restarting.

### ⚡ AI Model Routing
Primnox routes inference across multiple providers with automatic fallback — if one fails or rate-limits, the next kicks in seamlessly.

Supported: **Groq**, **OpenAI**, **Anthropic**, **Ollama** (local).

### 🔬 Deep Research
- Multi-round research engine with live streaming output.
- Three depth modes: **Fast**, **Standard**, **Deep**.
- Produces a structured cited report with headings, bullet lists, and source badges.
- Live progress log as it works — stop anytime.

### 📝 Notes
- Rich text editor — full markdown, headings, lists, code blocks.
- Auto-saves continuously.
- Pinning, workspace/folder filtering, full-text search.
- Context panel: word count, read time, table of contents, quick actions.
- Knowledge Graph view — visualise connections between notes.

### 🧩 Memory
- Every conversation and observation can be saved to a persistent memory store.
- Full-text search across all memories.
- Memories older than 7 days are automatically compressed into weekly summaries — key facts preserved, storage kept lean.
- No auto-deletion — you delete memories manually from Data Vault.
- Memory categories: `work`, `personal`, `project`, `session`.

### ✅ Tasks
- Add, complete, and delete tasks from the dashboard or via chat.
- Priority levels: low, normal, urgent.

### ⏰ Reminders
- Set a reminder with a message and a delay — fires as a notification when due.

### 📅 Calendar
- Full calendar: month grid, week strip, day agenda.
- Connects to Google Calendar, Outlook, Apple Calendar, and any CalDAV source.
- Dynamic Island integration — upcoming events surface as ambient strips.

### 🎙️ Meeting Recordings
- Records system audio during meetings.
- Browse recordings by date with transcript and summary preview.
- Manual delete only — nothing disappears until you review it.

### 🏝️ Dynamic Island
A floating always-on-top overlay that surfaces what matters without interrupting your flow:
- AI state, focus duration, Now Playing, productivity score.
- Error detection with AI-generated fix suggestions.
- Background task progress.
- Proactive alerts with quick-action suggestions.
- Minimising the main window transitions Primnox into Island Mode.

### 🛡️ Smart Clipboard
- Monitors clipboard for sensitive data (API keys, passwords, card numbers) and alerts you immediately.
- **Smart Paste**: paste anything → AI rewrites it for the active context → drops the improved version back to your clipboard.

### 📊 Dashboard
- Daily overview: today's events, tasks, reminders, recent meetings, current focus.
- Quick navigation to all major sections.

### ⌨️ Command Palette
- Global `Ctrl+K` palette accessible from anywhere in the app.
- Type naturally to navigate, search, run actions, or ask the AI.

### 🧬 Ambient Intelligence
- **Emotion Engine**: detects your mood from conversation history and adapts its tone accordingly.
- **Learning Profiler**: learns how you communicate and adjusts over time.
- **Flow State Tracker**: detects deep focus and shows how long you've been in it.
- **Error Streak Detector**: notices repeated errors and flags them proactively.

### 🔒 Encrypted Backups
- End-to-end encrypted backups to your storage of choice: S3, Backblaze B2, Cloudflare R2, Google Drive, Dropbox, or self-hosted.
- Protected by a 12-word seed phrase — we cannot decrypt your data even if we wanted to.
- Auto-syncs every 24 hours.

### 🔌 Skills
- Pluggable background skills that run alongside the main AI — shown as strips in the Dynamic Island.
- Drop any `*_skill.py` file into `backend/skills/` and Primnox auto-discovers it on next startup.
- Two base classes: `BaseSkill` for chat/file-triggered skills, `BaseIslandSkill` for Dynamic Island strips.
- Build your own: [github.com/Cyanexani/primox_extension](https://github.com/Cyanexani/primox_extension)

### 🚀 Onboarding
13-step guided setup covering privacy preferences, API key connection, voice settings, workspace creation, and personalisation. Existing users are automatically skipped past it after updates.

### 🔄 Auto-Updater
- Silent background update checks against GitHub Releases.
- Prompts to install when a new version is ready.

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

- [ ] Semantic search across notes and memories
- [ ] Real-time screen understanding
- [ ] Plugin marketplace for community skills
- [ ] macOS / Linux builds
- [ ] Voice wake-word detection
- [ ] Mobile companion app
