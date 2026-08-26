import { motion } from 'motion/react';
import {
  AlertCircle,
  CheckCircle,
  ChevronDown,
  Clock,
  Edit2,
  HelpCircle,
  Pause,
  Play,
  Trash2,
  Zap,
} from 'lucide-react';
import { useState } from 'react';

/**
 * TaskPanel
 *
 * Full view of a background task. Shows:
 * - Task goal and status
 * - Progress through actions
 * - Constraints and known facts
 * - Latest observation
 * - Next action with candidates
 * - Error callouts and recovery options
 *
 * This is Phase 2: detailed progress tracking with error recovery.
 */

interface TaskRecord {
  id: string;
  goal: string;
  status: 'active' | 'blocked' | 'completed' | 'failed' | 'partial' | 'abandoned';
  constraints: string[];
  created_at: string;
  updated_at: string;
  latest_observation: string | null;
  next_actions: string[];
  known: string[];
  actions: Array<{
    id: string;
    sequence: number;
    description: string;
    status: 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'unknown' | 'skipped';
    started_at: string | null;
    finished_at: string | null;
    error: string | null;
    detail: string | null;
  }>;
}

function formatTime(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - date.getTime();

  if (diff < 60000) return 'just now';
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
  return date.toLocaleDateString();
}

function calculateDuration(started: string | null, finished: string | null): string {
  if (!started || !finished) return '—';
  const start = new Date(started);
  const end = new Date(finished);
  const diff = end.getTime() - start.getTime();

  if (diff < 1000) return '< 1s';
  if (diff < 60000) return `${Math.floor(diff / 1000)}s`;
  if (diff < 3600000) return `${Math.floor(diff / 60000)}m`;
  return `${Math.floor(diff / 3600000)}h`;
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    completed: 'bg-success/10 text-success border-success/25',
    running: 'bg-primary/10 text-primary border-primary/25 animate-pulse',
    failed: 'bg-error/10 text-error border-error/25',
    partial: 'bg-warn/10 text-warn border-warn/25',
    unknown: 'bg-warn/10 text-warn border-warn/25',
    pending: 'bg-on-surface/5 text-on-surface/50 border-on-surface/15',
    skipped: 'bg-on-surface/5 text-on-surface/50 border-on-surface/15 line-through',
  };

  return (
    <span className={`px-2 py-1 rounded text-[11px] font-medium border ${styles[status] || styles.pending}`}>
      {status}
    </span>
  );
}

function ActionIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckCircle size={14} className="text-success" />;
    case 'failed':
      return <AlertCircle size={14} className="text-error" />;
    case 'partial':
      return <AlertCircle size={14} className="text-warn" />;
    case 'unknown':
      return <HelpCircle size={14} className="text-warn" />;
    case 'running':
      return <Clock size={14} className="animate-spin text-primary" />;
    default:
      return <Circle size={14} className="text-on-surface/30" />;
  }
}

function Circle({ className }: any) {
  return <div className={`w-3.5 h-3.5 rounded-full border border-current ${className}`} />;
}

interface ActionRowProps {
  action: TaskRecord['actions'][0];
  index: number;
  isNext: boolean;
  expanded: boolean;
  onToggle: () => void;
}

