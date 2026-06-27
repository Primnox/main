# Primnox — Full Context Snapshot

> Generated 2026-06-26 from memory, codebase inspection, and website review.

---

## What Is Primnox

Primnox is a **privacy-first personal AI OS** for Windows (Electron desktop app). The tagline is *"The AI That Actually Gives A Damn."* It captures the user's digital life locally, scrubs PII on-device, and sends only de-identified context to a cloud AI brain. The trust story is verifiable local code, not server promises.

Website: https://primnox.github.io

---

## Tech Stack

| Layer | Tech |
|---|---|
| Frontend | React + TypeScript, Electron, Vite, Tailwind CSS |
| Backend | Python (FastAPI-style server) |
| Database | SQLite (`chat.db`, `memory.db`) |
| AI Brain | Groq (Llama 3.3 70B → Mixtral 8x7B → Gemma2 9B → Qwen 2.5 32B → Llama 3.1 8B fallback chain) + Gemini (2.0 Flash → 2.0 Flash Lite → 1.5 Flash) |
| Vision | YOLOv8 (`yolov8n.pt`) for screen understanding |
| Backup | AES-256-GCM encrypted `.prx` files to S3-compatible / GDrive / Dropbox / custom HTTPS |

---

## Product Vision

- **Privacy thesis:** Small local model scrubs PII → only de-identified context leaves the device. Cloud is a dumb blob store; the key never leaves the user.
- **Personal OS goal:** Unify calendar + tasks + notes + AI into a single connected system where an event, task, note, and AI assistant all attach to the **same underlying object**.
- **Target user:** Prosumer / regulated-industry professional who can afford frontier AI and genuinely cares about privacy.
- **P2P sync:** Deliberately shelved to `future_scope/sync/`. GitHub is the de-facto sync mechanism for now.

---

## AI Personality

The intended personality is a non-negotiable product differentiator:

- **"Cracked" / characterful** — not bland or corporate.
- **Roasts back** when insulted, then apologizes later — human and friend-like.
- **Does NOT blindly agree.** Pushes back on genuinely harmful life choices. "That one cool guy who does ethical things yet stays cool."
- **Not preachy about small things.** College-kid behavior gets a pass. Ethics are for real-life stakes.
- **Never coercive or manipulative.** Explicit anti-pattern: AI that "blackmails you because you didn't complete a task."
- **Playful + helpful** with social-life questions.
- **Silent memory** — remembers without announcing it.

---

## App Views / Components

| View | Status |
|---|---|
| Chat | Built; markdown rendering fixed |
| Calendar (Week/Day/Agenda/Month) | Fully built |
| Tasks | Built but unreliable — still needs investigation |
| Notes (Notion-like, sub-pages, BlockNote) | Built; linked pages + calendar↔note links pending |
| Memory / Knowledge Graph | Built; node sizing, color by type, hover-highlight, search-to-zoom |
| Meetings / Transcripts | Built |
| Research | Built |
| Dynamic Island overlay | Built; optional toggle pending |
| Settings | Built but lacks depth/customization |
| Onboarding | Built |
| Command Palette (Ctrl+K) | Built — CommandPalette.tsx wired into App.tsx |
| Dashboard | Built but needs visual redesign |

---

## Calendar + Tasks + Notes Design Vision

**3-panel layout:**
- **Left:** mini-calendar, calendar list (Personal/College/Primnox), Tasks (Today/Upcoming/Important), Projects
- **Center:** Day/Week/Month/Agenda/Year + Kanban + Timeline — Google-style drag/resize grid
- **Right:** event details + Notes + AI Actions (Generate Summary / Create Tasks / Reschedule / Draft Follow-Up)

**Key design principles:**
- Notes and Calendar are **two views of one underlying object** — a dated note IS a calendar entry (no sync needed, same record always)
- AI command bar (Ctrl+K) available everywhere for natural-language scheduling
- Tasks surface on the calendar; subtasks, priorities, tags, due dates
- Inspired by: Google Calendar (grid UX), Amie (unified timeline), Notion (notes + databases), TickTick/Todoist (task power), Apple Calendar (travel-time alerts)

---

## Encrypted Backup System

