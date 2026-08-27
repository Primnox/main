import { useState } from 'react';
import { CapabilityMatrix } from './CapabilityMatrix';
import { RoadmapStrip } from './RoadmapStrip';

/* Two views, because this unit produced two things and a reader arrives wanting
 * one of them.
 *
 * Tabs and not a single scroll: the matrix needs a horizontal scroll container
 * with two sticky axes, and nesting that inside a page that also scrolls
 * vertically is how a sticky header quietly stops sticking. Each view owns its
 * own scrolling.
 *
 * The matrix is first. The roadmap is a conclusion, and a conclusion read
 * before its evidence is a conclusion nobody can argue with.
 */

const VIEWS = [
  { id: 'matrix', label: 'Capability matrix' },
  { id: 'roadmap', label: 'Roadmap' },
] as const;

type ViewId = (typeof VIEWS)[number]['id'];

export function BenchmarkRoadmapDemo() {
  const [view, setView] = useState<ViewId>('matrix');

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg text-on-surface">
      <div
        className="flex shrink-0 gap-1 border-b border-on-surface/15 px-6 pt-4"
        role="tablist"
        aria-label="Unit 13 views"
      >
        {VIEWS.map((v) => {
          const on = v.id === view;
          return (
            <button
              key={v.id}
              type="button"
              role="tab"
              aria-selected={on}
              onClick={() => setView(v.id)}
              className={[
                'px-interactive border-b-2 px-3 py-2 font-mono text-[10px]',
                'uppercase tracking-[0.14em] transition-none',
                on
                  ? 'border-b-on-surface text-on-surface'
                  : 'border-b-transparent text-on-surface/60 hover:text-on-surface',
              ].join(' ')}
            >
              {v.label}
            </button>
          );
        })}
      </div>

      <div className="min-h-0 flex-1">
        {view === 'matrix' ? <CapabilityMatrix /> : <RoadmapStrip />}
      </div>
    </div>
  );
}