function ActionRow({ action, index, isNext, expanded, onToggle }: ActionRowProps) {
  return (
    <div>
      <button
        onClick={onToggle}
        className="w-full text-left p-3 hover:bg-on-surface/[0.05] transition-colors rounded-lg flex items-start gap-3 group"
      >
        {/* Index */}
        <span className="text-[11px] text-on-surface/50 font-mono mt-0.5 w-6 shrink-0">
          {index + 1}.
        </span>

        {/* Status icon */}
        <div className="mt-0.5 shrink-0">
          <ActionIcon status={action.status} />
        </div>

        {/* Description */}
        <div className="min-w-0 flex-1">
          <p className="text-sm font-medium text-on-surface/85 group-hover:text-on-surface">
            {action.description}
          </p>
          {isNext && action.status === 'pending' && (
            <p className="text-xs text-primary mt-0.5 flex items-center gap-1">
              <Zap size={11} /> Next to run
            </p>
          )}
        </div>

        {/* Status badge */}
        <StatusBadge status={action.status} />

        {/* Duration */}
        {action.status !== 'pending' && action.status !== 'skipped' && (
          <span className="text-xs text-on-surface/50 font-mono shrink-0">
            {calculateDuration(action.started_at, action.finished_at)}
          </span>
        )}

        {/* Expand arrow */}
        {(action.error || action.detail) && (
          <motion.div
            animate={{ rotate: expanded ? 180 : 0 }}
            transition={{ duration: 0.2 }}
          >
            <ChevronDown size={14} className="text-on-surface/30 shrink-0" />
          </motion.div>
        )}
      </button>

      {/* Expanded detail */}
      {expanded && (action.error || action.detail) && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          exit={{ opacity: 0, height: 0 }}
          transition={{ duration: 0.2 }}
          className="pl-11 pr-3 pb-3"
        >
          {action.error && (
            <div className="rounded-lg border border-error/25 bg-error/5 p-3 text-sm text-error/90">
              <p className="font-medium mb-1">Error</p>
              <p className="text-[12px] font-mono">{action.error}</p>
            </div>
          )}
          {action.detail && (
            <div className="rounded-lg border border-on-surface/15 bg-on-surface/5 p-3 text-sm text-on-surface/75 mt-2">
              <p className="font-medium mb-1">Detail</p>
              <p className="text-[12px]">{action.detail}</p>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
}

interface Props {
  task: TaskRecord;
  onClose: () => void;
  onPause?: () => void;
  onResume?: () => void;
  onCancel?: () => void;
  onRetarget?: (newGoal: string) => void;
}

export function TaskPanel({
  task,
  onClose,
  onPause,
  onResume,
  onCancel,
  onRetarget,
}: Props) {
  const [expandedAction, setExpandedAction] = useState<number | null>(null);
  const [showRetarget, setShowRetarget] = useState(false);
  const [retargetText, setRetargetText] = useState(task.goal);

  const completedCount = task.actions.filter(a => a.status === 'completed').length;
  const failedCount = task.actions.filter(a => a.status === 'failed').length;
  const unresolvedCount = task.actions.filter(
    a => ['pending', 'running', 'unknown', 'partial'].includes(a.status)
  ).length;

  const nextAction = task.actions.find(a =>
    ['unknown', 'partial', 'running', 'pending'].includes(a.status)
  );

  const isPaused = task.status === 'blocked';
  const isRunning = task.status === 'active';

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 20 }}
      transition={{ duration: 0.3 }}
      className="fixed inset-y-0 right-0 w-96 max-w-[90vw] border-l border-on-surface/10 bg-surface flex flex-col z-40"
    >
      {/* Header */}
      <div className="border-b border-on-surface/10 p-4 shrink-0">
        <div className="flex items-start justify-between mb-3">
          <h2 className="text-lg font-semibold text-on-surface pr-2">{task.goal}</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-on-surface/[0.08] rounded transition-colors shrink-0"
            aria-label="Close panel"
          >
            <span className="text-[18px]">×</span>
          </button>
        </div>

        {/* Status and stats */}
        <div className="flex items-center gap-2 mb-3">
          <StatusBadge status={task.status} />
          <span className="text-xs text-on-surface/60">
            {completedCount}/{task.actions.length} done
          </span>
          {failedCount > 0 && (
            <span className="text-xs text-error">
              {failedCount} failed
            </span>
          )}
          {/* Unresolved is shown even though it is the least alarming number.
              task_state.py treats unknown and partial as outcomes in their own
              right, and a header that counts only done and failed silently
              rounds them into one or the other — which is the exact conflation
              the four-valued model exists to prevent. */}
          {unresolvedCount > 0 && (
            <span className="text-xs text-warn">
              {unresolvedCount} unresolved
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex gap-2">
          {isPaused && onResume && (
            <button
              onClick={onResume}
              className="flex-1 px-3 py-2 rounded-lg border border-primary/25 bg-primary/10 text-primary text-sm font-medium hover:bg-primary/15 transition-colors flex items-center justify-center gap-2"
            >
              <Play size={12} /> Resume
            </button>
          )}
          {isRunning && onPause && (
            <button
              onClick={onPause}
              className="flex-1 px-3 py-2 rounded-lg border border-on-surface/15 text-on-surface/85 text-sm font-medium hover:bg-on-surface/[0.08] transition-colors flex items-center justify-center gap-2"
            >
              <Pause size={12} /> Pause
            </button>
          )}
          {onCancel && (
            <button
              onClick={onCancel}
              className="px-3 py-2 rounded-lg border border-error/25 text-error text-sm font-medium hover:bg-error/[0.08] transition-colors"
              aria-label="Cancel task"
            >
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto">
        {/* Constraints */}
        {task.constraints.length > 0 && (
          <div className="px-4 py-3 border-b border-on-surface/10">
            <p className="text-xs font-medium text-on-surface/60 mb-2">Constraints</p>
            <ul className="space-y-1">
              {task.constraints.map((c, i) => (
                <li key={i} className="text-xs text-on-surface/75 flex items-start gap-2">
                  <span className="text-on-surface/40 mt-0.5">·</span>
                  <span>{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Latest observation */}
        {task.latest_observation && (
          <div className="px-4 py-3 border-b border-on-surface/10 bg-primary/5">
            <p className="text-xs font-medium text-primary mb-2">Latest observation</p>
            <p className="text-sm text-on-surface/85 leading-relaxed">
              {task.latest_observation}
            </p>
            <p className="text-xs text-on-surface/50 mt-1">
              {formatTime(task.updated_at)}
            </p>
          </div>
        )}

        {/* Known facts */}
        {task.known.length > 0 && (
          <div className="px-4 py-3 border-b border-on-surface/10">
            <p className="text-xs font-medium text-on-surface/60 mb-2">Known</p>
            <ul className="space-y-1">
              {task.known.map((k, i) => (
                <li key={i} className="text-xs text-on-surface/75 flex items-start gap-2">
                  <span className="text-on-surface/40 mt-0.5">·</span>
                  <span>{k}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions timeline */}
        <div className="px-4 py-3">
          <p className="text-xs font-medium text-on-surface/60 mb-3">Progress</p>
          <div className="space-y-1">
            {task.actions.map((action, i) => (
              <ActionRow
                key={action.id}
                action={action}
                index={i}
                isNext={action.id === nextAction?.id}
                expanded={expandedAction === i}
                onToggle={() => setExpandedAction(expandedAction === i ? null : i)}
              />
            ))}
          </div>
        </div>

        {/* Next action candidates */}
        {task.next_actions.length > 0 && (
          <div className="px-4 py-3 border-t border-on-surface/10">
            <p className="text-xs font-medium text-on-surface/60 mb-2">Candidates</p>
            <ul className="space-y-1">
              {task.next_actions.map((a, i) => (
                <li key={i} className="text-xs text-on-surface/75 flex items-start gap-2">
                  <span className="text-primary mt-0.5">→</span>
                  <span>{a}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Footer with retarget option */}
      <div className="border-t border-on-surface/10 p-4 shrink-0">
        {!showRetarget && (
          <button
            onClick={() => setShowRetarget(true)}
            className="w-full px-3 py-2 rounded-lg border border-on-surface/15 text-on-surface/70 text-sm font-medium hover:bg-on-surface/[0.05] transition-colors flex items-center justify-center gap-2"
          >
            <Edit2 size={12} /> Retarget
          </button>
        )}
        {showRetarget && (
          <div className="space-y-2">
            <textarea
              value={retargetText}
              onChange={(e) => setRetargetText(e.target.value)}
              className="w-full px-3 py-2 rounded-lg border border-primary/25 bg-primary/5 text-sm font-mono text-on-surface resize-none focus:outline-none focus:ring-1 focus:ring-primary"
              rows={3}
            />
            <div className="flex gap-2">
              <button
                onClick={() => {
                  if (onRetarget && retargetText !== task.goal) {
                    onRetarget(retargetText);
                  }
                  setShowRetarget(false);
                }}
                className="flex-1 px-3 py-2 rounded-lg border border-primary/25 bg-primary/10 text-primary text-sm font-medium hover:bg-primary/15 transition-colors"
              >
                Retarget
              </button>
              <button
                onClick={() => {
                  setRetargetText(task.goal);
                  setShowRetarget(false);
                }}
                className="flex-1 px-3 py-2 rounded-lg border border-on-surface/15 text-on-surface/70 text-sm font-medium hover:bg-on-surface/[0.05] transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </motion.div>
  );
}
