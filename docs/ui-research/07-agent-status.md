# Unit 7: Agent Status UI — Transparency vs Cognitive Overload

**Status:** Research & Design Phase  
**Date:** 2026-08-26  
**Objective:** Resolve the transparency vs cognitive overload trade-off in agent status display through a 3-level information hierarchy.

---

## Executive Summary

Primnox currently distributes agent status information across four separate UI locations:
- **LiveStatus** (in TurnBlock) — simple spinner + elapsed time
- **ThinkingBlock** (collapsible) — model reasoning/thinking content
- **ContextRail** (sidebar panel) — progress steps, files, context metrics, stream status
- **MissionControl** (provider settings panel) — routing, telemetry, provider health

This fragmentation creates two problems:
1. **Information Overload:** ContextRail presents 15+ data points at once, overwhelming users during brief operations
2. **Hidden Details:** Critical diagnostics (sandbox state, cursor sync, open circuits) are buried in a sidebar that users may never discover

**Solution:** A 3-level hierarchy that surfaces only what's necessary at each level, allowing users to progressively deepen their understanding without ever seeing irrelevant noise.

---

## Current Landscape Analysis

### 1. LiveStatus (TurnBlock.tsx, lines 35-48)
**Purpose:** Real-time execution feedback  
**Shows:** Status + elapsed time  
**Interaction:** Read-only, always visible during execution  
**UX Pattern:** Polling with animated spinner  
**Problem:** Minimal information makes it impossible to diagnose hangs or provider failures

### 2. ThinkingBlock (ThinkingBlock.tsx)
**Purpose:** Model reasoning transparency  
**Shows:** Extended thinking content from supported models  
**Interaction:** Collapsible, collapsed by default  
**UX Pattern:** Progressive disclosure  
**Problem:** Only present for reasoning models; users on non-reasoning models get no transparency

### 3. ContextRail (ContextRail.tsx, lines 55-162)
**Purpose:** Multi-panel diagnostics dashboard  
**Shows:**
- Progress steps (4-step state machine)
- Generated files + workspaces
- Model/provider info
- Sandbox isolation status
- Privacy warnings
- Stream cursor/socket/sync status

**Interaction:** Always-open sidebar, manually closeable  
**UX Pattern:** Exhaustive transparency  
**Problem:** All 15+ data points present simultaneously; cognitive overload on quick operations

### 4. MissionControl (MissionControl.tsx)
**Purpose:** Session-level health & routing  
**Shows:**
- Provider counts (loaded, available)
- Telemetry (turns today, success rate, active mode)
- Route map with live breathing animation
- Session stats (first token latency, failed turns, benched providers)
- Connection test harness with live logging

**Interaction:** Persistent panel in Settings, requires navigation  
**UX Pattern:** Strategic overview with drill-in diagnostics  
**Problem:** Critical health info (benched providers, success rate) is only visible in Settings

---

## The Transparency vs Cognitive Overload Trade-off

### The Problem
- **Too transparent:** ContextRail's full-throttle display creates noise during normal operation. Users see 100 data points and can't identify what matters.
- **Too hidden:** Critical warnings (sandbox disabled, privacy scrubbing off, circuit breaker triggered) only appear in deep UI locations that users rarely visit.
- **Inconsistent surfacing:** Identical information appears in multiple places with different levels of detail, creating confusion about which is authoritative.

### Why Users Need Both
1. **Quick operations** (2-3 second turns): Status alone is sufficient. The spinner + elapsed time answer "is it working?"
2. **Slow operations** (10+ seconds): Users want to know *why*. Progress steps and current state matter.
3. **Failures:** Detailed diagnostics (which provider failed, error code, sandbox status) are critical for recovery.
4. **Deep inspection:** Performance analysis, routing decisions, and token accounting belong in a dedicated diagnostic view.

---

## Proposed 3-Level Hierarchy

### Level 1: Glance (0-1 second cognitive load)
**When:** Always visible, persistent  
**Shows:**
- Status word (with `aria-live` announcement on change)
- Elapsed timer
- Single dot indicator (working/idle)

**Why this level:** Answers "is it running?" immediately, without distraction.  
**Example:** `Working · 3.2s`

**Cognitive Load:** 1 data point (status word) + 1 metric (elapsed)  
**Interaction:** Passive, no clicks

