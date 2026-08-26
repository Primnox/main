import React, { useMemo } from 'react';
import { AlertTriangle, Repeat2, Copy, ChevronDown, ChevronUp } from 'lucide-react';
import { ArtifactCard, type CardAction, type CardMetadata } from './ArtifactCard';

/**
 * ErrorCard
 * Display error messages with:
 * - Error type and message
 * - Stack trace (collapsible)
 * - Related context (tool, input, etc.)
 * - Retry action
 * - Auto-expand on error
 */

export interface ErrorCardProps {
  id: string;
  title: string;
  errorMessage: string;
  errorType?: string;
  stackTrace?: string;
  context?: {
    tool?: string;
    input?: string;
    timestamp?: number;
  };
  onRetry?: () => void | Promise<void>;
  isMobile?: boolean;
}

export const ErrorCard: React.FC<ErrorCardProps> = ({
  id,
  title,
  errorMessage,
  errorType = 'Error',
  stackTrace,
  context,
  onRetry,
  isMobile = false,
}) => {
  const metadata: CardMetadata = useMemo(
    () => ({
      status: 'error',
      errorMessage,
      timestamp: context?.timestamp,
    }),
    [errorMessage, context?.timestamp]
  );

  const actions: CardAction[] = useMemo(() => {
    const acts: CardAction[] = [];

    if (onRetry) {
      acts.push({
        id: 'retry',
        label: 'Retry',
        icon: <Repeat2 size={14} />,
        level: 'core',
        onClick: onRetry,
      });
    }

    acts.push({
      id: 'copy-error',
      label: 'Copy Error',
      icon: <Copy size={14} />,
      level: 'common',
      onClick: () => {
        const errorText = `${errorType}: ${errorMessage}${stackTrace ? '\n\n' + stackTrace : ''}`;
        navigator.clipboard.writeText(errorText);
      },
    });

    return acts;
  }, [onRetry, errorType, errorMessage, stackTrace]);

  const errorHeader = useMemo(() => {
    return (
      <div className="space-y-2">
        <div className="flex items-start gap-2">
          <AlertTriangle size={16} className="text-error mt-0.5 flex-shrink-0" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-error">{errorType}</div>
            <div className="text-sm text-on-surface mt-1">{errorMessage}</div>
          </div>
        </div>
      </div>
    );
  }, [errorType, errorMessage]);

  const contextSection = useMemo(() => {
    if (!context) return null;
    return (
      <div className="space-y-1.5 text-xs">
        {context.tool && (
          <div>
            <span className="text-on-surface/60">Tool:</span> <span className="font-mono text-on-surface/80">{context.tool}</span>
          </div>
        )}
        {context.input && (
          <div>
            <span className="text-on-surface/60">Input:</span>
            <pre className="mt-1 bg-on-surface/[0.02] p-2 rounded border border-on-surface/[0.05] font-mono text-[10px] text-on-surface/70 max-h-32 overflow-auto">
              {context.input}
            </pre>
          </div>
        )}
        {context.timestamp && (
          <div>
            <span className="text-on-surface/60">When:</span> <span className="text-on-surface/80">{new Date(context.timestamp).toLocaleString()}</span>
          </div>
        )}
      </div>
    );
  }, [context]);

  const stackTraceSection = useMemo(() => {
    if (!stackTrace) return null;
    return (
      <div className="space-y-2">
        <h4 className="text-xs font-semibold text-on-surface/70">Stack Trace</h4>
        <pre className="bg-on-surface/[0.02] border border-on-surface/[0.05] rounded text-[9px] font-mono text-on-surface/70 overflow-x-auto p-2 leading-relaxed max-h-48">
          {stackTrace}
        </pre>
      </div>
    );
  }, [stackTrace]);

  return (
    <ArtifactCard
      id={id}
      type="error"
      title={title}
      metadata={metadata}
      actions={actions}
      coreAction={onRetry ? { label: 'Retry', icon: <Repeat2 size={16} />, onClick: onRetry } : undefined}
      isMobile={isMobile}
      variant="card"
    >
      <div className="space-y-4">
        {errorHeader}

        {contextSection && (
          <div className="border-t border-on-surface/[0.07] pt-3">
            <div className="text-xs font-semibold text-on-surface/70 mb-2">Context</div>
            {contextSection}
          </div>
        )}

        {stackTraceSection && (
          <div className="border-t border-on-surface/[0.07] pt-3">
            {stackTraceSection}
          </div>
        )}

        {/* Recovery suggestions */}
        <div className="border-t border-on-surface/[0.07] pt-3 px-3 py-2 bg-warn/10 rounded">
          <h4 className="text-xs font-semibold text-warn mb-1">Recovery Options</h4>
          <ul className="text-xs text-on-surface/80 space-y-1 list-disc list-inside">
            <li>Review the error message and input parameters</li>
            {onRetry && <li>Click "Retry" to run the operation again</li>}
            <li>Check the stack trace for debugging details</li>
            <li>Copy the error for reporting or searching</li>
          </ul>
        </div>
      </div>
    </ArtifactCard>
  );
};

export default ErrorCard;
