import React, { useMemo } from 'react';
import { Download, Repeat2, Copy, Eye } from 'lucide-react';
import { ArtifactCard, type CardAction, type CardMetadata } from './ArtifactCard';

/**
 * ExecutionCard
 * Display tool/script execution results with:
 * - Status indicator (success/error/running)
 * - Runtime & performance metadata
 * - File changes summary
 * - Output log (collapsible)
 * - Retry action
 */

export interface ExecutionCardProps {
  id: string;
  title: string;
  status: 'success' | 'error' | 'running' | 'pending';
  runtime?: number;
  outputLog?: string;
  fileChanges?: {
    created: string[];
    modified: string[];
    deleted: string[];
  };
  artifactCount?: number;
  errorMessage?: string;
  onRetry?: () => void | Promise<void>;
  onDownloadLog?: () => void;
  isMobile?: boolean;
}

export const ExecutionCard: React.FC<ExecutionCardProps> = ({
  id,
  title,
  status,
  runtime,
  outputLog,
  fileChanges,
  artifactCount = 0,
  errorMessage,
  onRetry,
  onDownloadLog,
  isMobile = false,
}) => {
  const metadata: CardMetadata = useMemo(
    () => ({
      status,
      runtime,
      itemCount: (fileChanges?.created.length ?? 0) + (fileChanges?.modified.length ?? 0) + (fileChanges?.deleted.length ?? 0),
      errorMessage,
    }),
    [status, runtime, fileChanges, errorMessage]
  );

  const actions: CardAction[] = useMemo(() => {
    const acts: CardAction[] = [];

    if (onDownloadLog) {
      acts.push({
        id: 'download-log',
        label: 'Download Log',
        icon: <Download size={14} />,
        level: 'common',
        onClick: onDownloadLog,
      });
    }

    if (onRetry) {
      acts.push({
        id: 'retry',
        label: 'Retry',
        icon: <Repeat2 size={14} />,
        level: status === 'error' ? 'core' : 'common',
        onClick: onRetry,
      });
    }

    acts.push({
      id: 'view-details',
      label: 'View Details',
      icon: <Eye size={14} />,
      level: 'advanced',
      onClick: () => console.log('View details clicked'),
    });

    return acts;
  }, [onDownloadLog, onRetry, status]);

  const fileChangeList = useMemo(() => {
    if (!fileChanges) return null;
    const { created, modified, deleted } = fileChanges;
    if (created.length === 0 && modified.length === 0 && deleted.length === 0) return null;

    return (
      <div className="space-y-3">
        <div>
          <h4 className="text-xs font-semibold text-on-surface/70 mb-1.5">File Changes</h4>
          <ul className="space-y-0.5 text-xs font-mono text-on-surface/80">
            {created.map((path) => (
              <li key={path}>
                <span className="text-primary">+</span> {path}
              </li>
            ))}
            {modified.map((path) => (
              <li key={path}>
                <span className="text-on-surface/60">~</span> {path}
              </li>
            ))}
            {deleted.map((path) => (
              <li key={path}>
                <span className="text-error">−</span> {path}
              </li>
            ))}
          </ul>
        </div>
      </div>
    );
  }, [fileChanges]);

  const outputSection = useMemo(() => {
    if (!outputLog) return null;
    const lines = outputLog.split('\n');
    const isLong = lines.length > 20;

    return (
      <div>
        <h4 className="text-xs font-semibold text-on-surface/70 mb-1.5">Output</h4>
        <pre className={`text-[10px] font-mono text-on-surface/70 overflow-x-auto ${isLong ? 'max-h-40' : ''} bg-on-surface/[0.02] p-2 rounded border border-on-surface/[0.05]`}>
          {isLong ? lines.slice(-20).join('\n') : outputLog}
          {isLong && <div className="text-on-surface/50 text-center mt-2">... {lines.length - 20} more lines ...</div>}
        </pre>
      </div>
    );
  }, [outputLog]);

  const artifactSection = useMemo(() => {
    if (artifactCount === 0) return null;
    return (
      <div className="inline-block px-2 py-1 bg-primary/10 rounded text-xs text-primary font-medium">
        {artifactCount} artifact{artifactCount !== 1 ? 's' : ''}
      </div>
    );
  }, [artifactCount]);

  return (
    <ArtifactCard
      id={id}
      type="execution"
      title={title}
      metadata={metadata}
      actions={actions}
      coreAction={onRetry && status === 'error' ? { label: 'Retry', icon: <Repeat2 size={16} />, onClick: onRetry } : undefined}
      isMobile={isMobile}
    >
      <div className="space-y-4">
        {artifactSection && (
          <div>{artifactSection}</div>
        )}

        {outputSection}

        {fileChangeList}

        {status === 'running' && (
          <div className="px-3 py-2 bg-warn/10 rounded border border-warn/20 text-xs text-warn">
            Execution in progress...
          </div>
        )}
      </div>
    </ArtifactCard>
  );
};

export default ExecutionCard;
