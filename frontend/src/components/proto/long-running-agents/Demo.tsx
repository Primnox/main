import { useState } from 'react'
import { BackgroundTaskIndicator } from './BackgroundTaskIndicator'
import { TaskPanel } from './TaskPanel'
import { TaskNotification } from './TaskNotification'
import { CatchUpSummary } from './CatchUpSummary'

// The four components of this unit only make sense together: the indicator is
// what you see while away, the notification is how you learn it finished, the
// catch-up summary is what you read on return, and the panel is where you go
// when the summary is not enough. Demoing them separately would hide the thing
// the unit is actually claiming — that those four surfaces are one story.
//
// The mock deliberately uses a PARTIAL task with one failed and one unknown
// action. A task that completed cleanly proves nothing: the whole argument in
// task_state.py is that partial and unknown are load-bearing, and a demo that
// only shows green never tests it.

const MINUTES = 60 * 1000

const now = Date.now()
const iso = (msAgo: number) => new Date(now - msAgo).toISOString()

const TASK = {
  id: 'task_7f3a91',
  goal: 'Audit the provider fallback path and report which routes lack a timeout',
  status: 'partial' as const,
  constraints: [
    'Do not modify provider configuration',
    'Read-only against the live route table',
  ],
  created_at: iso(137 * MINUTES),
  updated_at: iso(12 * MINUTES),
  latest_observation:
    'Six of eight routes declare an explicit timeout. The OmniRoute path inherits a default that could not be resolved statically.',
  next_actions: [
    'Resolve the inherited OmniRoute timeout at runtime',
    'Re-run the audit against the resolved value',
  ],
  known: [
    'Route table has 8 entries',
    '6 routes declare timeouts explicitly',
    'OmniRoute inherits from a chain the static pass could not follow',
  ],
  actions: [
    {
      id: 'a1',
      sequence: 1,
      description: 'Enumerate routes from the provider registry',
      status: 'completed' as const,
      started_at: iso(137 * MINUTES),
      finished_at: iso(135 * MINUTES),
      error: null,
      detail: 'Found 8 routes',
    },
    {
      id: 'a2',
      sequence: 2,
      description: 'Read timeout declarations per route',
      status: 'completed' as const,
      started_at: iso(135 * MINUTES),
      finished_at: iso(120 * MINUTES),
      error: null,
      detail: '6 explicit, 2 inherited',
    },
    {
      id: 'a3',
      sequence: 3,
      description: 'Resolve inherited timeout for OmniRoute',
      status: 'unknown' as const,
      started_at: iso(120 * MINUTES),
      finished_at: iso(118 * MINUTES),
      error: null,
      detail:
        'Static resolution followed the chain two levels and then hit a runtime-computed value. Neither confirmed nor refuted.',
    },
    {
      id: 'a4',
      sequence: 4,
      description: 'Cross-check against the live route table',
      status: 'failed' as const,
      started_at: iso(115 * MINUTES),
      finished_at: iso(113 * MINUTES),
      error: 'Connection refused — backend was not running at :4109',
      detail: null,
    },
    {
      id: 'a5',
      sequence: 5,
      description: 'Write the audit summary',
      status: 'pending' as const,
      started_at: null,
      finished_at: null,
      error: null,
      detail: null,
    },
  ],
}

const NOTIFICATION_TASK = {
  id: TASK.id,
  goal: TASK.goal,
  status: 'partial' as const,
  elapsed_seconds: 137 * 60,
  completed_actions: 2,
  total_actions: 5,
  latest_observation: TASK.latest_observation,
  error: null,
}

export function LongRunningAgentsDemo() {
  const [panelOpen, setPanelOpen] = useState(false)
  const [notificationOpen, setNotificationOpen] = useState(true)

  return (
    <div className="min-h-full p-8">
      <header className="mb-8 flex items-start justify-between gap-6">
        <div>
          <h1 className="text-lg">Long-running agents</h1>
          <p className="mt-1 max-w-prose text-sm text-on-surface/60">
            One task, four surfaces. The task is <em>partial</em> — two actions
            done, one failed, one genuinely unknown — because that is the state
            the backend models and the UI currently cannot express.
          </p>
        </div>

        {/* In the real shell this sits in TitleBar, visible from every section.
            A task you can only see from the conversation that started it is a
            task you have to remember to go back to. */}
        <BackgroundTaskIndicator
          task={TASK}
          onExpand={() => setPanelOpen(true)}
          onPause={() => {}}
          onResume={() => {}}
          onCancel={() => {}}
        />
      </header>

      <section className="mb-10">
        <h2 className="mb-3 text-xs uppercase tracking-widest text-on-surface/50">
          On return — catch-up summary
        </h2>
        <CatchUpSummary
          goal={TASK.goal}
          status={TASK.status}
          elapsed_since_update="12m"
          completed_count={2}
          total_actions={TASK.actions.length}
          failed_actions={[
            {
              action: 'Cross-check against the live route table',
              error: 'Connection refused — backend was not running at :4109',
            },
          ]}
          unresolved_actions={[
            {
              action: 'Resolve inherited timeout for OmniRoute',
              status: 'unknown',
              detail:
                'Static resolution hit a runtime-computed value. Neither confirmed nor refuted.',
            },
          ]}
          known_facts={TASK.known}
          latest_observation={TASK.latest_observation}
          next_action={TASK.next_actions[0]}
          onVerify={() => {}}
          onResume={() => {}}
        />
      </section>

      <section>
        <h2 className="mb-3 text-xs uppercase tracking-widest text-on-surface/50">
          Full task panel
        </h2>
        <button
          type="button"
          onClick={() => setPanelOpen(true)}
          className="border border-on-surface/25 px-3 py-1.5 text-sm hover:bg-on-surface/5"
        >
          Open task panel
        </button>
      </section>

      {panelOpen && (
        <TaskPanel
          task={TASK}
          onClose={() => setPanelOpen(false)}
          onPause={() => {}}
          onResume={() => {}}
          onCancel={() => setPanelOpen(false)}
          onRetarget={() => {}}
        />
      )}

      {notificationOpen && (
        <TaskNotification
          task={NOTIFICATION_TASK}
          onDismiss={() => setNotificationOpen(false)}
          onOpen={() => {
            setNotificationOpen(false)
            setPanelOpen(true)
          }}
        />
      )}
    </div>
  )
}

export default LongRunningAgentsDemo
