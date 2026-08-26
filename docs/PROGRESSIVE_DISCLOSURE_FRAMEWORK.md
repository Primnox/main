# Progressive Disclosure Framework — Five Levels

## Overview

Progressive disclosure is the practice of revealing interface elements, options, and information in stages rather than all at once. This prevents cognitive overload while keeping power-user features accessible.

Primnox implements a **five-level cascade** where each level balances visibility, clarity, and accessibility:

| Level | Name | Visibility | Trigger | Audience | Examples |
|-------|------|------------|---------|----------|----------|
| **1** | Core | Always visible | – | All users | Chat input, send button, conversation list |
| **2** | Common | Shown by default | – | Most users | Edit/delete actions, quick settings, format options |
| **3** | Advanced | Hidden, 1 click to expand | Click "More" or chevron | Power users | Retry logic, permission overrides, model selection |
| **4** | Expert | Hidden, must search or scroll deep | Settings panel, debug menu | Expert users | Tool inspection, cache debugging, trace logs |
| **5** | Debug | Off by default, env-gated | `PRIMNOX_DEBUG=1` | Developers | Raw event logs, provider calls, timing data |

---

## Disclosure Rules

### Rule 1: Frequency ≥ 80% → Level 1 (Core)

**If a control is used in 80%+ of all sessions**, it lives at Level 1 without a disclosure wrapper.

- **Chat input, send button** — in every session
- **Conversation switcher** — in ~95% of sessions
- **Stop button** (when active) — appears during every multi-turn

**Rationale:** Hiding what users do constantly feels broken. Visibility builds trust.

**Exception:** Stop button is conditionally rendered (hidden while idle), not wrapped in disclosure — it's contextual, not progressive.

---

### Rule 2: Frequency 40–80% → Level 2 (Common)

**If a control appears in 40–80% of sessions**, show it by default but allow quick hiding in preferences.

- **Edit/delete message** — ~70% of power users
- **Retry button** — ~55% (depends on model quality)
- **Copy/bookmark conversation** — ~45%
- **Mood/emotion indicator** — ~50% (when available)

**Disclosure Mechanism:** Inline button or chevron, no popover. Example:

```
┌─ Message ──────────────────────┐
│ Here's your summary.           │
│ [Copy] [Edit] [More ▼]        │
└────────────────────────────────┘
```

The "More" chevron expands to additional actions without leaving the message.

**Rationale:** 50% users need it; 50% don't. Defaulting to shown prevents "feature discovery" complaints. Users who don't need it can hide with a preference toggle.

---

### Rule 3: Frequency 10–40% → Level 3 (Advanced)

**If a control appears in 10–40% of sessions**, hide it behind a single click.

- **Tool execution logs** — ~25% (debugging)
- **Permission approval details** — ~30%
- **Model/provider selection** — ~20% (most use defaults)
- **Advanced formatting (markdown, LaTeX)** — ~15%
- **Workspace/file browser** — ~35%

**Disclosure Mechanism:** "More options" button → card/menu. Example:

```
┌─ Settings ─────────────────────┐
│ Model: Claude 3.5 Sonnet       │
│ [More options ▼]              │
│                                │
│ ┌─ Advanced ──────────────────┐│
│ │ ◇ Tool caching enabled      ││
│ │ ◇ Request ID: perm_xyz123   ││
│ │ ◇ Cache hit ratio: 73%      ││
│ └────────────────────────────┘│
└────────────────────────────────┘
```

On mobile, this becomes a bottom sheet. On desktop, a popover or slide panel.

**Rationale:** Avoids clutter for the 60–90% who don't need it, while keeping it accessible for those who do.

---

### Rule 4: Frequency < 10% → Level 4 (Expert)

**If a control is used in fewer than 10% of sessions**, gate it behind a dedicated panel or deep menu.

- **Raw event logs** — ~5% (debugging specific failures)
- **Token accounting** — ~8% (cost optimization)
- **Replay/restore** — ~3% (recovery from data loss)
- **Multi-model comparison** — ~5%
- **Workspace snapshots** — ~7%

**Disclosure Mechanism:** Settings panel tab or collapsible section. Example:

```
Settings Panel → [General] [Advanced] [Debug]
│
└─ Debug Tab
   ├─ Event Log (enable per-turn tracing)
   ├─ Provider Call Log
   ├─ Token Accounting
   ├─ Workspace Snapshots
   └─ Replay Recorder
```

**Rationale:** These are power-user tools. A dedicated panel keeps them organized and prevents accidental triggering.

---

### Rule 5: Frequency ~0%, Developer-only → Level 5 (Debug)

**If something is only useful during development or troubleshooting**, gate it behind an environment flag.

- Raw database queries (`PRIMNOX_DEBUG_DB=1`)
- Provider API payload inspection (`PRIMNOX_DEBUG_API=1`)
- Full execution timing traces (`PRIMNOX_DEBUG_TIMING=1`)
- Sandbox introspection (`PRIMNOX_DEBUG_SANDBOX=1`)

**Disclosure Mechanism:** Console log output + optional inline badges.

```
PRIMNOX_DEBUG=1 PRIMNOX_DEBUG_API=1 npm run dev

[Provider Call] POST /api/messages
  Model: claude-3-5-sonnet
  Tokens: 1450 (input) + 280 (output)
  Cache write: 622
  Time: 1.8s
  Status: 200
```

**Rationale:** Prevents UI noise for production users. Developers expect to enable debug flags when needed.

---

## Context-Aware Disclosure

### Expertise Level (Inferred)

The app learns a user's expertise over time:

