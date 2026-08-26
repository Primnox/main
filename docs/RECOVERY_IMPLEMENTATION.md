# RecoveryBlock Implementation Guide

## Overview

`RecoveryBlock` is Primnox's unified failure and recovery UI component. It handles error classification, retry logic visualization, and actionable recovery paths. Failures are categorized by type (auth, rate limit, timeout, etc.), and the UI adapts to show appropriate recovery options.

**Files:**
- `/frontend/src/components/RecoveryBlock.tsx` — Main component
- `/frontend/src/lib/error_classifier.ts` — Error categorization logic
- `/frontend/src/components/RecoveryBlock.stories.tsx` — Usage examples
- `/docs/failure-recovery-ux.md` — UX principles and taxonomy

## Components

### RecoveryBlock

The primary component for displaying recoverable errors.

#### Props

```typescript
interface RecoveryBlockProps {
  error: TurnError;                    // The error to display
  onRetry?: () => void;                // Called when user clicks Retry
  onAction?: (actionType: string) => void;  // Called for action buttons
  onDismiss?: () => void;              // Called when dismissed
  context?: {
    provider?: string;                 // Which provider failed (e.g., "Groq")
    tool?: string;                     // Which tool failed (e.g., "Python Sandbox")
    attempt?: number;                  // Current retry attempt
    maxAttempts?: number;              // Max retries allowed (default 3)
  };
  autoDismissMs?: number;              // Auto-dismiss after N ms (0 = no auto-dismiss)
  compact?: boolean;                   // Compact single-line mode
}
```

#### Usage

**In TurnBlock (for turn-level failures):**

```typescript
import { RecoveryBlock } from './RecoveryBlock';

export function TurnBlock({ turn }: { turn: Turn }) {
  const [recoveryDismissed, setRecoveryDismissed] = useState(false);

  return (
    <>
      {turn.error && !recoveryDismissed && (
        <div className="mt-2">
          <RecoveryBlock
            error={turn.error}
            onRetry={() => api.retry(turn.id)}
            onDismiss={() => setRecoveryDismissed(true)}
            context={{
              attempt: turn.attempt ?? 1,
              maxAttempts: 3,
            }}
          />
        </div>
      )}
    </>
  );
}
```

**In ExecutionBlock (for tool execution failures):**

```typescript
import { RecoveryBlock } from './RecoveryBlock';

export function ExecutionBlock({ execution }: { execution: Execution }) {
  const executionError: TurnError | null = execution.status === 'failed'
    ? {
      code: 'tool_execution_failed',
      message: execution.summary || 'Tool execution failed',
      retryable: true,
    }
    : null;

  return (
    <>
      {executionError && (
        <RecoveryBlock
          error={executionError}
          compact={false}
          context={{ tool: execution.runtime }}
        />
      )}
    </>
  );
}
```

**Compact mode (inline with streaming status):**

```typescript
<RecoveryBlock
  error={error}
  compact={true}
  context={{ provider: 'Groq' }}
/>
```

### RecoveryStatusLine

A minimal status-only version for informational errors (no interactive recovery).

```typescript
export function RecoveryStatusLine({
  error,
  context
}: {
  error: TurnError;
  context?: RecoveryBlockProps['context'];
}) { /* ... */ }
```

Only renders for `severity: 'info'` errors (transient, rate limit, timeout, cancelled).

## Error Classifier

The `error_classifier.ts` module converts backend errors into actionable categories.

### classifyError()

```typescript
import { classifyError, type ClassifiedError } from '../lib/error_classifier';

const classified = classifyError({
  code: '401_unauthorized',
  message: 'Groq API key invalid (expired)',
  retryable: false,
});

console.log(classified);
// {
//   category: 'auth_failed',
//   severity: 'critical',
//   message: 'Groq API key invalid (expired)',
//   retryable: false,
//   fallbackable: true,
//   actionable: true,
//   actionLabel: 'Update API Key',
//   ...
// }
```

### Error Categories

| Category | Trigger | Retry | Action | Severity |
|----------|---------|-------|--------|----------|
| `transient` | Network hiccup, connection reset | ✓ Auto | — | info |
| `rate_limited` | 429, backoff needed | ✓ Auto | — | info |
| `auth_failed` | 401, invalid key | ✗ No | Update Key | critical |
| `capability_missing` | Model unavailable | ✗ No | — | warn |
| `permission_denied` | Sandbox/file permission | ✓ Manual | Grant | warn |
| `quota_exceeded` | Budget exhausted | ✗ No | Add Credits | critical |
| `timeout` | 504, slow provider | ✓ Auto | — | warn |
| `tool_failed` | Execution error | ✓ Manual | Debug | error |
| `unsupported` | Feature not available | ✗ No | — | warn |
| `cancelled` | User stopped turn | ✗ No | — | info |
| `unknown` | Unclassified error | ✓ Depends | — | error |

### recoveryMessage()

Formats a recovery message based on classification:

```typescript
import { recoveryMessage } from '../lib/error_classifier';

const msg = recoveryMessage(classified, {
  provider: 'Groq',
  retry: 2,
});

console.log(msg);
// "Groq is rate-limited. Retrying on next provider..."
```

## State Machine

RecoveryBlock manages retry state internally via `CountdownTimer`:

