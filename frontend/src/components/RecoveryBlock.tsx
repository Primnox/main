import { useEffect, useState } from 'react';
import { AlertTriangle, Clock, Key, Zap, RotateCw, X, ChevronDown } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { type TurnError } from '../lib/crs';
import {
  classifyError,
  recoveryMessage,
  type ErrorCategory,
} from '../lib/error_classifier';

export interface RecoveryBlockProps {
  /** The error to display */
  error: TurnError;

  /** Called when user clicks Retry */
  onRetry?: () => void;

  /** Called when user clicks an action button */
  onAction?: (actionType: string) => void;

  /** Called when user dismisses */
  onDismiss?: () => void;

  /** Additional context (e.g., which provider, which tool) */
  context?: {
    provider?: string;
    tool?: string;
    attempt?: number;
    maxAttempts?: number;
  };

  /** Whether to auto-dismiss after this many ms (0 = no auto-dismiss) */
  autoDismissMs?: number;

  /** Compact mode: no expand/collapse, smaller */
  compact?: boolean;
}

const ICON_BY_CATEGORY: Record<ErrorCategory, React.ReactNode> = {
  transient: <Zap size={14} />,
  rate_limited: <Clock size={14} />,
  auth_failed: <Key size={14} />,
  capability_missing: <AlertTriangle size={14} />,
  permission_denied: <AlertTriangle size={14} />,
  quota_exceeded: <AlertTriangle size={14} />,
  timeout: <Clock size={14} />,
  tool_failed: <AlertTriangle size={14} />,
  unsupported: <AlertTriangle size={14} />,
  cancelled: <X size={14} />,
  unknown: <AlertTriangle size={14} />,
};

const COLOR_BY_CATEGORY: Record<ErrorCategory, string> = {
  transient: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  rate_limited: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  auth_failed: 'border-error/25 bg-error/[0.06] text-error',
  capability_missing: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  permission_denied: 'border-error/25 bg-error/[0.06] text-error',
  quota_exceeded: 'border-error/25 bg-error/[0.06] text-error',
  timeout: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  tool_failed: 'border-error/25 bg-error/[0.06] text-error',
  unsupported: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  cancelled: 'border-on-surface/15 bg-on-surface/[0.03] text-on-surface/80',
  unknown: 'border-error/25 bg-error/[0.06] text-error',
};

/**
 * Countdown display for retry backoff.
 * Shows "Retrying in 5s..." and counts down.
 */
function CountdownTimer({ from, onComplete }: { from: number; onComplete: () => void }) {
  const [remaining, setRemaining] = useState(from);

  useEffect(() => {
    if (remaining <= 0) {
      onComplete();
      return;
    }
    const timer = window.setInterval(() => {
      setRemaining(s => Math.max(0, s - 100));
    }, 100);
    return () => clearInterval(timer);
  }, [remaining, onComplete]);

  const seconds = Math.ceil(remaining / 1000);
  return <span className="tabular-nums">{seconds}s</span>;
}

/**
 * RecoveryBlock — shows an error and recovery options.
 *
 * States:
 * - Retrying: automatic backoff + countdown
 * - Failed: show full error + action buttons
 * - Escalated: actionable recovery (add key, grant permission)
 * - Dismissed: hidden
 */
