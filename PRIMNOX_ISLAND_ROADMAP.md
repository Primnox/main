# Primnox Dynamic Island — Feature Roadmap

All features brainstormed and planned. Saved 2026-06-07.

---

## ✅ Implemented (Core)
- **Error handler island** — Groq-powered blunt roast + fix chip + copy button
- **Two-stage UAI→SS error monitor** — text-only Stage 1 (60s cooldown) → vision Stage 2 (300s cooldown)
- **Error streak timer** — tracks how long a VS Code error persists, shows `ERR:Xm`
- **Flow state detector** — 25+ min in a focus app → indigo `FLOW:Xm` badge (no camera)
- **Git pulse** — background 30s polling, shows `↑3 ↓1 ✗7` in ambient row
- **Now playing** — Spotify window-title parser, music strip appears below island
- **Productivity heat** — focus-app ratio drives island border amber tint when score < 50
- **Zenith mode** — hold logo 1s OR Ctrl+Shift+Z → full-focus panel, task input + timer
- **Deadline bomb** — Alt+D → set label + minutes → countdown bar with urgency escalation
- **Hotkey chord hints** — hold Ctrl or Alt for 400ms → chord sheet appears below island
- **Parallel task pills** — skill_started/complete events spawn colored pills on island
- **Smart paste** — Ctrl+Shift+P → transforms clipboard via LLM for target app context

---

## Tier 1 (Active Context Layer)

### Context Breadcrumb *(next up)*
**Goal:** Always-visible `VS Code › app.py › def authenticate()` breadcrumb in the idle island.  
**Implementation:**
- UIA data already includes `window_title` and `focused_text`
- Parse VS Code window title: `● filename.py — project — Visual Studio Code`
- Parse focused element for function/class context
- New WS event: `context_update { app, file, symbol }`
- DynamicIsland: show as dim `app › file › symbol` in the ambient row

### Error Streak Timer *(implemented)*
Tracks time of persistent errors. Shows `ERR:14m` in ambient row.
On resolution: backend broadcasts `error_resolved` with duration.

### Git Pulse *(implemented)*
30s background git poll. Shows `↑3 ✗7` in ambient row.
Click → (future) ask Primnox to write a commit message.

---

## Tier 2 (Power User Layer)

### Zenith Mode *(implemented)*
Hold logo 1s or Ctrl+Shift+Z → full-focus panel.
- Editable task label
- Live elapsed timer (h:mm:ss)
- Chord hint: "notifications suppressed"
- Esc to exit

### Hotkey Chord Hints *(implemented)*
Hold Ctrl/Alt for 400ms → hint panel appears below island with current shortcuts.
Auto-hides on key release.

### Parallel Task Pills *(implemented)*
`skill_started` WS event → colored pill with task label.
`skill_complete` → removes oldest pill.
Max 3 pills displayed.

### Smart Paste *(implemented)*
`Ctrl+Shift+P` → reads clipboard → POST `/api/smart_paste` → LLM reformats for target app → writes back to clipboard.
Target context: auto-detected from `read_screen()` window title.

### Multi-Clipboard *(skip — Windows has it natively: Win+V)*

---

## Tier 3 (Deep Intelligence Layer)

### Flow State Detector *(implemented — no camera)*
Track continuous time in focus apps (VS Code, Obsidian, PyCharm, Terminal, etc.).
- 25+ min threshold before firing `flow_state` event
- Updates at 5-min milestones: 25, 30, 35...
- `flow_broken` on app switch away from focus app
- Frontend: live counter from `started_at` timestamp

### Live Primnox Cost Meter
**Goal:** Show token usage after each Primnox response.
**Status:** Partially stubbed in usePrimnox (token counting) — frontend display pending.
**Implementation:**
- Count tokens from WS `token` events in usePrimnox
- After `message` event, set `tokenMetrics {tokens, cost}`
- Show in ambient row for 10s then fade

### Deadline Bomb *(implemented)*
Alt+D → set task label + minutes → armed countdown.
- Green bar → amber (< 5min) → red pulsing (< 1min)
- Dismissed with X or auto-clears at zero

### Ambient Productivity Heat *(implemented)*
Track time ratio: focus apps vs total time (60s window).
- Score >= 80: clean border
- Score < 50: amber border tint
- Backend sends `productivity_score` every 60s

---

## Wildcard Features

### Whisper to Island
**Goal:** Sub-threshold mic activation without click.
**Status:** VAD is disabled in current build. Implement as low-threshold wake mode.
**Implementation:**
- New backend endpoint: `POST /api/whisper/start` (enables 5s high-sensitivity listen)
- Frontend shortcut: `Ctrl+Shift+W` → activates whisper mode briefly
- Island indicator: pulsing dim mic icon

### Now Playing *(implemented)*
Spotify window title parser (`"Artist - Track Name"`).
- Appears as `♪ Artist — Track` strip below ambient row
- Auto-hides when Spotify stops or switches

### Proximity Lock *(skip — requires camera access)*

---

## Future Ideas Backlog

### Focus Buddy
Link with another user's Primnox island. Sync flow state for accountability. Show "buddy: FLOW: 42m" in island.

### Smart Snippets Drawer
Pull frequently used code snippets from history. Ctrl+Shift+S → searchable drawer in island.

### Commit Draft on Click
When Git Pulse badge is clicked, ask Primnox to write a commit message for the staged changes. Auto-copy to clipboard.

### Daily Sprint Tracker
Morning: set 3 goals in island. Track completion. End-of-day summary sent to Primnox memory.

### Spatial Workspace Map
Island shows a tiny heat map of screen zones you've focused on. Detects multitasking exhaustion.

### Voice Macro Palette
Record custom voice triggers for island actions ("commit this", "explain selection").

### Token Cost Sparkline
Show last 10 responses as a mini bar chart of token cost. Helps users track expensive queries.

---

## Architecture Notes

- **AiStatus type**: `'idle' | 'listening' | 'thinking' | 'transcript' | 'copy' | 'error'`
  - Zenith + Deadline are internal DynamicIsland state (not AiStatus) — user-toggled, not backend-driven
- **Ambient row**: appears when any of `flowState | errorStreak | gitPulse` is non-null
- **Now playing row**: independent strip below ambient row
- **Chord hints**: rendered BELOW the island div, not inside it
- **Productivity score**: border tint only, no text — purely ambient signal
- **`islandBorderClass` priority**: zenith > deadline-critical > deadline-warning > listening > error > productivity-tint > default

---

*Last updated: 2026-06-07*