**Format:** `.prx` binary file
```
Offset  Size  Field
0       4     Magic b"PRNX"
4       1     Version 0x01
5       12    GCM nonce (random)
17      N     AES-256-GCM ciphertext (gzip-compressed JSON payload)
```
Payload = `gzip(JSON)` with keys: `version`, `created_at`, `databases {memory.db, chat.db}`, `settings`.

**Key derivation:** PBKDF2-SHA512, salt `b"primnox-backup"`, 600k iterations, from BIP-39 mnemonic.

**Providers:** AWS S3 / Backblaze B2 / Cloudflare R2 / Wasabi / MinIO, Google Drive, Dropbox, custom HTTPS.

**Pending:** Optional encryption (default-ON, opt-out path) — let users start without a mnemonic but default to encrypted; `setup` takes an `encrypted` flag; `.prx` version byte `0x02` = plaintext-gzip. Convert-later action re-encrypts + re-uploads + deletes old copies.

---

## Open Backlog (as of 2026-06-11)

| # | Item | Status |
|---|---|---|
| 1 | Chat markdown rendering | ✅ Fixed |
| 2 | Sidebar open/close janky | ✅ Fixed |
| 3 | Dashboard visual redesign | Open |
| 4 | Calendar views | ✅ Built |
| 5 | Settings — more features/customization | Open |
| 6 | Memory should be silent | Open (behavior) |
| 7 | Error detection scope (code errors only) | Open |
| 8 | Daily-use stickiness / personality | Open |
| 9 | Roast-back personality | Open |
| 10 | Social-life helpfulness | Open |
| 11 | Remove pointless stats ("words Primnox heard") | Open |
| 12 | Knowledge graph UI improvements | ✅ Built |
| 13 | Dynamic Island toggle + Smart Paste broken | Open (Smart Paste is a functional bug) |
| 14 | Notes → Notion-like (linked pages, calendar↔note links) | Partially open |
| 15 | Tasks don't work reliably | Open |

---

## Website (primnox.github.io)

Dark editorial landing page.

| Token | Value |
|---|---|
| Background | `#070707` |
| Text | `#f0ede6` |
| Primary (lavender) | `#c3c0ff` |
| Accent (warm) | `#ffb695` |
| Green | `#34d399` |
| Display font | Syne (800 weight) |
| Body font | DM Sans |
| Mono font | JetBrains Mono |

Features: custom CSS cursor, marquee ticker, full-viewport hero with large uppercase display type, smooth-scroll nav that slims on scroll.

---

## Roadmap (2026-06-26)

### Phase 0 — Foundation (Now – 1 Month)
- `primnox-cli` — accepts text, scrubs PII, routes to local/cloud models
- `primnox-mirror` — standalone data scrubbing API
- `primnox-core` — shared library for context, plugins, settings
- **Metric:** 100 devs clone. CLI runs on a 4GB laptop.

### Phase 1 — User Apps (1 – 3 Months)
- Desktop App (Electron/Tauri): Chat UI, system tray, Ctrl+Space summon
- Android App: voice input, local models (JoyAI), BYOK
- BYOK Integration: paste OpenAI/Anthropic key — Primnox never stores it
- **Metric:** 1,000 downloads. 50 DAU.

### Phase 2 — Primnox OS (3 – 6 Months)
- Bootable Linux ISO (Arch/Debian base, stripped)
- Waydroid integration — Android apps in native windows
- No Google by default — microG + Aurora Store + F-Droid
- 3 Android profiles: Privacy (default), Google (optional), Hardened (GrapheneOS)
- Privacy Mirror daemon — scrubs traffic at kernel level
- **Metric:** 1,000 OS downloads. Runs on 3 laptop models.

### Phase 3 — Ecosystem & Plugins (6 – 9 Months)
- Plugin SDK — APIs for new models, UI components, automations
- Skins Engine — full UI customization via config files
- Plugin Store — one-click install, 70/30 revenue split
- **Metric:** 20 community plugins. 100 skins uploaded.

### Phase 4 — Data Economy & Self-Training (9 – 12 Months)
- Opt-in system — users choose to share scrubbed data
- Synthetic pipeline — scrub → aggregate → generate synthetic datasets
- Payout system — 30–70% cut to users (UPI / crypto)
- Self-training — Primnox trains its "future brain" on synthetic data
- **Metric:** 1,000 opt-in users. First training cycle completed.