---

### Level 2: Expand (5-15 seconds cognitive load)
**When:** Triggered by user click or auto-opened on slow operations (>2s elapsed)  
**Shows:**
- Progress steps (building context → thinking → streaming)
- Current step highlighted + next step shown
- File downloads (if any generated)
- Single most-critical warning (sandbox disabled, or privacy-scrub status)

**Why this level:** Gives context without overwhelm. Progressive disclosure pattern.  
**Example:**
```
Working · 7.2s
├─ queued ✓
├─ building_context ✓
├─ thinking (●)
├─ streaming ○
Generated: style.css (2.5K)
⚠ Sandbox: NONE — code runs unisolated
```

**Cognitive Load:** ~7 data points, but grouped and sequenced  
**Interaction:** One click to expand, esc/click to collapse

---

### Level 3: Deep Inspect (30+ seconds, active debugging)
**When:** User navigates to Diagnostics panel, or deep-linked  
**Shows:**
- Full progress state machine with timings per step
- Complete file list with versions
- Detailed provider chain (which provider attempted, why it was skipped, fallback order)
- Sandbox isolation mode + security posture
- Stream statistics (cursor position, socket state, resync events)
- Telemetry (latency, success rate, open circuits, local models loaded)
- Reasoning/thinking block (full text)
- Privacy scrub mirror (what was replaced)

**Why this level:** Complete transparency for users who need to understand system behavior.  
**Cognitive Load:** 50+ data points, heavily structured  
**Interaction:** Tabbed/sectioned view, searchable

---

## Design Principles

1. **Earn the expansion:** Level 1 surfaces only if it's currently true. No empty states.
2. **Context-aware defaults:** Level 2 auto-opens for operations >2s. Users don't have to remember to click.
3. **Hierarchy is temporal:** What you need changes with operation duration. Reflect that in the UI.
4. **Single source of truth:** Every metric appears once, at the level where it's most useful. No duplication.
5. **Keyboard accessible:** All levels navigable without mouse. Arrow keys to expand, Esc to collapse.
6. **Respect prefers-reduced-motion:** Animations (spinner, breathing dots) become static on reduced-motion.
7. **Color is never the only signal:** Status is word + color + position, never just color.

---

## Information Architecture

```
LiveStatus (Level 1)
├── Status word (aria-live)
├── Elapsed timer
└── Idle/working indicator

Expanded Status (Level 2)
├── Progress steps (current + next)
├── Recent files (if any)
└── Single critical warning

Diagnostics Panel (Level 3)
├── Progress Details
│   ├── Per-step timings
│   └── Failure mode if applicable
├── Artifacts
│   ├── Generated files (with sizes, download links)
│   └── Workspaces (with versions)
├── Routing & Health
│   ├── Provider chain (with eligibility)
│   ├── Fallback order
│   └── Circuit breaker status
├── Security & Privacy
│   ├── Sandbox isolation mode
│   ├── Data scrubbing status
│   └── Privacy mirror (replaced content)
├── Stream Diagnostics
│   ├── Cursor position
│   ├── Socket state (open/closed)
│   └── Resync events (count + last timestamp)
├── Session Telemetry
│   ├── Latency (animated count-up)
│   ├── Success rate
│   ├── Turns today
│   ├── Failed turns
│   ├── Benched providers
│   └── Local models loaded (VRAM)
└── Reasoning (if available)
    └── Full thinking block
```

---

## Implementation Roadmap

### Phase 1: AgentStatus Component (This Sprint)
- Extract unified component from LiveStatus + ContextRail
- Implement Level 1: Status + elapsed time
- Implement Level 2: Collapsible with progress steps + warnings
- Prototype at port 5307 with mock data

### Phase 2: Integration (Next Sprint)
- Replace LiveStatus in TurnBlock
- Add Level 2 auto-expand logic (>2s elapsed)
- Deprecate ContextRail sidebar in favor of Level 3 panel
- Migrate MissionControl diagnostics into Level 3

