import React from 'react';
import { Check, X, Eye } from 'lucide-react';

export interface ApprovalState {
  status: 'pending' | 'approved' | 'rejected';
  turnId: string;
  turnTitle: string;
  fileCount: number;
  timestamp?: number;
}

interface ApprovalPanelProps {
  approval: ApprovalState;
  onApprove?: () => void;
  onReject?: () => void;
  onReview?: () => void;
  disabled?: boolean;
}

export const ApprovalPanel: React.FC<ApprovalPanelProps> = ({
  approval,
  onApprove,
  onReject,
  onReview,
  disabled = false,
}) => {
  const statusColors = {
    pending: 'yellow',
    approved: 'green',
    rejected: 'red',
  };

  const statusColor = statusColors[approval.status];
  const statusLabels = {
    pending: 'Pending Review',
    approved: 'Approved',
    rejected: 'Rejected',
  };

  return (
    <div
      className={`
        border-2 rounded-lg p-4
        ${
          statusColor === 'yellow'
            ? 'border-yellow-300 bg-yellow-50'
            : statusColor === 'green'
              ? 'border-green-300 bg-green-50'
              : 'border-red-300 bg-red-50'
        }
      `}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-gray-900">{statusLabels[approval.status]}</h3>
          <p className="text-xs text-gray-600 mt-1">
            "{approval.turnTitle}" — {approval.fileCount} file{approval.fileCount !== 1 ? 's' : ''}{' '}
            modified
          </p>
        </div>

        {/* Status badge */}
        <div
          className={`
            px-3 py-1 rounded-full text-xs font-medium
            ${
              statusColor === 'yellow'
                ? 'bg-yellow-200 text-yellow-800'
                : statusColor === 'green'
                  ? 'bg-green-200 text-green-800'
                  : 'bg-red-200 text-red-800'
            }
          `}
        >
          {statusLabels[approval.status]}
        </div>
      </div>

      {/* Action buttons */}
      {approval.status === 'pending' && (
        <div className="flex gap-3 mt-4">
          <button
            onClick={onReview}
            disabled={disabled}
            className="
              flex-1 flex items-center justify-center gap-2
              px-4 py-2 rounded-lg
              border border-blue-400 bg-blue-50
              text-blue-700 font-medium text-sm
              hover:bg-blue-100 active:bg-blue-200
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            <Eye size={16} />
            Review & Approve
          </button>

          <button
            onClick={onApprove}
            disabled={disabled}
            className="
              flex-1 flex items-center justify-center gap-2
              px-4 py-2 rounded-lg
              border border-green-400 bg-green-50
              text-green-700 font-medium text-sm
              hover:bg-green-100 active:bg-green-200
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            <Check size={16} />
            Accept All
          </button>

          <button
            onClick={onReject}
            disabled={disabled}
            className="
              flex-1 flex items-center justify-center gap-2
              px-4 py-2 rounded-lg
              border border-red-400 bg-red-50
              text-red-700 font-medium text-sm
              hover:bg-red-100 active:bg-red-200
              disabled:opacity-50 disabled:cursor-not-allowed
              transition-colors
            "
          >
            <X size={16} />
            Reject
          </button>
        </div>
      )}

      {approval.status === 'approved' && (
        <div className="flex items-center gap-2 mt-4 text-green-700 text-sm">
          <Check size={16} />
          <span>Changes applied successfully</span>
        </div>
      )}

      {approval.status === 'rejected' && (
        <div className="flex items-center gap-2 mt-4 text-red-700 text-sm">
          <X size={16} />
          <span>Changes discarded</span>
        </div>
      )}

      {/* Keyboard shortcut hint */}
      {approval.status === 'pending' && (
        <div className="text-xs text-gray-600 mt-3 italic">
          Keyboard: <kbd className="px-2 py-1 bg-gray-200 rounded">Tab</kbd> to accept,{' '}
          <kbd className="px-2 py-1 bg-gray-200 rounded">Shift+Tab</kbd> to reject
        </div>
      )}
    </div>
  );
};

export default ApprovalPanel;
