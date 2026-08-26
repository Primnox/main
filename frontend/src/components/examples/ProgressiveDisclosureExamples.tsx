/**
 * Progressive Disclosure Examples
 *
 * Real-world usage patterns across Primnox features.
 * Copy-paste these patterns when implementing disclosure in your component.
 */

import React, { useState } from 'react';
import {
  ProgressiveDisclosure,
  ProgressiveDisclosureGroup,
  useUserExpertise,
  useErrorContext,
  DisclosureLevelBadge,
} from '../ProgressiveDisclosure';
import { Copy, Trash2, Edit3, BookmarkPlus } from 'lucide-react';

/* ============================================================================
   Example 1: Chat Message Actions (Level 2 → Level 3)
   ============================================================================
   Shows: Common actions inline, advanced actions in disclosure
*/

export const ChatMessageExample: React.FC = () => {
  const [messageText] = useState(
    'Here is a summary of the key points from your document.'
  );

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-600">Chat Message with Disclosure</h3>

      <div className="border border-gray-200 rounded-lg p-4 bg-white">
        <p className="text-gray-900 mb-4">{messageText}</p>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Level 1: Always shown */}
          <button className="inline-flex items-center gap-1 px-2 py-1 text-sm text-gray-600 hover:bg-gray-100 rounded">
            <Copy size={14} /> Copy
          </button>

          {/* Level 2: Common, shown by default */}
          <ProgressiveDisclosure
            level="2-common"
            title="More"
            cardStyle={false}
          >
            <div className="flex flex-col gap-2 text-sm">
              <button className="text-left px-2 py-1 hover:bg-gray-100 rounded flex items-center gap-2">
                <Edit3 size={14} /> Edit
              </button>
              <button className="text-left px-2 py-1 hover:bg-gray-100 rounded flex items-center gap-2">
                <BookmarkPlus size={14} /> Bookmark
              </button>
              <button className="text-left px-2 py-1 hover:bg-red-50 rounded flex items-center gap-2 text-red-600">
                <Trash2 size={14} /> Delete
              </button>
            </div>
          </ProgressiveDisclosure>
        </div>
      </div>

      <p className="text-xs text-gray-500">
        Common: [Copy] [More ▼]  |  Advanced expands: Edit, Bookmark, Delete
      </p>
    </div>
  );
};

/* ============================================================================
   Example 2: Settings Panel with Tiers (All Levels)
   ============================================================================
   Shows: Progressive revelation of settings based on expertise
*/

export const SettingsPanelExample: React.FC = () => {
  const { expertise } = useUserExpertise();

  return (
    <div className="space-y-6">
      <h3 className="text-sm font-semibold text-gray-600">
        Settings Panel (Expertise: {expertise})
      </h3>

      <div className="border border-gray-200 rounded-lg p-6 bg-white max-w-md">
        {/* Level 1: Core settings */}
        <ProgressiveDisclosureGroup level="1-core" title="Core">
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-900">
                Theme
              </label>
              <select className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                <option>Light</option>
                <option>Dark</option>
                <option>Auto</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-900">
                Notification
              </label>
              <input type="checkbox" defaultChecked />
            </div>
          </div>
        </ProgressiveDisclosureGroup>

        {/* Level 2: Common settings */}
        <ProgressiveDisclosureGroup level="2-common" title="Appearance">
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-gray-900">
                Density
              </label>
              <select className="mt-1 block w-full px-3 py-2 border border-gray-300 rounded-md text-sm">
                <option>Compact</option>
                <option>Normal</option>
                <option>Spacious</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-900">
                Font Size
              </label>
              <input
                type="range"
                min="12"
                max="18"
                defaultValue="14"
                className="w-full"
              />
            </div>
          </div>
        </ProgressiveDisclosureGroup>

        {/* Level 3: Advanced options */}
        <ProgressiveDisclosure
          level="3-advanced"
          title="Advanced Options"
          cardStyle={true}
        >
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <input type="checkbox" id="tool-caching" />
              <label htmlFor="tool-caching" className="text-sm">
                Enable tool result caching
              </label>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="streaming" />
              <label htmlFor="streaming" className="text-sm">
                Stream responses (slower models only)
              </label>
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="memory" />
              <label htmlFor="memory" className="text-sm">
                Use memory across conversations
              </label>
            </div>
          </div>
        </ProgressiveDisclosure>

        {/* Level 4: Expert tools */}
        <ProgressiveDisclosure
          level="4-expert"
          title="Expert Debugging"
          cardStyle={true}
          collapsedDescription="Token accounting, event logs, traces"
        >
          <div className="space-y-2 text-sm">
            <div className="bg-gray-50 p-2 rounded font-mono text-xs">
              Token Usage: 1,450 input | 280 output
            </div>
            <button className="text-blue-600 hover:underline text-xs">
              View event log
            </button>
            <button className="text-blue-600 hover:underline text-xs block">
              Export trace
            </button>
          </div>
        </ProgressiveDisclosure>
      </div>
    </div>
  );
};

