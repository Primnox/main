# Unit 10 Research: Long-Running Agents and Task Delegation UX

**Research Date:** August 2026  
**Scope:** How agents work for minutes or hours, and how users safely delegate work they cannot watch in real-time

## Executive Summary

Long-running agent work presents a fundamental UX shift: users are transitioning from instant responses (fast AI) to results that take minutes or hours (slow AI). The key design challenge is building trust in a system the user cannot watch. This requires four design pillars:

1. **Honest progress visibility** — not a spinner, but real state
2. **Resumption with coherence** — pick up where you left off without losing context
3. **Notification that doesn't interrupt** — report completion without blocking the user
4. **Recovery mechanics** — what to do when things go wrong or change

---

## Backend Architecture: task_state.py

Primnox's backend carries the patterns needed for this transition. The task_state module implements:

### Task Lifecycle
- **Status values:** `active`, `blocked`, `completed`, `failed`, `partial`, `abandoned`
- **Four-valued outcomes:** `completed`, `failed`, `partial`, `unknown` (not yes/no, but honestly uncertain)
- **Key insight:** "partial" and "unknown" are load-bearing. A tool that crashes mid-write doesn't fail cleanly — marking it failed invites a destructive blind retry. "Unknown" is the honest answer when nobody has checked.

### State Compaction
The `snapshot()` and `render()` functions produce compact, structured views of task state for context construction:

```
Task: reduce tool-call cost
Status: active
Completed:
  ✓ benchmarked 1/2/4/8 steps
  ✓ measured cache behaviour
Unresolved:
  ? design immutable compaction [pending]
  ? integrate state references [pending]
Known:
  · tool transcripts accumulate superlinearly
Latest: Cached writes save 35% vs uncached baseline
Next: → design immutable compaction
```

This structure is small enough to fit in a prompt without the transcript — enabling resumption without re-reading a wall of raw events.

### Action Tracking
Each step in a task is tracked:
- **Sequence:** numbered, ordered
- **Status:** `pending`, `running`, `completed`, `failed`, `partial`, `unknown`, `skipped`
- **Timestamps:** `started_at`, `finished_at`
- **Results:** reference to tool output, not the output itself

The `verify()` function re-checks completed/unknown actions against the real system before resuming — this is the architecture's resumption step.

---

## Backend Architecture: episodes.py

For gaps longer than 30 minutes, episodic memory consolidates raw events into narrative episodes. Key concepts:

### Events and Episodes
- **Events:** cheap, individual observations (file opened, tool ran, test failed)
- **Episodes:** coherent stretches of work (consolidation of related events)
- **Importance scoring:** errors (0.9), task start/complete (0.8), commits (0.8), tool runs (0.5), file opens (0.3)

### Temporal Reconstruction
The `timeline()` function answers "what was I doing?" by reconstructing a period from episodes and loose events, ranked by importance and trimmed to key entries. Each entry carries evidence references.

### Consolidation Strategy
- **Deterministic by default:** grouping by time gap and scope (30 minutes = new episode)
- **Summarization hook:** can inject a model-written summary, but the system works without it
- **Result references:** episodes link to tool outputs, not inline them

---

## Current UI: TurnBlock and MissionControl

### TurnBlock.tsx
Shows live progress of a single turn:
- **LiveStatus component:** elapsed time (not just spinner)
- **Streaming reply:** tokens arriving in real-time
- **Tool calls and executions:** visible as they run
- **Failure handling:** retryable errors as first-class UI

### MissionControl.tsx
Provider-focused dashboard:
- **Telemetry stats:** turns today, success rate, local loading
- **Route map:** real-time routing status
- **Health indicator:** "all clear" vs. benched circuit breakers

**Gap identified:** No task-level dashboard. Users can see provider health and individual turn progress, but not "what agent am I waiting for, and what's it doing?"

---

## Competitor Patterns: Devin, Hermes, CI/CD

