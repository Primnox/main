import React, { useState, useCallback } from 'react';
import {
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  AlertCircle,
  CheckCircle,
  Clock,
  AlertTriangle,
} from 'lucide-react';

/**
 * Artifact Card System - Base Component
 *
 * Unified card interface for displaying artifacts:
 * - Execution results (tool outputs)
 * - Files/attachments
 * - Code snippets
 * - Errors with recovery
 *
 * Features:
 * - Progressive disclosure (metadata → details)
 * - Smart action menus (core → common → advanced)
 * - Mobile-first responsive design
 * - Error-driven auto-expand
 */

export type ArtifactCardType = 'execution' | 'attachment' | 'code' | 'error' | 'table';
export type CardStatus = 'success' | 'error' | 'warning' | 'running' | 'pending';
export type ActionLevel = 'core' | 'common' | 'advanced' | 'expert';

export interface CardAction {
  id: string;
  label: string;
  icon?: React.ReactNode;
  level: ActionLevel;
  destructive?: boolean;
  onClick: () => void | Promise<void>;
  confirmText?: string;
  disabled?: boolean;
}

export interface CardMetadata {
  status?: CardStatus;
  runtime?: number; // milliseconds
  itemCount?: number; // files, rows, etc.
  size?: number; // bytes
  type?: string; // 'pdf', 'json', etc.
  timestamp?: number; // unix epoch
  errorMessage?: string;
}

export interface ArtifactCardProps {
  // Core
  id: string;
  type: ArtifactCardType;
  title: string;

  // Metadata & content
  metadata?: CardMetadata;
  children?: React.ReactNode;
  preview?: React.ReactNode;
  previewLoading?: boolean;

  // Actions
  actions?: CardAction[];
  coreAction?: {
    label: string;
    icon?: React.ReactNode;
    onClick: () => void | Promise<void>;
  };

  // State
  expanded?: boolean;
  onExpandChange?: (expanded: boolean) => void;

  // Responsive
  isMobile?: boolean;

  // Styling
  variant?: 'card' | 'plate';
  className?: string;
}

const getStatusIcon = (status?: CardStatus) => {
  switch (status) {
    case 'success':
      return <CheckCircle size={14} className="text-primary" />;
    case 'error':
      return <AlertTriangle size={14} className="text-error" />;
    case 'running':
      return <Clock size={14} className="text-on-surface/50 animate-spin" />;
    case 'warning':
      return <AlertCircle size={14} className="text-warn" />;
    default:
      return null;
  }
};

