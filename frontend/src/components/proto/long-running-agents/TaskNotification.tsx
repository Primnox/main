import { motion, AnimatePresence } from 'motion/react';
import { AlertCircle, CheckCircle, ChevronRight, Clock, X } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * TaskNotification
 *
 * Non-blocking notification when a background task completes.
 * Appears in bottom-right, auto-dismisses after 8 seconds.
 * User can click to expand, or dismiss manually.
 *
 * This is Phase 3: notification pattern that doesn't interrupt the user.
 */

interface TaskNotificationProps {
  task: {
    id: string;
    goal: string;
    status: 'completed' | 'failed' | 'partial' | 'abandoned';
    elapsed_seconds: number;
    completed_actions: number;
    total_actions: number;
    latest_observation: string | null;
    error: string | null;
  };
  onDismiss: () => void;
  onOpen: () => void;
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

function NotificationIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle size={16} className="text-success shrink-0" />;
    case 'failed':
      return <AlertCircle size={16} className="text-error shrink-0" />;
    case 'partial':
      return <AlertCircle size={16} className="text-warn shrink-0" />;
    default:
      return <Clock size={16} className="text-on-surface/50 shrink-0" />;
  }
}

function statusMessage(status: string): string {
  switch (status) {
    case 'completed':
      return 'Task completed';
    case 'failed':
      return 'Task failed';
    case 'partial':
      return 'Task partially completed';
    default:
      return 'Task finished';
  }
}

export function TaskNotification({
  task,
  onDismiss,
  onOpen,
}: TaskNotificationProps) {
  const [autoClose, setAutoClose] = useState(true);

  useEffect(() => {
    if (!autoClose) return;
    const timer = setTimeout(onDismiss, 8000);
    return () => clearTimeout(timer);
  }, [autoClose, onDismiss]);

  const borderColor: Record<string, string> = {
    completed: 'border-success/25 bg-success/5',
    failed: 'border-error/25 bg-error/5',
    partial: 'border-warn/25 bg-warn/5',
    abandoned: 'border-on-surface/15 bg-on-surface/5',
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 20, x: 20 }}
        animate={{ opacity: 1, y: 0, x: 0 }}
        exit={{ opacity: 0, y: 20, x: 20 }}
        transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
        onMouseEnter={() => setAutoClose(false)}
        onMouseLeave={() => setAutoClose(true)}
        className={`fixed bottom-4 right-4 w-96 max-w-[calc(100vw-2rem)] rounded-xl border ${borderColor[task.status]} p-4 shadow-lg z-50`}
      >
        <div className="flex items-start gap-3">
          {/* Icon */}
          <NotificationIcon status={task.status} />

          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm text-on-surface">
              {statusMessage(task.status)}
            </p>
            <p className="text-sm text-on-surface/75 mt-0.5 truncate">
              {task.goal}
            </p>

            {/* Summary stats */}
            <div className="flex gap-4 mt-2 text-xs text-on-surface/60">
              <span>
                {task.completed_actions}/{task.total_actions} actions
              </span>
              <span>
                {formatElapsed(task.elapsed_seconds)}
              </span>
            </div>

            {/* Key finding */}
            {task.latest_observation && (
              <p className="text-xs text-on-surface/70 mt-2 line-clamp-2">
                {task.latest_observation}
              </p>
            )}

            {/* Error callout */}
            {task.error && (
              <div className="mt-2 p-2 rounded bg-error/10 border border-error/25">
                <p className="text-xs text-error font-mono truncate">
                  {task.error}
                </p>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={onOpen}
              className="p-1.5 hover:bg-on-surface/[0.08] rounded transition-colors"
              aria-label="View task details"
            >
              <ChevronRight size={14} className="text-on-surface/50" />
            </button>
            <button
              onClick={onDismiss}
              className="p-1.5 hover:bg-on-surface/[0.08] rounded transition-colors"
              aria-label="Dismiss notification"
            >
              <X size={14} className="text-on-surface/50" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
