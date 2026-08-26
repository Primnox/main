# Agent Status UI Prototype (Unit 7)

Three-level information hierarchy resolving transparency vs cognitive overload in agent status displays.

## Quick Start

### Run the Proto

```bash
cd frontend
npm run dev:proto
```

Server runs on http://localhost:5307

### Build for Deployment

```bash
cd frontend
npm run build:proto
```

Output goes to `dist-proto/`

## What's Included

### Components

- **AgentStatus.tsx** — Main component implementing all 3 levels
- **AgentStatusDemo.tsx** — Interactive demo with 6 different scenarios
- **AgentStatus.css** — Styling with dark mode support

### Demos

1. **Idle** — No operation. Minimal state.
2. **Quick** — Fast operation (<2s). Level 1 only, no auto-expand.
3. **Slow** — Long operation (8+ seconds). Level 2 auto-expands at 2s.
4. **Warning** — Shows critical alert + generated files. Demonstrates Level 2 warning state.
5. **Failed** — Operation failed. Error state with provider info.
6. **Reasoning** — Completed with Claude Extended Thinking. Shows Level 3 reasoning tab.

## Design Principles

### Level 1: Glance (0-1 second cognitive load)
- Status word + elapsed time
- Single dot indicator (working/idle)
- Click to expand
- **Cognitive load:** 1 data point

### Level 2: Expanded (5-15 seconds cognitive load)
- Progress steps (building context → thinking → streaming)
- Recent generated files (if any)
- Single critical warning (sandbox, privacy, circuit breaker)
- Auto-opens after 2 seconds on slow operations
- **Cognitive load:** ~7 data points, grouped

### Level 3: Deep Inspect (30+ seconds, active debugging)
- Tabbed interface (Progress, Security & Privacy, Stream, Telemetry, Reasoning)
- Complete diagnostics with timings
- Security posture + sandbox status
- Stream statistics (cursor, socket, syncs)
- Session telemetry (latency, success rate, failed turns)
- **Cognitive load:** 50+ data points, heavily structured

## Accessibility

- ✓ Status changes announced via `aria-live`
- ✓ Keyboard navigation (Enter/Space to expand, Esc to collapse)
- ✓ Color is never the only signal (icon + word + position)
- ✓ Respects `prefers-reduced-motion` (animations disabled)
- ✓ All interactive elements have descriptive labels
- ✓ Logical tab order through keyboard

## Integration Path

### Phase 1: Extract (This Sprint)
- AgentStatus component lives in `proto/agent-status/`
- No integration yet, pure demo

### Phase 2: Integrate (Next Sprint)
- Move to `frontend/src/components/AgentStatus.tsx`
- Replace LiveStatus in TurnBlock
- Add to ContextRail as an option
- Deprecate old components gradually

### Phase 3: Polish (Sprint After)
- Add performance metrics (step timings per provider)
- Integrate MissionControl diagnostics into Level 3
- Add keyboard shortcuts (? to toggle deep inspect)
- Implement search/filter in Level 3 diagnostics
- Animated counter-up for latency (inherit from MissionControl)

## Data Structure

```typescript
interface AgentStatusProps {
  // Level 1
  status: 'idle' | 'queued' | 'building_context' | 'thinking' | 'streaming' | 'completed' | 'failed';
  elapsed: number; // seconds

  // Level 2
  progress?: { label: string; completed: boolean; duration?: number }[];
  recentFiles?: { name: string; bytes?: number; url?: string }[];
  warning?: { type: string; severity: 'info' | 'warning' | 'error'; message: string };

  // Level 3
  diagnostics?: {
    sandbox: 'appcontainer' | 'unsandboxed' | null;
    scrubbing: boolean;
    successRate?: number;
    latency_ms?: number;
    turnsToday?: number;
    failedTurns?: number;
    benchedProviders?: number;
    cursor?: number;
    connected?: boolean;
    synced?: boolean;
    resyncs?: number;
    thinking?: string;
  };
}
```

## Browser Support

- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

## Styling

Uses CSS custom properties for theming:

```css
--color-on-surface: rgb(0 0 0);
--color-primary: rgb(0 102 255);
--color-success: rgb(34 197 94);
--color-warn: rgb(245 158 11);
--color-error: rgb(239 68 68);
```

Dark mode support via `prefers-color-scheme: dark`

## See Also

- [Unit 7 Research Doc](../../../../docs/ui-research/07-agent-status.md)
- [Current LiveStatus](../../../components/TurnBlock.tsx)
- [Current ThinkingBlock](../../../components/ThinkingBlock.tsx)
- [Current ContextRail](../../../components/ContextRail.tsx)
- [Current MissionControl](../../../components/MissionControl.tsx)