### Phase 3: Polish & Telemetry (Sprint After)
- Add keyboard navigation (arrow keys, Esc)
- Implement search/filter in Level 3
- Add performance metrics (step timings)
- Animated counter for latency (inherit MissionControl's useCountUp)
- Respect prefers-reduced-motion

---

## Audit: Current Component Issues

### ContextRail (Lines 56-162)
**Issues:**
- Conflates progress (top section) with artifacts (middle) with diagnostics (bottom)
- All sections visible simultaneously, no hierarchy
- Progress section shows 4 identical items with only state varying
- Socket/cursor info (lines 146-153) is highly technical but always shown
- No distinction between "currently relevant" and "nice to know"

**Migration Path:**
- Progress → Level 2 expanded view
- Files + workspaces → Level 3 Artifacts tab
- Context stats (model, provider, sandbox, privacy) → Level 3 Security/Routing tab
- Stream diagnostics → Level 3 Stream Diagnostics tab

### ThinkingBlock (Lines 22-54)
**Issues:**
- Only renders for models that provide thinking content
- Collapsed by default, requiring user discovery
- Isolated from other execution signals

**Upgrade:**
- Promote to Level 3 Reasoning tab
- Keep inline Level 2 indicator if thinking is present: "Model reasoning available (expand to view)"

### LiveStatus (TurnBlock.tsx, Lines 35-48)
**What's Good:**
- Simple, uncluttered
- Aria-live for screen readers
- Elapsed timer provides information

**Upgrade:**
- Becomes Level 1 of AgentStatus hierarchy
- Add click-to-expand affordance (visual hint)
- Add auto-expand logic (>2s elapsed)

### MissionControl (Lines 116-255)
**What's Good:**
- Comprehensive health overview
- Live animation (breathing nodes) for visual feedback
- Route map shows chain of providers

**What's Missing:**
- No task-level focus (lives in settings, not in conversation)
- Success rate only visible here, nowhere else
- Telemetry refresh logic not tied to turn execution

**Upgrade:**
- Move session stats to Level 3 Session Telemetry tab
- Link turn-level failures to circuit breaker status
- Add contextual warnings when success rate drops

---

## Mock Data Structure (for Prototype)

```typescript
interface AgentStatusData {
  // Level 1 (always shown)
  status: 'idle' | 'queued' | 'building_context' | 'thinking' | 'streaming' | 'completed' | 'failed';
  elapsed: number; // seconds
  
  // Level 2 (expanded)
  progress?: {
    steps: { label: string; completed: boolean }[];
    currentStepIndex: number;
  };
  recentFiles?: { name: string; bytes: number; url: string }[];
  warning?: {
    type: 'sandbox' | 'privacy' | 'circuit_breaker' | 'provider';
    severity: 'info' | 'warning' | 'error';
    message: string;
  };
  
  // Level 3 (diagnostics)
  diagnostics?: {
    progressTimings: { step: string; duration: number; error?: string }[];
    artifacts: { name: string; bytes?: number; version?: number; type: 'file' | 'workspace' }[];
    routing: {
      chain: { provider: string; model: string; eligible: boolean }[];
      openCircuits: number;
    };
    security: {
      sandbox: 'appcontainer' | 'unsandboxed' | null;
      scrubbing: boolean;
      privacyMirror?: { original: string; replaced: string }[];
    };
    stream: {
      cursor: number;
      connected: boolean;
      synced: boolean;
      resyncs: number;
    };
    telemetry: {
      latency_ms: number;
      successRate: number;
      turnsToday: number;
      failedTurns: number;
      benchedProviders: number;
      loadedModels: { name: string; vram_gb: number }[];
    };
    thinking?: string;
  };
}
```

---

## Success Criteria

- [x] Research document complete
- [ ] Level 1 displays instantly, no layout shift
- [ ] Level 2 auto-expands for operations >2s elapsed
- [ ] Level 3 accessible via deep-inspect link or diagnostics tab
- [ ] All data synchronized with actual turn state
- [ ] Keyboard navigation functional (arrow keys, Esc)
- [ ] Accessible to screen readers (aria-live, aria-expanded)
- [ ] Animated counters respect prefers-reduced-motion
- [ ] No flickering or jank during expansion/collapse

---

## References

- Current implementations: TurnBlock.tsx (LiveStatus), ThinkingBlock.tsx, ContextRail.tsx, MissionControl.tsx
- Status enum: `src/lib/status.ts` (STATUS_COPY mapping)
- Turn type: `src/lib/crs.ts` (TERMINAL states, Turn interface)
- Animation patterns: MissionControl's useCountUp (motion/react, cubic-bezier easing)