### Devin AI (2026 Updates)
- **/handoff command:** transfers context to cloud, user can close laptop
- **Parallel sessions:** multiple agents work simultaneously
- **Instant notifications:** team members stay informed of progress
- **Pattern:** Fire-and-forget with async context injection

### Hermes Agent (Nous Research)
- **delegate_task(background=true):** returns immediately with agent ID
- **Result injection:** subagent result comes back as notification when done
- **Fan-out pattern:** run multiple subagents in background, consolidate results
- **Notification suppression:** child task noise is filtered; only final summary surfaces
- **Key insight:** "auto-execution + notification > full autonomy from day one"

### CI/CD Monitoring (Datadog, Site24x7)
- **Real-time dashboards:** pipeline status updates without polling
- **Performance tracking:** job duration vs. baseline, resource usage
- **Custom dashboards:** teams configure what matters to them
- **Alerting:** failures/delays/regressions trigger notifications
- **Pattern:** Multi-stage visibility (pipeline → stage → job → step)

---

## Gap Audit: What Primnox Needs

### 1. Task-Level Dashboard (Missing)
**Current state:** TurnBlock shows one turn; MissionControl shows provider health  
**Needed:** Background task panel showing:
- Task goal and status
- Progress through planned actions
- Latest observation / latest error
- Elapsed time and estimate to completion
- Action menu: pause, resume, cancel, retarget

**Evidence:** Devin and Hermes both surface delegated work as first-class entities, not just notifications