```
[Initial]
    ↓
[Retrying] ← user clicks Retry or error.retryable && auto-retry
    ↓ (suggestedWait elapses)
    → onRetry() called
    → External code (turn_manager, etc.) attempts recovery
    ↓
[Result] (handled by caller)
    → Turn succeeds → RecoveryBlock removed
    → Turn fails again → New error shown
```

The component does **not** perform retries itself. It:
1. Detects retry conditions
2. Shows countdown
3. Calls `onRetry()` callback
4. Caller decides what to retry (turn, execution, provider fallback, etc.)

## Styling & Theming

RecoveryBlock uses Primnox's design system colors:

- **Info-level errors:** `bg-on-surface/[0.03] border-on-surface/15` (subtle, non-intrusive)
- **Error-level:** `bg-error/[0.06] border-error/25` (prominent, actionable)

These map to light/dark theme automatically via CSS variables.

### Icons

Each error category has a semantic icon:
- `Zap` (transient)
- `Clock` (rate limit, timeout)
- `Key` (auth)
- `AlertTriangle` (other errors)
- `X` (cancelled)

## Integration Checklist

- [x] RecoveryBlock component created
- [x] error_classifier module created
- [x] Integrated into TurnBlock
- [x] Integrated into ExecutionBlock
- [x] Stories/examples created
- [ ] Add `attempt` field to `Turn` type (backend needs to track retry count)
- [ ] Add `attempt` field to `Execution` type (if tool-level retries tracked)
- [ ] Wire up `onAction()` handlers in TurnBlock/ExecutionBlock
  - `auth_failed` → Modal to update API key
  - `quota_exceeded` → Link to provider billing
  - `permission_denied` → Permission grant UI
  - `tool_failed` → Debug/details modal
- [ ] Test with synthetic failures (mock provider errors)
- [ ] Add retry endpoint to backend API (if not already present)
  - `POST /api/retry/{turn_id}`
  - `POST /api/retry/execution/{execution_id}`

## Testing

### Manual Testing

1. Use stories in `RecoveryBlock.stories.tsx`:
   ```bash
   # In a dev server or Storybook
   import { StoryTransientError, StoryAuthFailed, etc. } from './RecoveryBlock.stories';
   ```

2. Test in the UI by triggering synthetic errors:
   - Mock provider to return 429
   - Mock provider to return 401
   - Mock sandbox to deny permission
   - Mock tool to timeout

### Example Test Cases

```typescript
// Test: Transient error shows countdown
test('transient error shows retry countdown', () => {
  const { getByText } = render(
    <RecoveryBlock
      error={{ code: 'ECONNRESET', message: 'Connection reset', retryable: true }}
      onRetry={mockRetry}
    />
  );
  expect(getByText(/retrying in/i)).toBeInTheDocument();
  // Wait for countdown to elapse
  waitFor(() => expect(mockRetry).toHaveBeenCalled());
});

// Test: Auth error shows action button
test('auth error shows update key button', () => {
  const { getByText } = render(
    <RecoveryBlock
      error={{ code: '401', message: 'Invalid key', retryable: false }}
      onAction={mockAction}
    />
  );
  expect(getByText(/update.*key/i)).toBeInTheDocument();
  fireEvent.click(getByText(/update.*key/i));
  expect(mockAction).toHaveBeenCalledWith('auth_failed');
});
```

## Design Notes

### Why No Auto-Modal?

RecoveryBlock does not open modals or sidebars itself. The caller owns the recovery UX:
- TurnBlock might show an in-place key-input form
- Or link to Settings
- Or trigger a modal handler
- Or do nothing (silent retry)

This keeps concerns separated and lets the caller choose the best UX for context.

### Why Severity Instead of Color?

`severity` (info, warn, error, critical) maps to visual weight, not just color. Info errors stay subtle; critical errors are prominent. This prevents alarm fatigue when most failures are transient.

### Why Countdown?

A countdown is visible proof that retry is happening. A spinner alone cannot distinguish "working" from "hung". The countdown shows: "yes, the turn is still open, and yes, I'm waiting intentionally."

---

## Troubleshooting

### Error shows but no retry happens
- Check `error.retryable` is set to `true`
- Check `onRetry` callback is wired
- Check `suggestedWait` is reasonable (not 0 or negative)

### RecoveryBlock appears for both turn AND execution
- This is correct. If a turn fails due to tool execution, both blocks might show.
- Use `compact={true}` in execution block to avoid redundancy.

### Error classification is wrong
- Add a new pattern to `error_classifier.ts`
- Check the `message` and `code` fields
- Test with the pattern in `classifyError()` test suite

### Auto-dismiss not working
- Pass `autoDismissMs` in props
- Check that `onDismiss` callback is implemented
- Verify timeout is not interfering

---

## Next Steps

1. **Backend integration:**
   - Ensure all errors include `code` and `message`
   - Add `attempt` tracking to turn manager
   - Implement retry endpoints

2. **Action handlers:**
   - Wire auth action → key update modal
   - Wire quota action → billing link
   - Wire permission action → grant UI

3. **Telemetry:**
   - Track error categories
   - Track which recovery paths users choose
   - Measure retry success rates

4. **Enhancements:**
   - Multi-language support (translate error messages)
   - Dark mode refinement
   - Animation polish (retry shimmer, action hover states)
   - Accessibility audit (screen reader testing)
