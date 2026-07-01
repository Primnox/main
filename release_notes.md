# Primnox v0.1.1 Release Notes
**Released: 2026-07-01**

---

## What's New

### 🔒 Privacy Mirror — Reversible PII Scrubbing
Your personal data never leaves your device in plaintext. PII is detected and replaced with stable placeholders (`§FIRSTNAME_1§`) before any cloud request, then rehydrated in the reply so you read real names. Streaming-safe. An in-chat collapsible block shows exactly what was scrubbed per message.

**Quality improvements in this release:**
- NER model now loads in fp32 — no more garbled placeholder output
- `TIME` entity dropped from scrubbing (timestamps aren't PII)
- App-name denylist: "Primnox", "Groq", "Gemini" etc. are never redacted
- Privacy Mirror now **defaults to ON** — privacy-first out of the box
- Startup race fixed: PII model is guaranteed loaded before the first cloud message

### ⚙️ Settings Redesign
The model picker is replaced with a **4-card privacy architecture selector**:
- **Full Cloud** — fastest, all processing in the cloud
- **Privacy Mirror** — cloud speed + on-device PII scrubbing
- **Local + Cloud** — local model for chat, cloud for heavy tasks
- **Full Local** — nothing leaves your machine (requires Ollama / llama.cpp)

### 🧭 Onboarding Overhaul
- Interactive data-flow diagrams in step 2 show what each privacy mode does
- Local LLM setup (Ollama / llama.cpp) built into onboarding
- Voice modes that aren't ready are greyed out with "coming soon"
- UX gaps across steps 3, 8, 11, 13 fixed

### 🎙️ Meeting Transcription & Audio
- Full mic + speaker capture via WASAPI loopback
- Whisper transcription with size-bounded buffers (no more memory growth)
- Shared transcriber instance across sessions
- Dropped unused PortAudio DLLs — smaller Windows installer

### 💾 Backup Import
Restore from a local `.prx` file with your 12-word seed phrase — no cloud provider needed.

### 🛡️ Security & Stability
- Path traversal vulnerability in meeting-delete endpoints patched
- DNS-rebinding host guard added to local API
- Backend port moved `8000 → 4009` to avoid conflicts
- App lifecycle hardened: ports freed on launch, backend process tree killed cleanly on quit

### 🖥️ Electron Fixes
- Transparent frameless window now reliably appears on Windows
- Dev mode no longer kills and respawns the backend
- Title bar version auto-syncs from `package.json`

### 🎨 Branding
- First real Primnox icon — multi-size `.ico` (16–256 px) across exe, taskbar, tray, and NSIS installer

### 📄 Open Source
- MIT License added
- `CONTRIBUTING.md` and `CLA.md` added

### 🧹 Housekeeping
- `chat.db` scrubbed from entire git history
- `chat_sessions.json`, `memory.json` added to `.gitignore`
- `social-automation` module added

---

## Installation
Download `Primnox-Setup-0.1.1.exe` from the [Releases page](https://github.com/Primnox/public/releases/tag/v0.1.1) and run it.

**Minimum requirements:** Windows 10/11 x64, 8 GB RAM (16 GB recommended for local models)
