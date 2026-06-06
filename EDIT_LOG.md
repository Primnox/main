# Primnox — Edit Log (Archive Summary)

All edits made across the project history, grouped by area.

---

## v0.0.7-alpha Changes (2026-06-06)

### Backend (`backend/`)

| File | What was done |
|---|---|
| `skills/base_skill.py` | **Full rewrite** — typed `SkillContext` / `SkillResult` dataclasses, lifecycle hooks (`before_execute` / `after_execute`), `REQUIRES_PIP` validation, auto-timing, exception wrapping in `run()` |
| `skills/skill_router.py` | **Rewrite** — `_check_pip_deps()` validates deps at load, `discover_skills()` auto-discovers `*_skill.py`, `route_skill()` uses SkillContext, `list_skills()` returns describe() dicts |
| `skills/pdf_skill.py` | Migrated to `execute(ctx: SkillContext) -> SkillResult` pattern; added `REQUIRES_PIP = ["pypdf", "reportlab"]` |
| `skills/ppt_skill.py` | Migrated to new pattern; added `REQUIRES_PIP = ["pptx"]` |
| `skills/code_skill.py` | Migrated to new pattern; `REQUIRES_PIP = []` |
| `skills/screenshot_skill.py` | Migrated to new pattern; `REQUIRES_PIP = ["PIL"]` |
| `skills/transcript_skill.py` | **New** — `TranscriptSkill`: summarizes `.txt/.srt/.vtt` transcripts, extracts action items + key moments via brain |
| `skills/meeting_summary_skill.py` | **New** — `MeetingSummarySkill`: reads latest meeting dir from `~/Documents/Primnox/Meetings/`, returns cached or newly generated summary |
| `skills/daily_brief_skill.py` | **New** — `DailyBriefSkill`: compiles today's meetings + feed history into a synthesized daily debrief |
| `settings_manager.py` | Added two-layer storage: APPDATA (primary) + Windows Credential Manager via `keyring` (backup). API keys are mirrored to keyring on save and restored on load if APPDATA is missing them. Auto-flips `onboarding_completed=True` if groq key is recovered from keyring. Added `ollama_model` / `ollama_base_url` to DEFAULT_SETTINGS |
| `brain.py` | Added `get_ollama_status()` helper (GET `/api/tags`). Added Ollama path in `think()` and `think_stream()` — uses `is_ollama` flag to bypass tool-calling loop, sets `api_key = "ollama"` sentinel to pass truthiness check, handles `ConnectionError` gracefully |
| `server.py` | Added `GET /api/dashboard` (live stats: words heard, meetings, notes, memories, feed, active window), `POST /api/daily_brief` (background task), `GET /api/ollama/status`. Bumped version to `0.0.7-alpha` |

### Frontend (`frontend/`)

| File | What was done |
|---|---|
| `src/app/App.tsx` | Added `ollamaModel`, `setOllamaModel`, `ollamaBaseUrl`, `setOllamaBaseUrl` state; synced from settings; included in `handleSync()`; passed as props to `IslandSettings` |
| `src/app/components/SummaryViews.tsx` | **Rewrote `SummariesExpanded`** as a live dashboard: polls `/api/dashboard` every 30s, shows Words Heard / Meetings / Notes / Memories stat cards, Activity Feed (color-coded), Current Focus card, Recent Meetings list, Daily Brief button, API key warning banner, Quick Nav buttons |
| `src/app/components/ChatView.tsx` | Added chat rename: Pencil/Check icons, `renameState`, `submitRename()` (PUT `/api/chats/:id`), rename button in context menu, rename modal portal with pre-filled input |
| `src/app/components/OnboardingView.tsx` | Removed Groq API key step (Step 3) — total steps 13→12. Updated `Step2Privacy`: fetches `/api/ollama/status` on mount, shows live detection badge on Hybrid card, enables Hybrid card only when Ollama detected, sets `active_model: 'Ollama_Local'` if user picks Hybrid |
| `src/app/components/SettingsView.tsx` | Added Ollama to model dropdown (`Ollama_Local`). Added Ollama config panel (conditionally shown when `activeModel === 'Ollama_Local'`): live status indicator with Wifi icons, detected model list as dropdown, Base URL input, install instructions, note about Groq still needed for transcription |
| `package.json` | Bumped version `0.0.6-alpha` → `0.0.7-alpha`; added `mac` build target: DMG (arm64 + x64) |

### CI / Config

