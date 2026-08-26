/**
 * RecoveryBlock Stories
 *
 * Storybook-style examples demonstrating RecoveryBlock behavior
 * with different error types and recovery paths.
 *
 * Usage: Uncomment any story below to preview it in development.
 * (Or integrate with Storybook if available.)
 */

import { useState } from 'react';
import { type TurnError } from '../lib/crs';
import { RecoveryBlock, RecoveryStatusLine } from './RecoveryBlock';

// Example errors for each category
const EXAMPLE_ERRORS: Record<string, TurnError> = {
  transient: {
    code: 'ECONNRESET',
    message: 'Connection reset by peer while streaming from Claude (Anthropic).',
    retryable: true,
  },
  rate_limited: {
    code: '429_rate_limit',
    message: 'Groq API: Rate limit exceeded. Queued for retry on next provider.',
    retryable: true,
  },
  auth_failed: {
    code: '401_unauthorized',
    message: 'Groq API key invalid (expired). Last successful call was 3 days ago.',
    retryable: false,
  },
  capability_missing: {
    code: 'model_unavailable',
    message: 'Claude Opus is not available in your region (US West 2).',
    retryable: false,
  },
  permission_denied: {
    code: 'permission_denied',
    message: 'Python sandbox: Cannot write to /home (permission denied).',
    retryable: true,
  },
  quota_exceeded: {
    code: 'quota_exceeded',
    message: 'Groq: Quota exhausted. You have $0.00 remaining. Add credits to continue.',
    retryable: false,
  },
  timeout: {
    code: '504_gateway_timeout',
    message: 'Anthropic (Claude) took longer than 60s. Retrying on fallback provider.',
    retryable: true,
  },
  tool_failed: {
    code: 'tool_execution_failed',
    message: 'Python execution error: ModuleNotFoundError: No module named "pandas"',
    retryable: true,
  },
  unsupported: {
    code: 'unsupported_operation',
    message: 'Tool "screenshot" is not available in this sandboxed environment.',
    retryable: false,
  },
  cancelled: {
    code: 'cancelled',
    message: 'Turn cancelled by user.',
    retryable: false,
  },
};

/**
 * Story 1: Transient Network Error
 * Shows: Retry countdown, auto-recovery messaging
 */
export function StoryTransientError() {
  const [dismissed, setDismissed] = useState(false);

  if (dismissed) return <p className="text-on-surface/50">Dismissed.</p>;

  return (
    <div className="space-y-4">
      <h3 className="font-medium">Network Blip (Retrying)</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.transient}
        onRetry={() => console.log('Retry clicked')}
        onDismiss={() => setDismissed(true)}
        context={{ provider: 'Anthropic', attempt: 1, maxAttempts: 3 }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Blue info-level block, auto-retry countdown, no action needed.
      </p>
    </div>
  );
}

/**
 * Story 2: Rate Limited with Fallback
 * Shows: Informational message, automatic retry handling
 */
export function StoryRateLimited() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Rate Limited (Attempting Fallback)</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.rate_limited}
        onRetry={() => console.log('Retry clicked')}
        context={{ provider: 'Groq', attempt: 2, maxAttempts: 3 }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Info-level, shows it's trying another provider, no user action.
      </p>
    </div>
  );
}

/**
 * Story 3: Authentication Failure
 * Shows: Critical error, actionable recovery (add key)
 */
export function StoryAuthFailed() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">API Key Expired</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.auth_failed}
        onAction={(action) => console.log(`Action: ${action}`)}
        onDismiss={() => console.log('Dismissed')}
        context={{ provider: 'Groq' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Error-level (red), action button "Update API Key", not retryable.
      </p>
    </div>
  );
}

/**
 * Story 4: Model Not Available
 * Shows: Capability mismatch, graceful degradation
 */
export function StoryCapabilityMissing() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Model Unavailable in Region</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.capability_missing}
        onAction={(action) => console.log(`Action: ${action}`)}
        context={{ provider: 'Anthropic' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Informational, suggests fallback (Sonnet), not retryable.
      </p>
    </div>
  );
}

