import React, { useState } from 'react';
import { CodingAgentCard } from './CodingAgentCard';
import { FileDiff, FileTreeItem, ApprovalState } from './index';

/**
 * Demo page for the Coding Agents prototype
 * Showcases: DiffViewer, FileTreeMarkers, ApprovalPanel, CodingAgentCard
 *
 * Run with: npm run dev (port 5302)
 */

const sampleDiffs: FileDiff[] = [
  {
    filename: 'src/components/Chat.tsx',
    language: 'tsx',
    added: 12,
    removed: 3,
    blocks: [
      {
        lineNum: 1,
        type: 'context',
        content: 'import React, { useState } from "react";',
      },
      {
        lineNum: 2,
        type: 'context',
        content: 'import { Button } from "./Button";',
      },
      {
        lineNum: 3,
        type: 'add',
        content: 'import { useMessages } from "../hooks/useMessages";',
      },
      {
        lineNum: 4,
        type: 'add',
        content: 'import { Spinner } from "./Spinner";',
      },
      {
        lineNum: 5,
        type: 'context',
        content: '',
      },
      {
        lineNum: 6,
        type: 'context',
        content: 'export const ChatComponent = () => {',
      },
      {
        lineNum: 7,
        type: 'remove',
        content: '  const messages = useState([]);',
      },
      {
        lineNum: 8,
        type: 'remove',
        content: '  const loading = useState(false);',
      },
      {
        lineNum: 9,
        type: 'add',
        content: '  const { messages, loading, error } = useMessages();',
      },
      {
        lineNum: 10,
        type: 'context',
        content: '',
      },
      {
        lineNum: 11,
        type: 'context',
        content: '  return (',
      },
      {
        lineNum: 12,
        type: 'context',
        content: '    <div className="chat-container">',
      },
      {
        lineNum: 13,
        type: 'context',
        content: '      {messages.map(m => <Message key={m.id} {...m} />)}',
      },
      {
        lineNum: 14,
        type: 'add',
        content: '      {loading && <Spinner />}',
      },
      {
        lineNum: 15,
        type: 'add',
        content: '      {error && <ErrorBoundary error={error} />}',
      },
      {
        lineNum: 16,
        type: 'context',
        content: '    </div>',
      },
      {
        lineNum: 17,
        type: 'context',
        content: '  );',
      },
      {
        lineNum: 18,
        type: 'context',
        content: '};',
      },
    ],
  },
  {
    filename: 'src/hooks/useMessages.ts',
    language: 'ts',
    added: 8,
    removed: 0,
    blocks: [
      {
        lineNum: 1,
        type: 'add',
        content: 'import { useState, useEffect } from "react";',
      },
      {
        lineNum: 2,
        type: 'add',
        content: '',
      },
      {
        lineNum: 3,
        type: 'add',
        content: 'export interface Message {',
      },
      {
        lineNum: 4,
        type: 'add',
        content: '  id: string;',
      },
      {
        lineNum: 5,
        type: 'add',
        content: '  text: string;',
      },
      {
        lineNum: 6,
        type: 'add',
        content: '  timestamp: number;',
      },
      {
        lineNum: 7,
        type: 'add',
        content: '}',
      },
      {
        lineNum: 8,
        type: 'add',
        content: '',
      },
      {
        lineNum: 9,
        type: 'add',
        content: 'export const useMessages = () => {',
      },
      {
        lineNum: 10,
        type: 'add',
        content: '  const [messages, setMessages] = useState<Message[]>([]);',
      },
      {
        lineNum: 11,
        type: 'add',
        content: '  const [loading, setLoading] = useState(false);',
      },
      {
        lineNum: 12,
        type: 'add',
        content: '  const [error, setError] = useState<string | null>(null);',
      },
      {
        lineNum: 13,
        type: 'add',
        content: '',
      },
      {
        lineNum: 14,
        type: 'add',
        content: '  useEffect(() => {',
      },
      {
        lineNum: 15,
        type: 'add',
        content: '    // Fetch messages from API',
      },
      {
        lineNum: 16,
        type: 'add',
        content: '  }, []);',
      },
      {
        lineNum: 17,
        type: 'add',
        content: '',
      },
      {
        lineNum: 18,
        type: 'add',
        content: '  return { messages, loading, error };',
      },
      {
        lineNum: 19,
        type: 'add',
        content: '};',
      },
    ],
  },
];