### 2. Catch-Up Summary (Partially implemented)
**Current state:** task_state.render() exists; no UI uses it  
**Needed:**
- On resumption, show task snapshot inline (not just in the model's context)
- Distinguish "completed" from "unknown" from "partial" visually
- Link unresolved actions to their errors for quick debugging

**Evidence:** CI/CD dashboards show job status with error callouts; Devin notifications include error context

### 3. Notification Pattern (Missing)
**Current state:** TurnBlock has live status; no background task updates  
**Needed:**
- Background task completion arrives as non-blocking notification
- User can dismiss or expand; UI never freezes the chat
- Notification includes: what changed, why it matters, next steps

**Evidence:** Hermes suppresses child task noise; only final summary surfaces. Devin uses instant notifications.

### 4. Verification and Recovery (Implemented in backend, not exposed)
**Current state:** task_state.verify() exists and checks against the system  
**Needed:**
- On resumption, auto-verify completed actions (or prompt if risky)
- Show which actions need re-checking before proceeding
- Allow user to manually mark actions as true/false

**Evidence:** task_state.verify() is the architecture's resumption step; CI/CD dashboards show failure states with recovery actions

### 5. Multi-Step Workflow Tracking (Not visible)
**Current state:** Actions are tracked but UI doesn't surface the sequence  
**Needed:**
- Visual progress bar or step indicator (5/12 actions done)
- Timeline of when actions started/finished
- Links to relevant tool outputs or assets

**Evidence:** Enterprise agent patterns include "multi-step workflow tracking" as a core design pillar

---

## Design Principles for Implementation

### Principle 1: Honest Progress, Not Spinner
Don't use a generic spinner. Surface real state:
- Status: pending → running → completed/failed/partial/unknown
- Elapsed time (not wall-clock, but time spent)
- Next action (what's about to run)
- Latest error or observation (if any)

### Principle 2: Current Intent Outranks Stale Plans
When a user retargets a task (goal changes), the pending plan is dropped but completed work is kept. The UI should reflect this:
- Show old plan as greyed-out history
- Highlight new next-step
- Keep "known" facts visible (they're still true)

### Principle 3: Unknown is Load-Bearing
A crashed tool that wrote a file is not "failed." It's "unknown" — the system doesn't know if it succeeded. The UI should surface this:
- Treat "unknown" and "partial" as distinct from "completed" and "failed"
- Offer a verify action (re-check against the system)
- Only retry after verification, not blind

### Principle 4: Resumption is Verification
When a user comes back to a task after minutes or hours, the UI should:
1. Show the task snapshot (what's done, what's not)
2. Highlight what needs verification before proceeding
3. Allow quick resume or retarget
4. Keep the full transcript available but not in the way (search, expand, context panel)

### Principle 5: Notification Without Interruption
When a background task finishes:
1. Add to a notification queue (non-blocking)
2. User can dismiss, expand, or act on it
3. Don't freeze the current chat or turn
4. Consolidate multiple task notifications into one summary if they're related

---

## Implementation Priorities

### Phase 1: Background Task Indicator (MVP)
- [ ] Small badge in header showing open task count
- [ ] Click to expand task panel
- [ ] Show task goal, status, elapsed time
- [ ] Show next pending action and latest observation
- [ ] Action buttons: expand, pause, cancel

### Phase 2: Task Panel with Progress
- [ ] Full-width or side panel view
- [ ] Visual progress: completed ✓, failed ✗, pending ?, unknown ⚠
- [ ] Action timeline: when each step ran
- [ ] Error callouts with recovery options
- [ ] Catch-up summary on hover/expand

### Phase 3: Notification Pattern
- [ ] Task completion arrives as non-blocking notification
- [ ] Notification includes: goal, status, elapsed time, key findings
- [ ] User can dismiss, open task panel, or run next suggested step
- [ ] Multiple task notifications consolidate into one summary

### Phase 4: Verification and Recovery
- [ ] On resumption, show which actions need verification
- [ ] One-click verify option
- [ ] Show verification results before proceeding
- [ ] Manual override: mark action as true/false

---

## Technical Decisions

### State Synchronization
- Polling (4-8 second intervals): acceptable for background tasks, trades latency for client simplicity
- WebSocket or SSE: would enable sub-second updates; defer to Phase 3
- Optimistic updates: show action as "running" before confirmation; risky with unknown outcomes

### Data Cardinality
- One task active at a time: simpler UX, aligns with current "resume one task" pattern
- Multiple concurrent tasks: richer feature, requires task switching UI, defer to Phase 2

### Context Injection
- Send task snapshot to model: reduces transcript size by ~60% (task_state.render() is ~500 tokens vs 2000+ for full transcript)
- Auto-resume on come-back: load last task automatically; needs user consent (e.g., "Resume task X?" button)

---

## Success Metrics

1. **Resumption coherence:** User returns to a task after 1+ hours and knows exactly where they left off (task snapshot is sufficient, no need to re-read transcript)
2. **Error recovery:** When a task enters "partial" or "unknown" state, the UI guides the user to verify or retry (not left confused)
3. **Notification efficiency:** Background task completion reaches the user without blocking their current work (test: can user read chat while task completes in background)
4. **Trust building:** Users successfully delegate minutes-long tasks and check back later (measure: session duration, task completion rate)

---

## References and Sources

- [Devin Reviews 2026: Pricing, Features & More](https://www.selecthub.com/p/ai-agent-tools/devin/)
- [Long-Running AI Agents and Task Decomposition 2026 | Zylos Research](https://zylos.ai/research/2026-01-16-long-running-ai-agents)
- [AI Agent Delegation Patterns: Four Best Architectures for 2026 | Fastio](https://fast.io/resources/ai-agent-delegation-patterns/)
- [Agent UX: designing UI for AI agents in 2026](https://fuselabcreative.com/ui-design-for-ai-agents/)
- [How Agents Manage Other Agents: Four Subagents Patterns in 2026](https://www.philschmid.de/subagent-patterns-2026)
- [Best practices for CI/CD monitoring | Datadog](https://www.datadoghq.com/blog/best-practices-for-ci-cd-monitoring/)
- [Primnox backend: task_state.py](../backend/v2/task_state.py)
- [Primnox backend: episodes.py](../backend/v2/episodes.py)
- [Primnox frontend: TurnBlock.tsx](../../frontend/src/components/TurnBlock.tsx)
- [Primnox frontend: MissionControl.tsx](../../frontend/src/components/MissionControl.tsx)