| File | What was done |
|---|---|
| `.github/workflows/build-linux.yml` | Added 8 missing Electron system deps: `libgtk-3-dev`, `libnotify-dev`, `libnss3`, `libxss1`, `libxtst6`, `xauth`, `xvfb`, `libfuse2` |
| `.github/workflows/build-mac.yml` | **New** — macOS DMG build on `macos-14`, arm64 + x64, code signing off by default with instructions for enabling via secrets |

---

## Pre-v0.0.7 History

### Backend (`backend/`)

| File | What was done |
|---|---|
| `server.py` | Added auto-updater endpoint, feedback system, notes CRUD (create/pin/project), DuckDuckGo search integration, SQLite migration fixes, voice ID routes, system scanner routes |
| `brain.py` | Rewrote context assembly logic, added emotion agent calls, profiler integration, memory compression |
| `chat_manager.py` | Session management improvements, streaming fixes |
| `notes_manager.py` | Added custom projects support, note pinning, fixed infinite creation loop by tracking real DB IDs |
| `memory.py` | Added memory compression and trimming logic |
| `settings_manager.py` | Fixed settings.json persistence to APPDATA so settings survive app updates |
| `tools.py` | Replaced Tavily with DuckDuckGo for unlimited web search, removed unused mic tools |
| `emotion_agent.py` | New file — emotion detection agent added in v0.0.6 |
| `profiler.py` | New file — user profiler agent added in v0.0.6 |
| `system_prompts.py` | Updated prompts for emotion/profile awareness |
| `voice_id.py` | Voice identification fixes |
| `settings.json` | Set `onboarding_completed` to false by default |
| `skills/` | Initial skill router, PDF skill, PPT skill, screenshot skill, code skill |

### Frontend (`frontend/`)

| File | What was done |
|---|---|
| `public/electron.cjs` | Added auto-updater (electron-updater), update event logging, dev-update config, Python spawn fix for production |
| `public/preload.js` | Exposed IPC channels for auto-updater |
| `src/app/App.tsx` | Wired up onboarding flow, removed Tavily references |
| `src/app/components/NotesView.tsx` | Full notes UI — pinning, custom projects, BlockNote editor, auto-save race fix, context panel, full-width layout on panel collapse |
| `src/app/components/TitleBar.tsx` | Added feedback button, auto-updater UI (update available / install), cosmetic fixes |
| `src/app/components/ChatView.tsx` | Streaming UI improvements, emotion-aware display |
| `src/app/components/OnboardingView.tsx` | Wired all onboarding steps to real settings state (API key, model, preferences) |
| `src/app/components/SettingsView.tsx` | Minor settings wiring fixes |
| `src/app/components/CommandCenter.tsx` | Layout and shortcut fixes |
| `src/app/components/Layout.tsx` | Removed unused props, layout cleanup |
| `src/app/components/SummaryViews.tsx` | Minor display fixes |
| `src/app/components/DynamicIsland.tsx` | Removed mic/Tavily references |
| `src/app/components/FeedbackModal.tsx` | New file — feedback form modal added in v0.0.4 |
| `src/app/components/NoteGeneratorPanel.tsx` | Minor prop fixes |
| `src/styles/tailwind.css` | BlockNote CSS overrides for Notion-style editor, killed grey background (#1f1f1f), dark theme overrides |
| `src/hooks/usePrimnox.ts` | Added hook utilities for system scanner |
| `package.json` | Bumped versions v0.0.2 → v0.0.6, added electron-updater, set `private: false` for public releases, corrected publish target to `primnox_extension` |
| `dev-app-update.yml` | New file — dev auto-update config for testing updater locally |
| `vite.config.ts` | Set relative base path to fix blank screen in Electron production build |
| `installer.nsh` | NSIS installer script |

### CI / Config

| File | What was done |
|---|---|
| `.github/workflows/build-linux.yml` | Added GitHub Actions workflow to build Linux AppImage |
| `.gitignore` | Initial ignore rules |

### Docs

| File | What was done |
|---|---|
| `CHANGELOG.md` | Maintained across v0.0.2 → v0.0.6-alpha with full feature/fix entries |
| `README.md` | Initial readme |

---

## Shelved (not on main)

| Branch | What's in it |
|---|---|
| `shelved/video-editor` | 15 AI video editing modules, Tech-Noir React frontend, UI Inspector wired to Master Analyzer, Phase 3 decoupling + Phase 4 security hardening (Codex DB patches) |

---

*Updated 2026-06-06 for v0.0.7-alpha manual push.*