const sampleFileTree: FileTreeItem[] = [
  {
    id: 'src',
    path: 'src/',
    name: 'src',
    type: 'folder',
    children: [
      {
        id: 'src-components',
        path: 'src/components/',
        name: 'components',
        type: 'folder',
        isModified: true,
        children: [
          {
            id: 'src-components-Chat',
            path: 'src/components/Chat.tsx',
            name: 'Chat.tsx',
            type: 'file',
            isModified: true,
          },
          {
            id: 'src-components-Message',
            path: 'src/components/Message.tsx',
            name: 'Message.tsx',
            type: 'file',
          },
          {
            id: 'src-components-Spinner',
            path: 'src/components/Spinner.tsx',
            name: 'Spinner.tsx',
            type: 'file',
          },
        ],
      },
      {
        id: 'src-hooks',
        path: 'src/hooks/',
        name: 'hooks',
        type: 'folder',
        isModified: true,
        children: [
          {
            id: 'src-hooks-useMessages',
            path: 'src/hooks/useMessages.ts',
            name: 'useMessages.ts',
            type: 'file',
            isNew: true,
          },
          {
            id: 'src-hooks-useAuth',
            path: 'src/hooks/useAuth.ts',
            name: 'useAuth.ts',
            type: 'file',
          },
        ],
      },
    ],
  },
];

const sampleApprovalState: ApprovalState = {
  status: 'pending',
  turnId: 'turn_01J8X3AB4N',
  turnTitle: 'Refactor Chat component with loading state',
  fileCount: 2,
  timestamp: Date.now(),
};

