import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import { initTheme } from './lib/themes'
import './styles/fonts.css'
import './styles/tailwind.css'
import './styles/themes.css'
import './styles/progressive-disclosure.css'

import { MainstreamShowcase } from './components/proto/mainstream-assistants'
import CodingAgentsDemoPage from './components/proto/coding-agents/Demo'
import { ResearchPanel } from './components/proto/research-build-agents'
import { ResponsePrimitivesDemo } from './components/proto/response-primitives'
import { ArtifactCardsShowcase } from './components/proto/artifact-cards'
import { ArtifactModelDemo } from './components/proto/artifact-model'
import { AgentStatusDemo } from './components/proto/agent-status'
import { ProgressiveDisclosureShowcase } from './components/examples/ProgressiveDisclosureExamples'
import { StoryGallery } from './components/RecoveryBlock.stories'
import { ComposerDemo } from './components/proto/navigation-composer'
import FamiliarityDesignProto from './components/proto/familiarity-design'
import { LongRunningAgentsDemo } from './components/proto/long-running-agents/Demo'

// The thirteen research units each built a prototype in isolation, on its own
// port, against its own mock data. That was right for producing them and wrong
// for judging them: nobody compares two interfaces by running two dev servers.
// This gallery is the comparison surface — one server, one theme, one place to
// see whether the units actually agree with each other.
//
// Unit 13 has no entry here on purpose: it delivered documents only, and
// listing it with an empty panel would imply a prototype exists. Unit 4 was
// re-run — its first attempt produced a backend classifier instead of the
// response-primitive rule it was asked for — and now has one.

interface Proto {
  id: string
  unit: number
  title: string
  blurb: string
  render: () => React.ReactNode
}

const PROTOS: Proto[] = [
  {
    id: 'mainstream-assistants',
    unit: 1,
    title: 'Mainstream assistants',
    blurb: 'Copy, regenerate, suggested prompts — the gaps against ChatGPT/Claude/Gemini.',
    render: () => <MainstreamShowcase />,
  },
  {
    id: 'coding-agents',
    unit: 2,
    title: 'Coding agents',
    blurb: 'Diff viewer, file-tree markers, and an approval gate before changes apply.',
    render: () => <CodingAgentsDemoPage />,
  },
  {
    id: 'research-build-agents',
    unit: 3,
    title: 'Research agents',
    blurb: 'Claim → evidence: the provenance world_model.py records but the UI never shows.',
    // embedded, because embedded={false} renders fixed inset-0 and covers the
    // gallery's own navigation.
    render: () => <ResearchPanel embedded />,
  },
  {
    id: 'response-primitives',
    unit: 4,
    title: 'Response primitives',
    blurb: 'One rule places any payload at inline / block / panel — semantic type is not an input.',
    render: () => <ResponsePrimitivesDemo />,
  },
  {
    id: 'artifact-cards',
    unit: 5,
    title: 'Artifact cards',
    blurb: 'Progressive action disclosure across execution, code, error and table cards.',
    render: () => <ArtifactCardsShowcase />,
  },
  {
    id: 'artifact-model',
    unit: 6,
    title: 'Artifact model',
    blurb: 'Three types through one metadata shape — and where the shared lifecycle breaks.',
    render: () => <ArtifactModelDemo />,
  },
  {
    id: 'agent-status',
    unit: 7,
    title: 'Agent status',
    blurb: 'Glance / expanded / deep-inspect, with duration deciding which level opens.',
    render: () => <AgentStatusDemo />,
  },
  {
    id: 'progressive-disclosure',
    unit: 8,
    title: 'Progressive disclosure',
    blurb: 'The five-level model applied to messages, settings, permissions and errors.',
    render: () => <ProgressiveDisclosureShowcase />,
  },
  {
    id: 'failure-recovery',
    unit: 9,
    title: 'Failure & recovery',
    blurb: 'Ten failure kinds, each offering only the recovery that can actually work.',
    render: () => <StoryGallery />,
  },
  {
    id: 'long-running-agents',
    unit: 10,
    title: 'Long-running agents',
    blurb: 'Delegate, leave, come back — indicator, task panel and catch-up summary.',
    render: () => <LongRunningAgentsDemo />,
  },
  {
    id: 'navigation-composer',
    unit: 11,
    title: 'Navigation & composer',
    blurb: 'The rail, the conversation list and the composer, extracted from App.tsx.',
    render: () => <ComposerDemo />,
  },
  {
    id: 'familiarity-design',
    unit: 12,
    title: 'Familiarity & design',
    blurb: 'The same components dark and light — the one DESIGN.md verdict that changed.',
    render: () => <FamiliarityDesignProto />,
  },
]

function Gallery() {
  const [activeId, setActiveId] = useState(PROTOS[0].id)
  const active = PROTOS.find((p) => p.id === activeId) ?? PROTOS[0]

  return (
    <div className="flex h-screen overflow-hidden bg-bg text-on-surface">
      <nav
        aria-label="Prototypes"
        className="flex w-72 shrink-0 flex-col overflow-y-auto border-r border-on-surface/15"
      >
        <div className="border-b border-on-surface/15 px-4 py-3">
          <div className="text-xs uppercase tracking-widest text-on-surface/60">
            UI research
          </div>
          <div className="mt-1 text-sm">
            {PROTOS.length} prototypes · 13 units
          </div>
        </div>

        {PROTOS.map((p) => {
          const isActive = p.id === active.id
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => setActiveId(p.id)}
              // aria-current, not colour alone: the active row has to be
              // announced, and DESIGN.md's accessibility line forbids using
              // the accent as the only signal.
              aria-current={isActive ? 'page' : undefined}
              className={[
                'border-b border-on-surface/10 px-4 py-3 text-left transition-none',
                isActive
                  ? 'bg-on-surface/10 text-on-surface'
                  : 'text-on-surface/70 hover:bg-on-surface/5',
              ].join(' ')}
            >
              <div className="flex items-baseline gap-2">
                <span className="text-xs tabular-nums text-on-surface/50">
                  {String(p.unit).padStart(2, '0')}
                </span>
                <span className="text-sm">{p.title}</span>
              </div>
              <p className="mt-1 text-xs leading-snug text-on-surface/50">
                {p.blurb}
              </p>
            </button>
          )
        })}
      </nav>

      <main className="min-w-0 flex-1 overflow-auto">
        {/* Remounting on id change rather than letting React reconcile: these
            prototypes were written independently and several hold timers and
            intervals. Reusing one's tree for another leaks them. */}
        <React.Fragment key={active.id}>{active.render()}</React.Fragment>
      </main>
    </div>
  )
}

initTheme()

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <Gallery />
    </MotionConfig>
  </React.StrictMode>,
)