const formatBytes = (bytes?: number) => {
  if (!bytes) return null;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

const formatDuration = (ms?: number) => {
  if (!ms) return null;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

/**
 * Main ArtifactCard Component
 */
export const ArtifactCard: React.FC<ArtifactCardProps> = ({
  id,
  type,
  title,
  metadata,
  children,
  preview,
  previewLoading = false,
  actions = [],
  coreAction,
  expanded: controlledExpanded,
  onExpandChange,
  isMobile = false,
  variant = 'card',
  className = '',
}) => {
  const [internalExpanded, setInternalExpanded] = useState(controlledExpanded ?? false);
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [loading, setLoading] = useState(false);

  const isExpanded = controlledExpanded !== undefined ? controlledExpanded : internalExpanded;

  const handleToggleExpand = useCallback(() => {
    const newState = !isExpanded;
    setInternalExpanded(newState);
    onExpandChange?.(newState);
  }, [isExpanded, onExpandChange]);

  const handleAction = useCallback(
    async (action: CardAction) => {
      setLoading(true);
      try {
        await action.onClick();
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const coreActions = actions.filter((a) => a.level === 'core');
  const commonActions = actions.filter((a) => a.level === 'common');
  const advancedActions = actions.filter((a) => a.level === 'advanced' || a.level === 'expert');

  const showMoreMenu = commonActions.length > 0 || advancedActions.length > 0;

  return (
    <div
      className={`mb-3 overflow-hidden ${
        variant === 'card'
          ? 'rounded-xl border border-on-surface/[0.09]'
          : 'rounded-lg border border-dr-rule'
      } bg-surface-container-lowest ${className}`}
      data-card-type={type}
      data-card-id={id}
    >
      {/* Header: Title, Metadata, Status */}
      <header className="flex items-center justify-between gap-2.5 px-4 py-2.5">
        {/* Left: Title + Metadata */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {metadata?.status && getStatusIcon(metadata.status)}
            <span className="font-medium text-sm truncate text-on-surface">{title}</span>
          </div>

          {/* Metadata line (only when closed or on desktop) */}
          {metadata && (
            <div className="flex items-center gap-3 mt-1 text-[11px] text-on-surface/60">
              {metadata.runtime && <span>⏱ {formatDuration(metadata.runtime)}</span>}
              {metadata.itemCount !== undefined && (
                <span>{metadata.itemCount} item{metadata.itemCount !== 1 ? 's' : ''}</span>
              )}
              {metadata.size && <span>{formatBytes(metadata.size)}</span>}
              {metadata.type && <span className="px-1.5 py-0.5 bg-on-surface/10 rounded">{metadata.type}</span>}
            </div>
          )}
        </div>

        {/* Right: Actions + Toggle */}
        <div className="flex items-center gap-1">
          {/* Core actions (always visible) */}
          {!isMobile &&
            coreActions.map((action) => (
              <button
                key={action.id}
                onClick={() => handleAction(action)}
                disabled={action.disabled || loading}
                title={action.label}
                className={`p-2 rounded text-on-surface/70 hover:bg-on-surface/[0.06] transition-colors ${
                  action.disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'
                }`}
              >
                {action.icon}
              </button>
            ))}

          {/* More menu button */}
          {showMoreMenu && (
            <div className="relative">
              <button
                onClick={() => setShowActionMenu(!showActionMenu)}
                className="p-2 rounded text-on-surface/70 hover:bg-on-surface/[0.06] transition-colors"
                title="More actions"
              >
                <MoreHorizontal size={16} />
              </button>

              {showActionMenu && (
                <div className="absolute right-0 mt-1 bg-surface-container rounded-lg shadow-lg border border-on-surface/[0.09] min-w-[200px] z-10">
                  {commonActions.map((action) => (
                    <button
                      key={action.id}
                      onClick={() => {
                        handleAction(action);
                        setShowActionMenu(false);
                      }}
                      className={`block w-full text-left px-4 py-2 text-sm hover:bg-on-surface/[0.06] first:rounded-t-lg last:rounded-b-lg transition-colors ${
                        action.destructive ? 'text-error' : 'text-on-surface'
                      }`}
                    >
                      {action.label}
                    </button>
                  ))}
                  {advancedActions.length > 0 && commonActions.length > 0 && (
                    <div className="border-t border-on-surface/[0.09]" />
                  )}
                  {advancedActions.map((action) => (
                    <button
                      key={action.id}
                      onClick={() => {
                        handleAction(action);
                        setShowActionMenu(false);
                      }}
                      className="block w-full text-left px-4 py-2 text-sm text-on-surface/70 hover:bg-on-surface/[0.06] last:rounded-b-lg transition-colors"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Expand toggle */}
          <button
            onClick={handleToggleExpand}
            className="p-2 rounded text-on-surface/70 hover:bg-on-surface/[0.06] transition-colors"
            aria-expanded={isExpanded}
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
      </header>

      {/* Error Message (if present) */}
      {metadata?.errorMessage && isExpanded && (
        <div className="px-4 py-3 border-t border-on-surface/[0.07] bg-error-container/10">
          <div className="flex gap-2 items-start">
            <AlertTriangle size={14} className="text-error mt-0.5 flex-shrink-0" />
            <p className="text-sm text-error">{metadata.errorMessage}</p>
          </div>
        </div>
      )}

      {/* Expanded Content */}
      {isExpanded && (
        <div className="border-t border-on-surface/[0.07]">
          {previewLoading ? (
            <div className="px-4 py-8 flex items-center justify-center text-on-surface/50">
              <Clock size={16} className="animate-spin mr-2" />
              Loading preview...
            </div>
          ) : (
            <>
              {preview && <div className="px-4 py-4 max-h-96 overflow-auto">{preview}</div>}
              {children && <div className="px-4 py-4 max-h-96 overflow-auto">{children}</div>}
            </>
          )}

          {/* Mobile action buttons (shown when expanded) */}
          {isMobile && (
            <div className="px-4 py-3 border-t border-on-surface/[0.07] flex gap-2">
              {coreAction && (
                <button
                  onClick={coreAction.onClick}
                  className="flex-1 py-2 px-3 bg-primary text-on-primary rounded text-sm font-medium hover:bg-primary/90 transition-colors"
                >
                  {coreAction.label}
                </button>
              )}
              {coreActions.length > 0 && (
                <div className="flex-1 flex gap-1">
                  {coreActions.map((action) => (
                    <button
                      key={action.id}
                      onClick={() => handleAction(action)}
                      className="flex-1 py-2 px-3 border border-on-surface/10 text-on-surface rounded text-sm font-medium hover:bg-on-surface/[0.05] transition-colors"
                    >
                      {action.icon}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default ArtifactCard;
