import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { DiffViewer, FileDiff } from './DiffViewer';
import { FileTreeMarkers, FileTreeItem } from './FileTreeMarkers';
import { ApprovalPanel, ApprovalState } from './ApprovalPanel';

interface CodingAgentCardProps {
  turnId: string;
  turnTitle: string;
  message: string;
  diffs: FileDiff[];
  fileTree: FileTreeItem[];
  approval: ApprovalState;
  onApprove?: () => void;
  onReject?: () => void;
  onReview?: () => void;
}

export const CodingAgentCard: React.FC<CodingAgentCardProps> = ({
  turnId: _turnId,
  turnTitle: _turnTitle,
  message,
  diffs,
  fileTree,
  approval,
  onApprove,
  onReject,
  onReview,
}) => {
  const [showDiffs, setShowDiffs] = useState(true);
  const [showFileTree, setShowFileTree] = useState(true);

  const totalAdded = diffs.reduce((sum, d) => sum + d.added, 0);
  const totalRemoved = diffs.reduce((sum, d) => sum + d.removed, 0);

  return (
    <div className="space-y-4">
      {/* Message content */}
      <div className="text-gray-800 whitespace-pre-wrap">{message}</div>

      {/* File tree with markers */}
      {fileTree.length > 0 && (
        <div>
          <button
            onClick={() => setShowFileTree(!showFileTree)}
            className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900 mb-2"
          >
            {showFileTree ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            Files Modified ({fileTree.length})
          </button>

          {showFileTree && <FileTreeMarkers items={fileTree} touchCount={fileTree.length} />}
        </div>
      )}

      {/* Diff viewer section */}
      {diffs.length > 0 && (
        <div>
          <button
            onClick={() => setShowDiffs(!showDiffs)}
            className="flex items-center gap-2 text-sm font-medium text-gray-700 hover:text-gray-900 mb-2"
          >
            {showDiffs ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            Changes ({diffs.length} file{diffs.length !== 1 ? 's' : ''} — +{totalAdded} −
            {totalRemoved})
          </button>

          {showDiffs && (
            <div className="space-y-2">
              {diffs.map((diff, idx) => (
                <DiffViewer key={idx} diff={diff} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Approval panel */}
      <ApprovalPanel
        approval={approval}
        onApprove={onApprove}
        onReject={onReject}
        onReview={onReview}
      />
    </div>
  );
};

export default CodingAgentCard;
