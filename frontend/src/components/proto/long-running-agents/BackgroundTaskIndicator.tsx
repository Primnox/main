import { motion, AnimatePresence } from 'motion/react';
import { AlertCircle, CheckCircle, Clock, Pause, Play, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * BackgroundTaskIndicator
 *
 * A small badge in the header showing that a background task is running.
 * Clicking expands to show the full task panel.
 *
 * This is Phase 1 of the long-running agents UI: minimal, scannable indicator
 * with quick access to the full view.
 */

interface TaskRecord {
  id: string;
  goal: string;
  status: 'active' | 'blocked' | 'completed' | 'failed' | 'partial' | 'abandoned';
  created_at: string;
  updated_at: string;
  latest_observation: string | null;
  next_actions: string[];
  actions: Array<{
    id: string;
    description: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'unknown' | 'skipped';
    started_at: string | null;
    finished_at: string | null;
    error: string | null;
  }>;
}

// createdAt is nullable because the indicator renders before a task exists, and
// a hook cannot be called conditionally — the caller passes null rather than
// skipping the call.
function useElapsedTime(createdAt: string | null) {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!createdAt) return;

    const calculate = () => {
      const start = new Date(createdAt);
      setElapsed(Math.floor((Date.now() - start.getTime()) / 1000));
    };

    calculate();
    const interval = setInterval(calculate, 1000);
    return () => clearInterval(interval);
  }, [createdAt]);

  const hours = Math.floor(elapsed / 3600);
  const mins = Math.floor((elapsed % 3600) / 60);
  const secs = elapsed % 60;

  if (hours > 0) return `${hours}h ${mins}m`;
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

function StatusIcon({ status }: { status: TaskRecord['status'] }) {
  switch (status) {
    case 'active':
    case 'blocked':
      return <Clock size={12} className="animate-spin text-primary" />;
    case 'completed':
      return <CheckCircle size={12} className="text-success" />;
    case 'failed':
      return <AlertCircle size={12} className="text-error" />;
    case 'partial':
      return <AlertCircle size={12} className="text-warn" />;
    default:
      return <Clock size={12} className="text-on-surface/50" />;
  }
}

function CompletedCount({ actions }: { actions: TaskRecord['actions'] }) {
  const completed = actions.filter(a => a.status === 'completed').length;
  return `${completed}/${actions.length}`;
}

interface Props {
  task: TaskRecord | null;
  onExpand: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
}

export function BackgroundTaskIndicator({
  task,
  onExpand,
  onPause,
  onResume,
  onCancel,
}: Props) {
  const [showActions, setShowActions] = useState(false);
  const elapsed = useElapsedTime(task?.created_at ?? null);

  if (!task) return null;

  const isPaused = task.status === 'blocked';
  const isRunning = task.status === 'active';

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.9 }}
        transition={{ duration: 0.2 }}
        className="relative"
      >
        <div className="flex items-center gap-2 rounded-lg border border-on-surface/15 bg-on-surface/[0.04] px-3 py-2">
          {/* Icon and status */}
          <button
            onClick={onExpand}
            className="flex items-center gap-2 hover:opacity-75 transition-opacity"
            aria-label={`View task: ${task.goal}`}
          >
            <StatusIcon status={task.status} />
            <span className="text-xs font-medium text-on-surface/85 truncate max-w-32">
              {task.goal}
            </span>
          </button>

          {/* Progress */}
          <span className="text-[11px] text-on-surface/60 tabular-nums">
            {CompletedCount({ actions: task.actions })}
          </span>

          {/* Elapsed time */}
          <span className="text-[11px] text-on-surface/50 tabular-nums">
            {elapsed}
          </span>

          {/* Quick actions */}
          <div className="relative">
            <button
              onClick={() => setShowActions(!showActions)}
              className="p-1 hover:bg-on-surface/[0.08] rounded transition-colors"
              aria-label="Task actions"
              aria-expanded={showActions}
            >
              <span className="text-[11px] text-on-surface/50">···</span>
            </button>

            <AnimatePresence>
              {showActions && (
                <motion.div
                  initial={{ opacity: 0, y: -2 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -2 }}
                  transition={{ duration: 0.15 }}
                  className="absolute right-0 top-full mt-1 z-50 rounded-lg border border-on-surface/15 bg-surface shadow-lg"
                >
                  <button
                    onClick={() => {
                      onExpand();
                      setShowActions(false);
                    }}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-on-surface/[0.08] transition-colors rounded-t-lg"
                  >
                    Expand panel
                  </button>
                  {isPaused && onResume && (
                    <button
                      onClick={() => {
                        onResume();
                        setShowActions(false);
                      }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-on-surface/[0.08] transition-colors flex items-center gap-2"
                    >
                      <Play size={12} /> Resume
                    </button>
                  )}
                  {isRunning && onPause && (
                    <button
                      onClick={() => {
                        onPause();
                        setShowActions(false);
                      }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-on-surface/[0.08] transition-colors flex items-center gap-2"
                    >
                      <Pause size={12} /> Pause
                    </button>
                  )}
                  {onCancel && (
                    <button
                      onClick={() => {
                        onCancel();
                        setShowActions(false);
                      }}
                      className="w-full text-left px-3 py-2 text-sm hover:bg-error/10 text-error transition-colors flex items-center gap-2 rounded-b-lg"
                    >
                      <Trash2 size={12} /> Cancel
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