### Phase 5 — Hardware & Enterprise (12 – 18 Months)
- Refurbished ThinkPads — wipe, flash Primnox OS, sell on website
- Enterprise license — $100/seat/year
- Hardware partner pitch — Indian brands (Lava, Micromax)
- **Metric:** 100 hardware units. 5 enterprise clients.

### Phase 6 — Physics & Scaling (18 – 24 Months)
- Physics Engine Integration — Genesis/Phantom for video/simulation generation
- Primnox Foundation — non-profit to steward open-source core
- Global distribution — OS in 10 languages
- **Metric:** 100k users. $1M ARR. Self-sustaining.

### The One Rule
**Raw data never reaches Primnox.** User owns the data. Privacy Mirror scrubs at source. Only synthetic/aggregated data used for training. User gets paid.

---

## Honest Assessment of the Roadmap (2026-06-26)

**Phase 0 — do it.** Building `primnox-mirror` as a standalone, benchmarkable, open-source scrubbing library is the right credibility artifact. Forces you to prove the privacy thesis before building anything on top.

**Phase 1 — you're already here.** The Electron app, BYOK, and chat UI exist today. Phase 1 isn't 1-3 months away, it's the current codebase. The gap between now and 1k downloads is a distribution problem, not a build problem. The risk is you built Phase 1 before Phase 0, so the foundation is missing under a working app.

**Phase 2 — company-killer if done too early.** A Linux distro + Waydroid + microG + 3 Android profiles is 2-3 engineers full-time for a year minimum. Canonical and GrapheneOS have been at this for years and still have rough edges. At month 3-6 solo, this will stall and kill Phase 1 momentum while debugging Waydroid GPU passthrough. Needs a co-founder who does only this, or gets pushed past month 12.

**Phase 3 — plugin SDK before 1k DAU is a trap.** Plugin ecosystems only work when developers smell users. At 1k DAU no one builds plugins. Ship this at 10k users minimum.

**Phase 4 — the most defensible moat in the whole roadmap.** The scrub → synthetic → pay-users loop is genuinely novel and no one else is doing it. But it stacks a lot of assumptions: 1k opt-in users, working training pipeline, RBI compliance for UPI payouts, regulatory clarity on crypto. Build this when the user base actually exists.

**Phase 5 — hardware margin on refurbished ThinkPads is brutal.** Inventory, shipping, support tickets about broken hinges will eat engineering time. Enterprise license is fine. Hardware needs an ops co-founder or gets cut.

**Phase 6 — vision slide, not a roadmap item.** Physics engine integration has no clear connection to a privacy-first personal OS. Feels added for ambition rather than user need.

**What to actually do:**
1. Build `primnox-mirror` standalone — this is the credibility artifact that gets devs to trust and clone.
2. Fix the broken things in the existing app (Tasks, Smart Paste, Settings) — can't grow on a leaky bucket.
3. Get to 100 real DAU before writing a line of plugin SDK or OS tooling.
4. Phase 2 either needs a dedicated co-founder or gets replaced with "Primnox runs great on Ubuntu/Arch" for 18 months.
5. The data economy (Phase 4) is the real thesis — consider making it the north star that everything else is built toward, not an afterthought at month 9.

---

## Key Files

| File | Purpose |
|---|---|
| `backend/brain.py` | Core LLM routing, Groq load balancer, adaptive system prompt injection |
| `backend/system_prompts.py` | `MASTER_PROMPT` — the AI personality |
| `backend/backup_manager.py` | BIP-39 mnemonic, PBKDF2 key derivation, AES-256-GCM encrypt/decrypt, scheduler |
| `backend/feed_manager.py` | Feed/context aggregation |
| `frontend/src/app/components/SettingsView.tsx` | Settings UI including Backup tab |
| `frontend/src/app/components/CommandPalette.tsx` | Global Ctrl+K palette |
| `frontend/src/app/components/Layout.tsx` | Sidebar open/close logic |
| `frontend/public/electron.cjs` | Electron main process |
| `website/index.html` | Marketing site |
