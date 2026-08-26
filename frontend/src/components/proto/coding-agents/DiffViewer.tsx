import React, { useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

export interface DiffBlock {
  lineNum: number;
  type: 'add' | 'remove' | 'context';
  content: string;
}

export interface FileDiff {
  filename: string;
  language?: string;
  added: number;
  removed: number;
  blocks: DiffBlock[];
}

interface DiffViewerProps {
  diff: FileDiff;
  isExpanded?: boolean;
  onToggleExpand?: (expanded: boolean) => void;
}

export const DiffViewer: React.FC<DiffViewerProps> = ({
  diff,
  isExpanded = true,
  onToggleExpand,
}) => {
  const [expanded, setExpanded] = useState(isExpanded);

  const handleToggle = () => {
    const newExpanded = !expanded;
    setExpanded(newExpanded);
    onToggleExpand?.(newExpanded);
  };

  const stats = `+${diff.added} -${diff.removed}`;

  return (
    <div className="border border-gray-200 rounded-lg bg-gray-50 overflow-hidden">
      {/* Header */}
      <div
        onClick={handleToggle}
        className="px-4 py-3 bg-gray-100 hover:bg-gray-150 cursor-pointer flex items-center justify-between border-b border-gray-200"
      >
        <div className="flex items-center gap-3 flex-1">
          <div className="text-sm font-mono text-gray-700">{diff.filename}</div>
          <div className="text-xs text-gray-500">
            <span className="text-green-600 font-mono">{stats.split(' ')[0]}</span>
            <span className="text-gray-400 mx-1">·</span>
            <span className="text-red-600 font-mono">{stats.split(' ')[1]}</span>
          </div>
        </div>
        <div className="text-gray-600">
          {expanded ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
        </div>
      </div>

      {/* Content */}
      {expanded && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs font-mono">
            <tbody>
              {diff.blocks.map((block, idx) => (
                <tr
                  key={idx}
                  className={`
                    ${
                      block.type === 'add'
                        ? 'bg-green-50 hover:bg-green-100'
                        : block.type === 'remove'
                          ? 'bg-red-50 hover:bg-red-100'
                          : 'bg-white hover:bg-gray-50'
                    }
                    border-b border-gray-100
                  `}
                >
                  {/* Line number indicator */}
                  <td className="w-8 px-2 py-1 text-gray-400 bg-gray-50 select-none border-r border-gray-200">
                    {block.type === 'context' && <span>{block.lineNum}</span>}
                  </td>

                  {/* Diff marker */}
                  <td className="w-6 px-1 py-1 text-center select-none bg-opacity-20">
                    <span
                      className={`
                        ${
                          block.type === 'add'
                            ? 'text-green-700 font-bold'
                            : block.type === 'remove'
                              ? 'text-red-700 font-bold'
                              : 'text-gray-400'
                        }
                      `}
                    >
                      {block.type === 'add' ? '+' : block.type === 'remove' ? '−' : ''}
                    </span>
                  </td>

                  {/* Code content */}
                  <td className="flex-1 px-3 py-1 text-gray-800 whitespace-pre-wrap break-words">
                    <code>{block.content}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default DiffViewer;
