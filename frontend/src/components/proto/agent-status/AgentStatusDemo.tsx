import { useState, useEffect } from 'react';
import { AgentStatus, type AgentStatusProps } from './AgentStatus';

/* Demo harness for the 3-level AgentStatus hierarchy.
 *
 * Shows all combinations:
 * 1. Idle state (no operation)
 * 2. Quick operation (< 2s, Level 1 sufficient)
 * 3. Slow operation (10+ seconds, Level 2 auto-expands)
 * 4. Long operation with warnings (Level 2 shows critical alert)
 * 5. Failed operation (Level 2 + error state)
 * 6. Completed with reasoning (Level 3 has reasoning tab)
 */

type Demo = 'idle' | 'quick' | 'slow' | 'warning' | 'failed' | 'reasoning';

const DEMOS: Record<Demo, AgentStatusProps> = {
  idle: {
    status: 'idle',
    elapsed: 0,
  },

  quick: {
    status: 'streaming',
    elapsed: 1.2,
    progress: [
      { label: 'Queued', completed: true, duration: 0.1 },
      { label: 'Building context', completed: true, duration: 0.3 },
      { label: 'Thinking', completed: true, duration: 0.5 },
      { label: 'Streaming', completed: false },
    ],
  },

  slow: {
    status: 'thinking',
    elapsed: 8.5,
    progress: [
      { label: 'Queued', completed: true, duration: 0.1 },
      { label: 'Building context', completed: true, duration: 3.2 },
      { label: 'Thinking', completed: false, duration: 5.2 },
      { label: 'Streaming', completed: false },
    ],
    recentFiles: [],
    diagnostics: {
      sandbox: 'appcontainer',
      scrubbing: true,
      successRate: 0.95,
      latency_ms: 245,
      turnsToday: 12,
      failedTurns: 0,
      benchedProviders: 0,
      cursor: 0,
      connected: true,
      synced: true,
      resyncs: 0,
    },
  },

  warning: {
    status: 'streaming',
    elapsed: 6.3,
    progress: [
      { label: 'Queued', completed: true, duration: 0.1 },
      { label: 'Building context', completed: true, duration: 1.2 },
      { label: 'Thinking', completed: true, duration: 2.0 },
      { label: 'Streaming', completed: false },
    ],
    recentFiles: [
      { name: 'analysis.json', bytes: 4096, url: '#' },
      { name: 'report.md', bytes: 12288, url: '#' },
    ],
    warning: {
      type: 'sandbox',
      severity: 'warning',
      message: 'Sandbox: NONE — code runs unisolated. Enable AppContainer in Settings.',
    },
    diagnostics: {
      sandbox: 'unsandboxed',
      scrubbing: false,
      successRate: 0.89,
      latency_ms: 412,
      turnsToday: 18,
      failedTurns: 2,
      benchedProviders: 1,
      cursor: 1024,
      connected: true,
      synced: true,
      resyncs: 0,
    },
  },

  failed: {
    status: 'failed',
    elapsed: 3.7,
    progress: [
      { label: 'Queued', completed: true, duration: 0.1 },
      { label: 'Building context', completed: true, duration: 1.2 },
      { label: 'Thinking', completed: false, duration: 2.4 },
      { label: 'Streaming', completed: false },
    ],
    warning: {
      type: 'provider',
      severity: 'error',
      message: 'Primary provider unreachable. Fallback provider exhausted.',
    },
    diagnostics: {
      sandbox: 'appcontainer',
      scrubbing: true,
      successRate: 0.92,
      latency_ms: 0,
      turnsToday: 15,
      failedTurns: 1,
      benchedProviders: 2,
      cursor: 512,
      connected: false,
      synced: false,
      resyncs: 3,
    },
  },

  reasoning: {
    status: 'completed',
    elapsed: 12.4,
    progress: [
      { label: 'Queued', completed: true, duration: 0.1 },
      { label: 'Building context', completed: true, duration: 2.1 },
      { label: 'Thinking', completed: true, duration: 7.2 },
      { label: 'Streaming', completed: true, duration: 3.0 },
    ],
    recentFiles: [
      { name: 'implementation.ts', bytes: 8192, url: '#' },
      { name: 'tests.ts', bytes: 5120, url: '#' },
    ],
    diagnostics: {
      sandbox: 'appcontainer',
      scrubbing: true,
      successRate: 0.97,
      latency_ms: 189,
      turnsToday: 24,
      failedTurns: 0,
      benchedProviders: 0,
      cursor: 2048,
      connected: true,
      synced: true,
      resyncs: 0,
      thinking: `I need to implement a TypeScript solution for the agent status UI component.

Let me think through the requirements:
1. Three-level hierarchy: Glance (Level 1) → Expand (Level 2) → Deep Inspect (Level 3)
2. Level 1: Status word + elapsed time, minimal cognitive load
3. Level 2: Auto-expands for slow operations (>2s), shows progress steps
4. Level 3: Comprehensive diagnostics with tabs

The key insight is that operation duration should drive the UI complexity. Quick operations
need only the spinner; long operations deserve more context.

I'll use React's Collapsible component (from Base UI) for the expand/collapse interaction,
and make Level 3 a tabbed interface with multiple diagnostic sections.

State management: Use local useState for expand/deepInspect flags, with a timer to auto-expand
at 2 seconds. This respects prefers-reduced-motion for animations.

The component needs to be accessible:
- aria-live for status changes
- aria-expanded for collapsible sections
- Keyboard navigation (Enter/Space to expand, Esc to collapse)
- Tab order respects logical flow

For styling, I'll use CSS custom properties so it works with Primnox's existing design system.`,
    },
  },
};

