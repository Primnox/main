import { useEffect, useState } from 'react';
import { AlertTriangle, CheckCircle2, Circle, Clock, X } from 'lucide-react';
import { api, type TaskRecord } from '../lib/crs';

/* Work the assistant thinks it is still in the middle of.
 *
 * v2/task_state.py has tracked this since it landed and nothing ever showed
 * it, so a task could be half-done across a dozen turns with no way to see
 * that from the interface. This is the smallest surface that fixes it.
 *
 * It lives in the title bar rather than in the conversation because a task you
 * can only see from the conversation that started it is a task you have to
 * remember to go back to — which is the failure the module exists to prevent.
 *
 * Polled, not streamed. Task state changes on the order of tool calls, not
 * tokens, and adding a second socket to carry it would be a lot of machinery
 * for a row that updates every few seconds. The interval stops while the tab
 * is hidden: a backgrounded window polling forever is how a local app ends up
 * with a mysterious idle CPU cost.
 */

const POLL_MS = 5000;

function StatusMark({ status }: { status: TaskRecord['status'] }) {
  // Icon plus word, never colour alone. A task row is exactly the kind of
  // dense telemetry where a red dot is the only thing distinguishing "failed"
  // from "running", and DESIGN.md holds that as a defect.
  switch (status) {
    case 'active':
      return <Clock size={11} className="shrink-0 px-spin text-on-surface/60" aria-hidden="true" />;
    case 'blocked':
      return <AlertTriangle size={11} className="shrink-0 text-warn" aria-hidden="true" />;
    case 'completed':
      return <CheckCircle2 size={11} className="shrink-0 text-success" aria-hidden="true" />;
    case 'failed':
      return <AlertTriangle size={11} className="shrink-0 text-error" aria-hidden="true" />;
    case 'partial':
      return <AlertTriangle size={11} className="shrink-0 text-warn" aria-hidden="true" />;
    default:
      return <Circle size={11} className="shrink-0 text-on-surface/40" aria-hidden="true" />;
  }
}

function counts(task: TaskRecord) {
  const done = task.actions.filter(a => a.status === 'completed').length;
  const failed = task.actions.filter(a => a.status === 'failed').length;
  // partial and unknown are neither done nor failed, and rounding them into
  // either is precisely what the four-valued model exists to stop.
  const unresolved = task.actions.filter(
    a => a.status === 'partial' || a.status === 'unknown'
      || a.status === 'running' || a.status === 'pending',
  ).length;
  return { done, failed, unresolved, total: task.actions.length };
}

export function TaskIndicator() {
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const read = async () => {
      try {
        const { tasks } = await api.tasks();
        if (live) setTasks(tasks ?? []);
      } catch {
        // The backend being down is already reported by the connection dot in
        // the rail. A second, louder complaint in the title bar would be the
        // same news twice.
        if (live) setTasks([]);
      }
    };

    // The first read ignores visibility; only the repeats respect it. Skipping
    // it while hidden meant a window that started backgrounded — restored from
    // a previous session, launched minimised, opened in an unfocused tab —
    // showed no tasks until it was focused AND a full interval had passed.
    // Measured: the pane reports visibilityState "hidden" and the indicator
    // never populated at all.
    const tick = async () => {
      if (!live) return;
      if (document.visibilityState === 'visible') await read();
      timer = setTimeout(tick, POLL_MS);
    };

    read();
    timer = setTimeout(tick, POLL_MS);

    // Coming back to the window should not cost up to a full interval of
    // staring at stale counts.
    const onVisible = () => { if (document.visibilityState === 'visible') read(); };
    document.addEventListener('visibilitychange', onVisible);

    return () => {
      live = false;
      if (timer) clearTimeout(timer);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, []);

  if (tasks.length === 0) return null;

  const lead = tasks[0];
  const { done, total } = counts(lead);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        aria-label={`${tasks.length} open task${tasks.length === 1 ? '' : 's'}`}
        className="px-interactive flex items-center gap-1.5 rounded border border-on-surface/15
                   px-2 py-0.5 text-[11px] text-on-surface/70 hover:text-on-surface"
      >
        <StatusMark status={lead.status} />
        <span className="max-w-40 truncate">{lead.goal}</span>
        <span className="tabular-nums text-on-surface/50">{done}/{total}</span>
        {tasks.length > 1 && (
          <span className="tabular-nums text-on-surface/50">+{tasks.length - 1}</span>
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Open tasks"
          className="absolute right-0 top-full z-50 mt-1 w-96 border border-on-surface/20 bg-surface"
        >
          <header className="flex items-center justify-between border-b border-on-surface/15 px-3 py-2">
            <span className="px-label">Open tasks</span>
            <button
              type="button" onClick={() => setOpen(false)} aria-label="Close"
              className="px-interactive text-on-surface/50 hover:text-on-surface"
            >
              <X size={12} aria-hidden="true" />
            </button>
          </header>

          <ul role="list" className="max-h-96 overflow-auto custom-scrollbar">
            {tasks.map(task => <TaskRow key={task.id} task={task} />)}
          </ul>
        </div>
      )}
    </div>
  );
}

function TaskRow({ task }: { task: TaskRecord }) {
  const { done, failed, unresolved, total } = counts(task);

  return (
    <li className="border-b border-on-surface/10 px-3 py-2 last:border-b-0">
      <div className="flex items-center gap-2">
        <StatusMark status={task.status} />
        <span className="min-w-0 flex-1 truncate text-[12px]">{task.goal}</span>
        <span className="shrink-0 text-[11px] uppercase tracking-wider text-on-surface/50">
          {task.status}
        </span>
      </div>

      <div className="mt-1 flex items-center gap-3 text-[11px] tabular-nums text-on-surface/55">
        <span>{done}/{total} done</span>
        {failed > 0 && <span className="text-error">{failed} failed</span>}
        {/* Shown even though it is the least alarming number. A summary that
            counts only done and failed silently rounds partial and unknown
            into one or the other. */}
        {unresolved > 0 && <span className="text-warn">{unresolved} unresolved</span>}
      </div>

      {task.latest_observation && (
        <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-on-surface/60">
          {task.latest_observation}
        </p>
      )}

      {task.next_actions.length > 0 && (
        <p className="mt-1 truncate text-[11px] text-on-surface/50">
          Next: {task.next_actions[0]}
        </p>
      )}
    </li>
  );
}