export const CodingAgentsDemoPage: React.FC = () => {
  const [approval, setApproval] = useState<ApprovalState>(sampleApprovalState);

  const handleApprove = () => {
    setApproval({ ...approval, status: 'approved' });
  };

  const handleReject = () => {
    setApproval({ ...approval, status: 'rejected' });
  };

  const handleReset = () => {
    setApproval({ ...sampleApprovalState });
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 p-8">
      <div className="max-w-4xl mx-auto space-y-8">
        {/* Header */}
        <div className="space-y-2">
          <h1 className="text-4xl font-bold text-gray-900">Coding Agents Prototype</h1>
          <p className="text-lg text-gray-600">
            UI patterns for human-in-the-loop approval of AI-generated code changes
          </p>
        </div>

        {/* Info boxes */}
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h3 className="font-semibold text-gray-900 mb-2">Key Transfers from Cursor/Windsurf</h3>
            <ul className="text-sm text-gray-700 space-y-1">
              <li>✓ Staged edits (don't auto-apply)</li>
              <li>✓ Inline diff viewer with context</li>
              <li>✓ File tree with modification markers</li>
              <li>✓ Accept/Reject workflow</li>
            </ul>
          </div>

          <div className="bg-white p-4 rounded-lg border border-gray-200">
            <h3 className="font-semibold text-gray-900 mb-2">Primnox Gaps Addressed</h3>
            <ul className="text-sm text-gray-700 space-y-1">
              <li>✓ Visual diff in chat context</li>
              <li>✓ Approval gate before application</li>
              <li>✓ File tree integration</li>
              <li>✓ Edit attribution & tracking</li>
            </ul>
          </div>
        </div>

        {/* Live demo section */}
        <div className="space-y-4">
          <h2 className="text-2xl font-bold text-gray-900">Live Demo</h2>

          {/* Control buttons */}
          <div className="flex gap-2">
            <button
              onClick={handleReset}
              className="px-4 py-2 bg-gray-500 text-white rounded-lg hover:bg-gray-600 transition-colors"
            >
              Reset to Pending
            </button>
          </div>

          {/* Chat message with embedded CodingAgentCard */}
          <div className="bg-white rounded-lg border border-gray-200 p-6 shadow-sm">
            <div className="space-y-4">
              {/* Fake chat message */}
              <div className="flex gap-4">
                <div className="w-10 h-10 rounded-full bg-blue-200 flex items-center justify-center text-blue-900 font-semibold text-sm flex-shrink-0">
                  AI
                </div>
                <div className="flex-1 space-y-4">
                  {/* The actual prototype component */}
                  <CodingAgentCard
                    turnId="turn_01J8X3AB4N"
                    turnTitle="Refactor Chat component with loading state"
                    message="I've refactored the Chat component to use a custom hook for message management. This improves code organization and makes it easier to reuse the logic elsewhere. I also added a loading spinner and error boundary for better UX."
                    diffs={sampleDiffs}
                    fileTree={sampleFileTree}
                    approval={approval}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Documentation */}
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
          <h3 className="text-xl font-bold text-gray-900">Component Architecture</h3>

          <div className="space-y-3 text-sm text-gray-700">
            <div>
              <h4 className="font-semibold text-gray-900 mb-1">DiffViewer</h4>
              <p>Renders line-by-line diffs with syntax highlighting. Collapsible per-file.</p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-900 mb-1">FileTreeMarkers</h4>
              <p>
                Hierarchical file tree with visual markers: blue dot for modified files, green plus
                for new files.
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-900 mb-1">ApprovalPanel</h4>
              <p>
                Status-aware panel showing pending/approved/rejected state with action buttons and
                keyboard hints.
              </p>
            </div>

            <div>
              <h4 className="font-semibold text-gray-900 mb-1">CodingAgentCard</h4>
              <p>
                Composite component that combines all three with collapsible sections. Ready to
                embed in chat messages.
              </p>
            </div>
          </div>
        </div>

        {/* Implementation roadmap */}
        <div className="bg-white rounded-lg border border-gray-200 p-6 space-y-4">
          <h3 className="text-xl font-bold text-gray-900">Implementation Roadmap</h3>

          <div className="space-y-2 text-sm">
            <div className="flex gap-2">
              <span className="text-green-600">✓</span>
              <div>
                <p className="font-semibold text-gray-900">Phase 1: Research & Prototype (Done)</p>
                <p className="text-gray-700">
                  Documented patterns from Cursor, Windsurf, Copilot, Replit, Devin
                </p>
              </div>
            </div>

            <div className="flex gap-2">
              <span className="text-yellow-600">→</span>
              <div>
                <p className="font-semibold text-gray-900">Phase 2: Backend Schema</p>
                <p className="text-gray-700">
                  Add WorkspaceVersion.approval_status, workspace.approval_requested event
                </p>
              </div>
            </div>

            <div className="flex gap-2">
              <span className="text-gray-400">→</span>
              <div>
                <p className="font-semibold text-gray-900">Phase 3: Chat Integration</p>
                <p className="text-gray-700">Render CodingAgentCard inline in chat messages</p>
              </div>
            </div>

            <div className="flex gap-2">
              <span className="text-gray-400">→</span>
              <div>
                <p className="font-semibold text-gray-900">Phase 4: File Tree Integration</p>
                <p className="text-gray-700">Add markers to ContextRail/workspace viewer</p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="text-center text-sm text-gray-600">
          <p>Research & prototype created 2026-08-26</p>
          <p>
            See <code className="bg-gray-200 px-2 py-1 rounded">docs/ui-research/02-coding-agents.md</code> for
            full analysis
          </p>
        </div>
      </div>
    </div>
  );
};

export default CodingAgentsDemoPage;