export function AgentStatusDemo() {
  const [selected, setSelected] = useState<Demo>('idle');
  const [liveElapsed, setLiveElapsed] = useState(0);

  // Simulate elapsed time for active demos
  useEffect(() => {
    if (selected === 'idle' || selected === 'quick' || selected === 'slow' || selected === 'warning' || selected === 'failed' || selected === 'reasoning') {
      return;
    }
  }, [selected]);

  // Live timer for demos that need it
  useEffect(() => {
    if (!['quick', 'slow', 'warning', 'failed'].includes(selected)) {
      setLiveElapsed(0);
      return;
    }

    const interval = setInterval(() => {
      setLiveElapsed(prev => {
        const maxTime = selected === 'quick' ? 2 : 15;
        if (prev >= maxTime) return prev;
        return prev + 0.1;
      });
    }, 100);

    return () => clearInterval(interval);
  }, [selected]);

  const data = { ...DEMOS[selected], elapsed: liveElapsed || DEMOS[selected].elapsed };

  return (
    <div className="min-h-screen bg-gradient-to-br from-on-surface/[0.02] to-on-surface/[0.04]">
      <div className="max-w-2xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-12">
          <h1 className="text-3xl font-bold mb-2">Agent Status UI</h1>
          <p className="text-on-surface/60">
            3-level hierarchy demonstrating transparency vs cognitive overload resolution
          </p>
        </div>

        {/* Demo selector */}
        <div className="mb-8 grid grid-cols-2 gap-2 sm:grid-cols-3">
          {(Object.keys(DEMOS) as Demo[]).map(key => (
            <button
              key={key}
              onClick={() => {
                setSelected(key);
                if (key !== 'reasoning' && key !== 'idle') setLiveElapsed(0);
              }}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition duration-200 ${
                selected === key
                  ? 'bg-primary text-white'
                  : 'bg-on-surface/[0.06] text-on-surface/70 hover:bg-on-surface/[0.1]'
              }`}>
              {key.charAt(0).toUpperCase() + key.slice(1)}
            </button>
          ))}
        </div>

        {/* Instructions */}
        <div className="mb-8 p-4 bg-on-surface/[0.03] border border-on-surface/[0.06] rounded-lg">
          <p className="text-sm text-on-surface/60 mb-2">
            <strong>Instructions:</strong>
          </p>
          <ul className="text-sm text-on-surface/60 space-y-1 list-disc list-inside">
            <li><strong>Idle:</strong> No operation in progress. Click to expand (shows nothing).</li>
            <li><strong>Quick:</strong> Fast operation (&lt;2s). Level 1 sufficient, no auto-expand.</li>
            <li><strong>Slow:</strong> Long operation (&gt;2s). Level 2 auto-expands, shows progress.</li>
            <li><strong>Warning:</strong> Shows critical alert + generated files. Click "Show full diagnostics" for Level 3.</li>
            <li><strong>Failed:</strong> Error state with sandbox warning and failed provider info.</li>
            <li><strong>Reasoning:</strong> Completed with model thinking (Claude Extended Thinking).</li>
          </ul>
        </div>

        {/* Demo component */}
        <div className="bg-white dark:bg-on-surface/[0.05] rounded-xl border border-on-surface/[0.08] p-8 shadow-sm">
          <AgentStatus {...data} />
        </div>

        {/* Meta info */}
        <div className="mt-8 text-xs text-on-surface/40 space-y-1">
          <p>Status: <code className="bg-on-surface/[0.05] px-1.5 py-0.5 rounded">{data.status}</code></p>
          <p>Elapsed: <code className="bg-on-surface/[0.05] px-1.5 py-0.5 rounded">{data.elapsed.toFixed(1)}s</code></p>
          {data.progress && <p>Progress steps: {data.progress.length}</p>}
          {data.diagnostics && <p>Diagnostics available: ✓</p>}
        </div>

        {/* Design notes */}
        <div className="mt-12 space-y-6">
          <section>
            <h2 className="text-lg font-semibold mb-3">Design Notes</h2>
            <div className="space-y-4">
              <div className="p-4 bg-on-surface/[0.02] rounded-lg border border-on-surface/[0.05]">
                <h3 className="font-medium mb-1">Level 1: Glance</h3>
                <p className="text-sm text-on-surface/70">
                  Always visible. Status word + elapsed time. Click the row to expand. No cognit overload.
                </p>
              </div>
              <div className="p-4 bg-on-surface/[0.02] rounded-lg border border-on-surface/[0.05]">
                <h3 className="font-medium mb-1">Level 2: Expanded</h3>
                <p className="text-sm text-on-surface/70">
                  Auto-opens for operations &gt;2s. Shows progress steps, generated files, and single critical warning. Grouped and sequenced to avoid overwhelm.
                </p>
              </div>
              <div className="p-4 bg-on-surface/[0.02] rounded-lg border border-on-surface/[0.05]">
                <h3 className="font-medium mb-1">Level 3: Deep Inspect</h3>
                <p className="text-sm text-on-surface/70">
                  Comprehensive diagnostics with tabs. Accessible only when needed. Includes progress timings, security info, stream status, telemetry, and model reasoning.
                </p>
              </div>
            </div>
          </section>

          <section>
            <h2 className="text-lg font-semibold mb-3">Accessibility</h2>
            <ul className="text-sm text-on-surface/70 space-y-1 list-disc list-inside">
              <li>Status changes announced via aria-live</li>
              <li>Keyboard navigation: Enter/Space to expand, Esc to collapse</li>
              <li>Color is never the only signal (icon + word + position)</li>
              <li>Respects prefers-reduced-motion (no animations)</li>
              <li>All interactive elements have descriptive labels</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