export function RecoveryBlock({
  error,
  onRetry,
  onAction,
  onDismiss,
  context,
  autoDismissMs = 0,
  compact = false,
}: RecoveryBlockProps) {
  const classified = classifyError(error);
  const [expanded, setExpanded] = useState(!compact);
  const [dismissed, setDismissed] = useState(false);
  const [retrying, setRetrying] = useState(false);
  const [retryCountdown, setRetryCountdown] = useState(0);

  // Auto-dismiss after specified time
  useEffect(() => {
    if (autoDismissMs === 0) return;
    const timer = window.setTimeout(() => {
      setDismissed(true);
      onDismiss?.();
    }, autoDismissMs);
    return () => clearTimeout(timer);
  }, [autoDismissMs, onDismiss]);

  if (dismissed) return null;

  const { category, message, actionable, actionLabel, suggestedWait } = classified;
  const colorClass = COLOR_BY_CATEGORY[category];
  const icon = ICON_BY_CATEGORY[category];

  // Defaulting to 1/3 was a fabrication: an unknown attempt count rendered as
  // a confident "Attempt 1/3" against a limit that does not exist for user
  // retries. Unknown now stays undefined and the label is omitted.
  //
  // `maxAttempts` is still honoured where a caller genuinely has one — the
  // provider budget in models/failures.py is a real ceiling — but the backend's
  // turn.failed carries `attempt` alone, because pressing Retry makes a new
  // turn and nothing caps how many times a person may do that.
  const attempt = context?.attempt;
  const maxAttempts = context?.maxAttempts;
  const attemptKnown = attempt !== undefined;
  const attemptsRemain =
    attempt === undefined || maxAttempts === undefined || attempt < maxAttempts;

  const handleRetry = () => {
    if (suggestedWait) {
      setRetrying(true);
      setRetryCountdown(suggestedWait);
    } else {
      onRetry?.();
    }
  };

  const handleRetryCountdownComplete = () => {
    setRetrying(false);
    setRetryCountdown(0);
    onRetry?.();
  };

  const isInfoLevel = category === 'transient' || category === 'rate_limited' || category === 'timeout' || category === 'cancelled';

  if (compact) {
    // Compact: single line, inline with other content
    return (
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-[11px] ${colorClass}`}>
        {icon}
        <span>{recoveryMessage(classified, context)}</span>
        {onRetry && !retrying && (
          <button
            onClick={handleRetry}
            className="ml-2 px-2 py-0.5 hover:bg-black/10 rounded"
            aria-label="Retry"
          >
            <RotateCw size={10} />
          </button>
        )}
        {retrying && (
          <span className="ml-2 text-[10px]">
            <CountdownTimer from={retryCountdown} onComplete={handleRetryCountdownComplete} />
          </span>
        )}
      </div>
    );
  }

  // Full block: collapsible with details
  return (
    <motion.div
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.2 }}
      className={`mb-3 rounded-xl border overflow-hidden ${colorClass}`}
    >
      {/* Header: always visible.
          A row, not a button. The recovery actions are themselves buttons, and
          a button inside a button is invalid HTML — the browser closes the
          outer one early, which in practice meant Retry and Dismiss sat outside
          the element they appeared to be inside and did not reliably click.
          The expand affordance is its own button covering the message. */}
      <div className="w-full flex items-center gap-2.5 px-3.5 py-2.5">
        <button
          type="button"
          onClick={() => setExpanded(!expanded)}
          aria-expanded={expanded}
          className="flex flex-1 min-w-0 items-center gap-2.5 text-left hover:bg-black/[0.03] transition-colors duration-200"
        >
          {icon}

          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium leading-snug">
              {recoveryMessage(classified, context)}
            </p>
            {(retrying || (classified.retryable && attemptKnown && attemptsRemain)) && (
              <p className="text-[11px] opacity-70 mt-0.5">
                {retrying ? (
                  <>Retry in <CountdownTimer from={retryCountdown} onComplete={handleRetryCountdownComplete} /></>
                ) : (
                  <>Attempt {attempt}{maxAttempts !== undefined && <>/{maxAttempts}</>}</>
                )}
              </p>
            )}
          </div>

          {/* Expand/collapse indicator if there's more detail */}
          {message && message.length > 60 && (
            <ChevronDown
              size={12}
              className={`shrink-0 transition-transform duration-200 ${expanded ? 'rotate-180' : ''}`}
            />
          )}
        </button>

        {/* Action buttons in header */}
        <div className="flex items-center gap-1.5">
          {retrying ? (
            <div className="text-[11px] opacity-60">
              <CountdownTimer from={retryCountdown} onComplete={handleRetryCountdownComplete} />
            </div>
          ) : (
            <>
              {classified.retryable && onRetry && attemptsRemain && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRetry();
                  }}
                  className="px-interactive p-1.5 hover:bg-black/10 rounded transition-colors"
                  aria-label="Retry"
                  title="Retry this operation"
                >
                  <RotateCw size={12} />
                </button>
              )}

              {actionable && actionLabel && onAction && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onAction(category);
                  }}
                  className="px-2 py-1 text-[11px] font-medium bg-black/10 hover:bg-black/20 rounded transition-colors"
                  aria-label={actionLabel}
                >
                  {actionLabel}
                </button>
              )}

              {!isInfoLevel && onDismiss && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setDismissed(true);
                    onDismiss();
                  }}
                  className="px-interactive p-1.5 hover:bg-black/10 rounded transition-colors"
                  aria-label="Dismiss"
                  title="Dismiss this error"
                >
                  <X size={12} />
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Expanded details */}
      <AnimatePresence>
        {expanded && message && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="border-t border-black/[0.05] overflow-hidden"
          >
            <div className="px-3.5 py-2.5 bg-black/[0.01]">
              <p className="text-[12px] leading-relaxed opacity-80">{message}</p>

              {/* Context details: provider, tool, etc. */}
              {(context?.provider || context?.tool) && (
                <div className="mt-2 pt-2 border-t border-black/[0.05] text-[11px] opacity-70 space-y-1">
                  {context.provider && (
                    <p>
                      <span className="font-medium">Provider:</span> {context.provider}
                    </p>
                  )}
                  {context.tool && (
                    <p>
                      <span className="font-medium">Tool:</span> {context.tool}
                    </p>
                  )}
                </div>
              )}

              {/* Recovery suggestion */}
              {!isInfoLevel && (
                <div className="mt-3 pt-3 border-t border-black/[0.05]">
                  <div className="text-[11px] opacity-70 space-y-2">
                    {classified.retryable && (
                      <p>✓ This operation can be retried automatically.</p>
                    )}
                    {classified.fallbackable && (
                      <p>✓ Primnox can try another provider if available.</p>
                    )}
                    {!classified.retryable && !actionable && (
                      <p>
                        This error needs investigation. {' '}
                        <button
                          onClick={() => onAction?.(category)}
                          className="font-medium hover:underline"
                        >
                          View details
                        </button>
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/**
 * Quick status line for minor issues (fits inline with running status).
 * Use this for degraded states (retrying on fallback, rate limited, etc.)
 */
export function RecoveryStatusLine({ error, context }: { error: TurnError; context?: RecoveryBlockProps['context'] }) {
  const classified = classifyError(error);
  const message = recoveryMessage(classified, context);

  if (classified.severity === 'info') {
    return (
      <p className="text-[11px] text-on-surface/60 flex items-center gap-1">
        {ICON_BY_CATEGORY[classified.category]}
        {message}
      </p>
    );
  }

  return null;
}