/* ============================================================================
   Example 3: Permission Approval (Context-aware disclosure)
   ============================================================================
   Shows: Auto-expanding details on approval request
*/

export const PermissionApprovalExample: React.FC = () => {
  const [approved, setApproved] = useState(false);
  const { errorContext, triggerExpand } = useErrorContext();

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-600">
        Permission Approval (Context-aware)
      </h3>

      <div className="border border-gray-200 rounded-lg p-4 bg-white max-w-md">
        {/* Level 1: Basic prompt */}
        <div className="mb-4">
          <h4 className="font-semibold text-gray-900">Run Python Code</h4>
          <p className="text-sm text-gray-600 mt-1">
            Primnox wants to execute code in a sandboxed environment.
          </p>
        </div>

        {/* Level 2: Common approval options */}
        <div className="flex gap-2 mb-4">
          <button
            onClick={() => setApproved(true)}
            className="flex-1 px-3 py-2 bg-blue-600 text-white text-sm font-medium rounded hover:bg-blue-700"
          >
            Allow Once
          </button>
          <button className="flex-1 px-3 py-2 border border-gray-300 text-sm font-medium rounded hover:bg-gray-50">
            For This Turn
          </button>
          <button
            onClick={() => triggerExpand('User denied permission')}
            className="flex-1 px-3 py-2 border border-gray-300 text-sm font-medium rounded hover:bg-gray-50"
          >
            Deny
          </button>
        </div>

        {/* Level 3: Advanced details (expandable) */}
        <ProgressiveDisclosure
          level="3-advanced"
          title="View Details"
          cardStyle={false}
          expandOnError={true}
          errorContext={errorContext}
        >
          <div className="bg-gray-50 p-3 rounded space-y-2 text-xs">
            <div>
              <span className="font-semibold text-gray-700">Tool:</span>
              <span className="ml-2 font-mono">run_python</span>
            </div>
            <div>
              <span className="font-semibold text-gray-700">Timeout:</span>
              <span className="ml-2">30 seconds</span>
            </div>
            <div>
              <span className="font-semibold text-gray-700">Sandbox:</span>
              <span className="ml-2">Isolated, read Documents only</span>
            </div>
            <div>
              <span className="font-semibold text-gray-700">Previous runs:</span>
              <span className="ml-2">5 in this conversation</span>
            </div>
          </div>
        </ProgressiveDisclosure>

        {approved && (
          <div className="mt-4 p-3 bg-green-50 border border-green-200 rounded text-sm text-green-800">
            ✓ Approved. Running code...
          </div>
        )}
      </div>
    </div>
  );
};

/* ============================================================================
   Example 4: Error State with Auto-expansion
   ============================================================================
   Shows: How errors trigger progressive disclosure of debugging info
*/

