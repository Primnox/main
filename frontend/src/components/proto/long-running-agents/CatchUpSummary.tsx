import { motion } from 'motion/react';
import { AlertTriangle, BookOpen, CheckCircle, Clock, TrendingUp } from 'lucide-react';

/**
 * CatchUpSummary
 *
 * Compact resume-view shown when a user returns to a task after a long gap.
 * Answers: "What did I leave it doing? What's changed since I left?"
 *
 * Shaped like task_state.snapshot() — small enough for context construction,
 * dense enough to make resumption fast.
 *
 * This is Phase 4: resumption and verification.
 */

interface CatchUpSummaryProps {
  goal: string;
  status: string;
  elapsed_since_update: string; // e.g., "2h 15m"
  completed_count: number;
  total_actions: number;
  failed_actions: Array<{ action: string; error: string }>;
  unresolved_actions: Array<{
    action: string;
    status: string;
    detail: string;
  }>;
  known_facts: string[];
  latest_observation: string;
  next_action: string | null;
  onVerify?: () => void;
  onResume?: () => void;
}

export function CatchUpSummary({
  goal,
  status,
  elapsed_since_update,
  completed_count,
  total_actions,
  failed_actions,
  unresolved_actions,
  known_facts,
  latest_observation,
  next_action,
  onVerify,
  onResume,
}: CatchUpSummaryProps) {
  const progress = Math.round((completed_count / total_actions) * 100);
  const needsVerification = unresolved_actions.length > 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="rounded-xl border border-on-surface/10 bg-on-surface/[0.02] p-4 space-y-3"
    >
      {/* Header with status */}
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h3 className="font-semibold text-sm text-on-surface">{goal}</h3>
          <span className={`px-2 py-0.5 rounded text-[11px] font-medium border ${
            status === 'completed'
              ? 'bg-success/10 text-success border-success/25'
              : status === 'partial'
              ? 'bg-warn/10 text-warn border-warn/25'
              : status === 'failed'
              ? 'bg-error/10 text-error border-error/25'
              : 'bg-primary/10 text-primary border-primary/25'
          }`}>
            {status}
          </span>
        </div>
        <p className="text-xs text-on-surface/50">
          Last updated {elapsed_since_update}
        </p>
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex items-center justify-between mb-1">
          <p className="text-xs text-on-surface/60">Progress</p>
          <p className="text-xs font-mono text-on-surface/60">{progress}%</p>
        </div>
        <div className="w-full h-2 rounded-full bg-on-surface/10">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            transition={{ duration: 0.5 }}
            className="h-full rounded-full bg-primary"
          />
        </div>
        <p className="text-xs text-on-surface/50 mt-1">
          {completed_count} of {total_actions} actions completed
        </p>
      </div>

      {/* Verification alert */}
      {needsVerification && (
        <div className="rounded-lg border border-warn/25 bg-warn/5 p-3">
          <div className="flex items-start gap-2 mb-2">
            <AlertTriangle size={14} className="text-warn mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-xs font-medium text-warn">Needs verification</p>
              <p className="text-[11px] text-on-surface/70 mt-0.5">
                {unresolved_actions.length} action(s) are unknown or partial. Check the system before proceeding.
              </p>
            </div>
          </div>
          {onVerify && (
            <button
              onClick={onVerify}
              className="text-xs px-2 py-1 rounded border border-warn/25 text-warn hover:bg-warn/10 transition-colors"
            >
              Verify now
            </button>
          )}
        </div>
      )}

      {/* Completed actions */}
      {completed_count > 0 && (
        <div>
          <p className="text-xs font-medium text-success mb-1">
            <CheckCircle size={12} className="inline mr-1" />
            Completed
          </p>
          <p className="text-xs text-on-surface/70 truncate">
            {completed_count} action{completed_count !== 1 ? 's' : ''} done
          </p>
        </div>
      )}

      {/* Failed actions */}
      {failed_actions.length > 0 && (
        <div>
          <p className="text-xs font-medium text-error mb-1">Failed</p>
          {failed_actions.slice(0, 2).map((f, i) => (
            <div key={i} className="text-xs text-on-surface/70 mb-1">
              <p className="font-mono text-[11px] text-error/80 truncate">
                {f.action}
              </p>
              <p className="text-[11px] text-error/60 truncate">
                {f.error}
              </p>
            </div>
          ))}
          {failed_actions.length > 2 && (
            <p className="text-xs text-on-surface/50">
              ... and {failed_actions.length - 2} more
            </p>
          )}
        </div>
      )}

      {/* Latest observation */}
      {latest_observation && (
        <div className="rounded-lg border border-primary/25 bg-primary/5 p-2.5">
          <p className="text-xs font-medium text-primary mb-1">
            <TrendingUp size={12} className="inline mr-1" />
            Latest finding
          </p>
          <p className="text-xs text-on-surface/75 line-clamp-2">
            {latest_observation}
          </p>
        </div>
      )}

      {/* Known facts */}
      {known_facts.length > 0 && (
        <div>
          <p className="text-xs font-medium text-on-surface/60 mb-1">
            <BookOpen size={12} className="inline mr-1" />
            What we know
          </p>
          <ul className="space-y-0.5">
            {known_facts.slice(0, 2).map((fact, i) => (
              <li key={i} className="text-xs text-on-surface/70 flex items-start gap-2">
                <span className="text-on-surface/40 mt-0.5">·</span>
                <span className="truncate">{fact}</span>
              </li>
            ))}
            {known_facts.length > 2 && (
              <li className="text-xs text-on-surface/50">
                ... and {known_facts.length - 2} more
              </li>
            )}
          </ul>
        </div>
      )}

      {/* Next action */}
      {next_action && (
        <div>
          <p className="text-xs font-medium text-on-surface/60 mb-1">
            <Clock size={12} className="inline mr-1" />
            Next
          </p>
          <p className="text-xs text-on-surface/75">
            → {next_action}
          </p>
        </div>
      )}

      {/* Resume button */}
      {onResume && (
        <button
          onClick={onResume}
          className="w-full px-3 py-2 rounded-lg border border-primary/25 bg-primary/10 text-primary text-sm font-medium hover:bg-primary/15 transition-colors"
        >
          Resume task
        </button>
      )}
    </motion.div>
  );
}