- **Novice** (< 5 conversations): Show only Levels 1–2. Advance to 3 after 10 turns.
- **Intermediate** (5–50 conversations): Show Levels 1–3 by default. Offer Level 4 in settings.
- **Expert** (> 50 conversations, or settings toggled): Show Levels 1–4. Level 5 via env flag.

This is **non-aggressive**: showing a Level 3 control to a novice doesn't break anything, it's just not the default.

### Failure Context

When something fails, disclosure **expands** automatically:

1. User gets a generic error message (Level 1).
2. Click "Details" → shows context (Level 2).
3. Still broken? "Troubleshoot" button → opens log viewer (Level 4).
4. Still stuck? Env flag hint: `PRIMNOX_DEBUG=1 npm run dev` (Level 5).

**Example:**

```
┌─ Error ────────────────────────┐
│ Message failed. Try again.     │
│ [Retry] [Details]              │
└────────────────────────────────┘

[Click Details]

┌─ Error Details ────────────────┐
│ Provider: claude-aerolink      │
│ Error: Rate limit (429)        │
│ Retried: 2/3                   │
│ Next retry in: 4 seconds       │
│ [Open Provider Logs]           │
└────────────────────────────────┘
```

---

## Implementation Checklist

### Level 1 (Core)
- [x] Chat input + send button always visible
- [x] Conversation list always visible
- [x] Stop button (conditional, not hidden)
- [x] Basic message bubble

### Level 2 (Common)
- [ ] Edit/delete action row under messages
- [ ] Copy/bookmark/archive actions
- [ ] Quick settings popover (model, temperature preview)
- [ ] Mood indicator toggle

### Level 3 (Advanced)
- [ ] "More options" expandable on messages
- [ ] Permission approval details card
- [ ] Workspace file browser (collapsible)
- [ ] Advanced formatting toolbar

### Level 4 (Expert)
- [ ] Settings panel with [Advanced] tab
- [ ] Token accounting dashboard
- [ ] Event log viewer
- [ ] Replay/restore tools

### Level 5 (Debug)
- [ ] Provider API inspector (env-gated)
- [ ] Raw database queries (env-gated)
- [ ] Execution timing traces (env-gated)
- [ ] Sandbox introspection (env-gated)

---

## Visual Language for Disclosure

### Chevron / Arrow Icon

Indicates expandable content:
- `▼` (down arrow) = closed/collapsed
- `▲` (up arrow) = open/expanded
- Used on "More", "Advanced", "Details", "Logs"

### "More" Button Style

```tsx
<button className="action-secondary">
  More
  <ChevronDown size={16} />
</button>
```

Styling:
- Desktop: inline button, right-aligned
- Mobile: bottom-sheet trigger
- Hover: subtle background change, no heavy feedback
- Disabled state: 50% opacity, no cursor change

### Disclosure Arrows in Forms

Inline expandable sections:

```
┌─────────────────────────────────┐
│ Permissions ▼                   │
│ ┌───────────────────────────────┤
│ │ ◇ Run Python (allowed)        │
│ │ ◇ Read files (asked once)     │
│ │ ◇ Network (denied)            │
│ └───────────────────────────────┤
└─────────────────────────────────┘
```

---

## Migration Path: V1 → V2

**Current state (V1):** Mixed, inconsistent disclosure.

**Phase 1:** Mark all controls with level metadata.
```tsx
<Button 
  level="2-common" // Meta attribute
  content="Edit"
/>
```

**Phase 2:** Implement Level 2 disclosure (most impact, lowest effort).
- Move 40–80% frequency actions to "More" buttons
- Test with 10 power users

**Phase 3:** Implement Level 3 (advanced expansion).
- Add collapsible sections for infrequent options
- Data: token accounting, permission logs

**Phase 4:** Full framework (Levels 4–5).
- Settings panel refactor
- Debug mode detection

---

## Metrics to Track

To validate the framework, measure:

1. **Discoverability:** % of users who find Level 3+ features
2. **Cognitive Load:** Session duration (should decrease after disclosure)
3. **Frequency Shift:** Track actual usage of each control
4. **Expertise Curve:** How quickly users graduate to higher levels

---

## Examples by Feature

### Chat Message

```
Level 1 (Core):
  [Message bubble text]

Level 2 (Common):
  [Message bubble text]
  [Copy] [Edit] [More ▼]

Level 3 (Advanced, when More clicked):
  [Copy] [Edit] [More ▼]
  ┌─ Advanced ──────────┐
  │ Delete              │
  │ Bookmark            │
  │ Archive             │
  │ Regenerate          │
  └─────────────────────┘
```

### Settings

```
Level 1 (Core):
  [Open Settings ⚙]

Level 2 (Common):
  General Tab:
    - Theme (light/dark)
    - Appearance density
    - Notifications

Level 3 (Advanced):
  [Advanced] Tab:
    - Model selection
    - Tool caching
    - Auto-approve level

Level 4 (Expert):
  [Debug] Tab:
    - Event logging
    - Token accounting
    - Workspace browser

Level 5 (Debug, env-gated):
  Visible only when PRIMNOX_DEBUG=1
```

### Permission Prompt

```
Level 1 (Core):
  [Tool name]
  [Allow] [Deny]

Level 2 (Common):
  [Tool name]
  Brief description of what this does
  [Allow once] [Allow for turn] [Deny]

Level 3 (Advanced, click Details):
  + Arguments (JSON preview)
  + Execution environment
  + Historical run logs
```

---

## Future: Predictive Disclosure

Phase 5+ (not in initial scope):

- Learn user patterns: if user always approves `run_python`, auto-approve on repeat
- Context-aware: if user is editing code, show advanced formatting automatically
- Heuristic: if error, expand disclosure to log level automatically

This requires telemetry collection (do after privacy audit).