export const ErrorStateExample: React.FC = () => {
  const { errorContext, triggerExpand, clearError } = useErrorContext();

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-600">
        Error with Progressive Debugging
      </h3>

      <div className="border border-red-200 rounded-lg p-4 bg-red-50 max-w-md">
        {/* Level 1: Error message */}
        <div className="flex items-start gap-3">
          <div className="text-red-600 text-lg">⚠</div>
          <div className="flex-1">
            <h4 className="font-semibold text-red-900">Request Failed</h4>
            <p className="text-sm text-red-700 mt-1">
              The model took too long to respond. Try again?
            </p>
          </div>
        </div>

        <div className="flex gap-2 mt-4">
          <button className="px-3 py-2 bg-red-600 text-white text-sm font-medium rounded hover:bg-red-700">
            Retry
          </button>
          <button
            onClick={() => triggerExpand('Request timeout after 30s')}
            className="px-3 py-2 border border-red-300 text-sm font-medium rounded hover:bg-red-100"
          >
            Troubleshoot
          </button>
        </div>

        {/* Level 3: Auto-expanded when user clicks Troubleshoot */}
        <ProgressiveDisclosure
          level="3-advanced"
          title="Debugging Information"
          expandOnError={true}
          errorContext={errorContext}
          cardStyle={true}
          className="mt-4"
          onOpen={() => {
            // In real code, log that user entered debug mode
            console.log('User opened debug info');
          }}
        >
          <div className="space-y-3">
            <div className="bg-gray-50 p-2 rounded font-mono text-xs space-y-1">
              <div>
                <span className="text-gray-600">Error:</span>{' '}
                <span className="text-red-600">Timeout</span>
              </div>
              <div>
                <span className="text-gray-600">Time elapsed:</span> 30s
              </div>
              <div>
                <span className="text-gray-600">Last response:</span> 1.2MB
                tokens
              </div>
              <div>
                <span className="text-gray-600">Provider:</span> claude-aerolink
              </div>
            </div>

            {/* Level 4: Deeper logs (nested disclosure) */}
            <ProgressiveDisclosure
              level="4-expert"
              title="Raw Logs"
              cardStyle={false}
            >
              <div className="bg-gray-900 text-gray-300 p-2 rounded font-mono text-xs overflow-auto max-h-32">
                <div>[14:32:18] POST /api/messages</div>
                <div>[14:32:19] Stream start</div>
                <div>[14:33:48] Timeout (30000ms)</div>
                <div>[14:33:48] Connection closed</div>
              </div>
            </ProgressiveDisclosure>

            <button
              onClick={clearError}
              className="text-sm text-blue-600 hover:underline"
            >
              Clear & retry
            </button>
          </div>
        </ProgressiveDisclosure>
      </div>
    </div>
  );
};

/* ============================================================================
   Example 5: Disclosure Level Badges (for learning)
   ============================================================================
   Shows: Visual badges showing what level each control is
*/

export const DisclosureLevelBadgesExample: React.FC = () => {
  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-600">
        Disclosure Level Badges
      </h3>

      <div className="grid grid-cols-2 gap-4 max-w-md">
        <div className="border border-gray-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <DisclosureLevelBadge level="1-core" />
            <span className="text-xs font-mono">1-core</span>
          </div>
          <p className="text-xs text-gray-600">Always visible</p>
        </div>

        <div className="border border-gray-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <DisclosureLevelBadge level="2-common" />
            <span className="text-xs font-mono">2-common</span>
          </div>
          <p className="text-xs text-gray-600">Shown by default</p>
        </div>

        <div className="border border-gray-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <DisclosureLevelBadge level="3-advanced" />
            <span className="text-xs font-mono">3-advanced</span>
          </div>
          <p className="text-xs text-gray-600">1 click to expand</p>
        </div>

        <div className="border border-gray-200 rounded-lg p-3 bg-white">
          <div className="flex items-center gap-2 mb-2">
            <DisclosureLevelBadge level="4-expert" />
            <span className="text-xs font-mono">4-expert</span>
          </div>
          <p className="text-xs text-gray-600">Settings panel</p>
        </div>
      </div>
    </div>
  );
};

/* ============================================================================
   Full Page Example
   ============================================================================
*/

export const ProgressiveDisclosureShowcase: React.FC = () => {
  return (
    <div className="space-y-12 max-w-2xl">
      <div>
        <h1 className="text-2xl font-bold mb-6 text-gray-900">
          Progressive Disclosure Examples
        </h1>
        <p className="text-gray-600 mb-8">
          Five-level disclosure patterns implemented across Primnox UI surfaces.
        </p>
      </div>

      <ChatMessageExample />
      <hr className="border-gray-200" />

      <SettingsPanelExample />
      <hr className="border-gray-200" />

      <PermissionApprovalExample />
      <hr className="border-gray-200" />

      <ErrorStateExample />
      <hr className="border-gray-200" />

      <DisclosureLevelBadgesExample />
    </div>
  );
};