/**
 * Story 5: Sandbox Permission Denied
 * Shows: Tool-level error, permission context
 */
export function StoryPermissionDenied() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Sandbox Permission Error</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.permission_denied}
        onAction={(action) => console.log(`Action: ${action}`)}
        context={{ tool: 'Python Sandbox' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Warn-level, shows resource, action to grant permission.
      </p>
    </div>
  );
}

/**
 * Story 6: Quota Exhausted
 * Shows: Critical error, user action required (add credits)
 */
export function StoryQuotaExceeded() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Out of Credits</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.quota_exceeded}
        onAction={(action) => console.log(`Action: ${action}`)}
        context={{ provider: 'Groq' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Error-level (red), action button "Add Credits" with link.
      </p>
    </div>
  );
}

/**
 * Story 7: Timeout with Fallback
 * Shows: Retry countdown, automatic recovery
 */
export function StoryTimeout() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Request Timeout (Retrying)</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.timeout}
        onRetry={() => console.log('Retry clicked')}
        context={{ provider: 'Anthropic', attempt: 1, maxAttempts: 3 }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Warn-level, retry countdown, automatic progression.
      </p>
    </div>
  );
}

/**
 * Story 8: Tool Execution Error
 * Shows: Detailed error output, retryable
 */
export function StoryToolFailed() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Python Module Not Found</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.tool_failed}
        onRetry={() => console.log('Retry clicked')}
        onAction={(action) => console.log(`Action: ${action}`)}
        context={{ tool: 'Python' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Error-level, expandable details, retry option.
      </p>
    </div>
  );
}

/**
 * Story 9: Unsupported Feature
 * Shows: Informational, not retryable, no action
 */
export function StoryUnsupported() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Feature Not Available</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.unsupported}
        context={{ tool: 'Screenshot' }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Info-level, explains limitation, no recovery option.
      </p>
    </div>
  );
}

/**
 * Story 10: User Cancelled
 * Shows: Neutral outcome, not an error
 */
export function StoryCancelled() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Turn Cancelled</h3>
      <RecoveryBlock
        error={EXAMPLE_ERRORS.cancelled}
        onRetry={() => console.log('Retry clicked')}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Info-level, neutral message, optional retry option.
      </p>
    </div>
  );
}

/**
 * Story 11: Compact Mode
 * Shows: Inline recovery status (for streaming turns)
 */
export function StoryCompactMode() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Compact Status (Inline)</h3>
      <div className="flex items-center gap-3">
        <p className="text-sm">Status:</p>
        <RecoveryBlock
          error={EXAMPLE_ERRORS.rate_limited}
          compact={true}
          context={{ provider: 'Groq', attempt: 1 }}
        />
      </div>
      <p className="text-[12px] text-on-surface/60">
        Expected: Single-line chip, fits inline with other status.
      </p>
    </div>
  );
}

/**
 * Story 12: Status Line (Info-only)
 * Shows: Minimal display for minor issues
 */
export function StoryStatusLine() {
  return (
    <div className="space-y-4">
      <h3 className="font-medium">Recovery Status Line</h3>
      <RecoveryStatusLine
        error={EXAMPLE_ERRORS.transient}
        context={{ provider: 'Anthropic', attempt: 2 }}
      />
      <p className="text-[12px] text-on-surface/60">
        Expected: Minimal line, icon + message, only for info-level errors.
      </p>
    </div>
  );
}

/**
 * Master Story: All Error Types
 * A gallery showing all error categories for comparison
 */
export function StoryGallery() {
  const entries = Object.entries(EXAMPLE_ERRORS).slice(0, 6);

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold">Recovery Block Gallery</h2>
      {entries.map(([category, error]) => (
        <div key={category} className="space-y-2">
          <h3 className="text-sm font-medium capitalize">{category.replace(/_/g, ' ')}</h3>
          <RecoveryBlock
            error={error}
            onRetry={() => console.log(`Retry: ${category}`)}
            onAction={() => console.log(`Action: ${category}`)}
            context={{ provider: 'Example', attempt: 1, maxAttempts: 3 }}
          />
        </div>
      ))}
    </div>
  );
}
