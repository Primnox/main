import { type TurnError } from './crs';

/**
 * Error categories for recovery UI.
 * Each category maps to a different recovery strategy.
 */
export type ErrorCategory =
  | 'transient'        // Retry automatically (network hiccup, rate limit)
  | 'rate_limited'     // Retry with backoff or fallback
  | 'auth_failed'      // Requires user action (new key)
  | 'capability_missing' // Model/feature unavailable
  | 'permission_denied' // Sandbox or system permission issue
  | 'quota_exceeded'    // User needs to add quota/credit
  | 'unsupported'      // Tool/provider incompatible
  | 'timeout'          // Long-running operation exceeded limit
  | 'tool_failed'      // Execution error (code, file I/O, etc.)
  | 'cancelled'        // User cancelled (not an error)
  | 'unknown';         // Could not classify

export type ErrorSeverity = 'info' | 'warn' | 'error' | 'critical';

export interface ClassifiedError {
  category: ErrorCategory;
  severity: ErrorSeverity;
  message: string;
  context?: Record<string, string | number | boolean>;
  retryable: boolean;
  fallbackable: boolean;  // Can use next provider in chain
  actionable: boolean;    // User can take action to fix
  actionLabel?: string;   // e.g., "Add Key", "Grant Permission"
  actionUrl?: string;     // Link to docs or settings
  suggestedWait?: number; // Milliseconds to wait before retry
}

/**
 * Classify an error from the backend to determine recovery strategy.
 */
export function classifyError(error: TurnError | { message: string; code?: string }): ClassifiedError {
  const message = error.message || '';
  const code = ('code' in error) ? (error.code ?? '') : '';
  const retryable = ('retryable' in error) ? error.retryable : false;

  // Rate limit errors (429, 524, etc.)
  if (code && code.match(/^(429|524|rate_limit|quota|backoff)/i)) {
    return {
      category: 'rate_limited',
      severity: 'info',
      message: 'Provider is rate-limited. Will retry on next provider.',
      retryable: true,
      fallbackable: true,
      actionable: false,
      suggestedWait: 5000,
    };
  }

  // Auth failures
  if ((code && code.match(/^(401|403|auth|unauthorized|forbidden|invalid.*key|expired.*token)/i)) ||
      message.match(/api key|unauthorized|forbidden|invalid.*key|expired.*token/i)) {
    const provider = extractProvider(message);
    return {
      category: 'auth_failed',
      severity: 'critical',
      message: extractErrorDetail(message, 'auth'),
      retryable: false,
      fallbackable: true, // Can use another provider if available
      actionable: true,
      actionLabel: 'Update API Key',
      context: {
        failureType: 'authentication',
        ...(provider && { provider }),
      },
    };
  }

  // Capability missing (model not available, feature unsupported)
  if (message.match(/model.*not.*available|unsupported|not.*supported|capability|not found.*model/i)) {
    const alternative = suggestAlternative(message);
    return {
      category: 'capability_missing',
      severity: 'warn',
      message: extractErrorDetail(message, 'capability'),
      retryable: false,
      fallbackable: true,
      actionable: false,
      context: {
        failureType: 'capability',
        ...(alternative && { availableAlternatives: alternative }),
      },
    };
  }

  // Quota exceeded
  if (message.match(/quota|insufficient.*credit|balance|out of.*quota|limit.*reached/i)) {
    return {
      category: 'quota_exceeded',
      severity: 'critical',
      message: extractErrorDetail(message, 'quota'),
      retryable: false,
      fallbackable: true,
      actionable: true,
      actionLabel: 'Add Credits',
      actionUrl: 'https://console.groq.com/billing',
      context: { failureType: 'quota' },
    };
  }

  // Permission/sandbox issues
  if (message.match(/permission.*denied|access.*denied|not allowed|sandbox|restricted/i)) {
    const resource = extractResource(message);
    return {
      category: 'permission_denied',
      severity: 'warn',
      message: extractErrorDetail(message, 'permission'),
      retryable: false,
      fallbackable: false,
      actionable: true,
      actionLabel: 'Grant Permission',
      context: {
        failureType: 'permission',
        ...(resource && { resource }),
      },
    };
  }

  // Timeout
  if ((code && code.match(/^(408|504|timeout)/i)) || message.match(/timeout|timed out|took too long/i)) {
    return {
      category: 'timeout',
      severity: 'warn',
      message: 'Request took too long and was cancelled.',
      retryable: true,
      fallbackable: true,
      actionable: false,
      suggestedWait: 10000,
      context: { failureType: 'timeout' },
    };
  }

  // Tool/execution failures
  if (message.match(/execution|tool.*failed|runtime|traceback|error running/i)) {
    return {
      category: 'tool_failed',
      severity: 'warn',
      message: extractErrorDetail(message, 'tool'),
      retryable: true,
      fallbackable: false,
      actionable: true,
      actionLabel: 'View Details',
      context: { failureType: 'tool_execution' },
    };
  }

  // Transient network errors
  if ((code && code.match(/^(50[0-3]|502|connection|network|econnreset|enotfound)/i)) ||
      message.match(/connection.*refused|network.*unreachable|dns|socket/i)) {
    return {
      category: 'transient',
      severity: 'info',
      message: 'Temporary connection issue. Retrying...',
      retryable: true,
      fallbackable: true,
      actionable: false,
      suggestedWait: 3000,
      context: { failureType: 'network' },
    };
  }

  // Unsupported features/tools
  if (message.match(/not implemented|unsupported operation|not available/i)) {
    return {
      category: 'unsupported',
      severity: 'warn',
      message: extractErrorDetail(message, 'unsupported'),
      retryable: false,
      fallbackable: false,
      actionable: false,
      context: { failureType: 'unsupported' },
    };
  }

  // Cancelled by user (not really an error)
  if (code === 'cancelled' || message.match(/cancelled|user.*stopped|interrupted by user/i)) {
    return {
      category: 'cancelled',
      severity: 'info',
      message: 'Cancelled.',
      retryable: false,
      fallbackable: false,
      actionable: false,
      context: { failureType: 'user_action' },
    };
  }

  // Fallback for unknown errors
  return {
    category: 'unknown',
    severity: 'error',
    message: message || 'An unknown error occurred.',
    retryable: retryable,
    fallbackable: true,
    actionable: false,
    context: { failureType: 'unknown', ...(code && { originalCode: code }) },
  };
}

/**
 * Extract the provider name from an error message.
 * E.g., "Groq API: 401" → "Groq"
 */
function extractProvider(message: string): string | undefined {
  const match = message.match(/(?:Groq|Claude|Anthropic|OpenAI|Gemini|Ollama|LLaMA)/i);
  return match ? match[0] : undefined;
}

/**
 * Extract the resource mentioned in a permission error.
 * E.g., "Cannot read /etc/shadow" → "/etc/shadow"
 */
function extractResource(message: string): string | undefined {
  const match = message.match(/(?:read|write|access|delete)\s+(?:to\s+)?(\S+)/i);
  return match ? match[1] : undefined;
}

/**
 * Get a clean error detail based on category.
 * Removes boilerplate and keeps the actionable part.
 */
function extractErrorDetail(message: string, category: string): string {
  // Remove stack traces and codes
  let cleaned = message
    .split('\n')[0] // First line only
    .replace(/\[?\d{3}\]?/g, '') // Remove status codes
    .replace(/^(Error|Exception):\s*/i, '')
    .trim();

  // Category-specific cleanup
  if (category === 'auth' && cleaned.length > 100) {
    cleaned = 'API key is invalid or expired.';
  }
  if (category === 'permission' && cleaned.length > 100) {
    const resource = extractResource(message);
    cleaned = resource
      ? `Permission denied for ${resource}.`
      : 'Permission denied. Check sandbox settings.';
  }

  return cleaned;
}

/**
 * Suggest an alternative based on what failed.
 * E.g., if Claude Opus unavailable → suggest Sonnet.
 */
function suggestAlternative(message: string): string | undefined {
  if (message.match(/opus/i)) return 'Claude Sonnet';
  if (message.match(/sonnet.*unavailable/i)) return 'Claude Haiku';
  if (message.match(/groq/i)) return 'Use local Ollama';
  return undefined;
}

/**
 * Format a recovery message for the user based on classification.
 * Use this for the main error block copy.
 */
export function recoveryMessage(classified: ClassifiedError, context?: { provider?: string; retry?: number }): string {
  const { category, message } = classified;
  const { provider, retry } = context || {};

  switch (category) {
    case 'transient':
      return `Connection issue. Retrying${retry ? ` (${retry}/3)` : ''}...`;
    case 'rate_limited':
      return provider
        ? `${provider} is rate-limited. Trying next provider...`
        : 'Rate limited. Retrying with backoff...';
    case 'timeout':
      return `Request timed out. Retrying${retry ? ` (${retry}/3)` : ''}...`;
    case 'auth_failed':
      return message;
    case 'quota_exceeded':
      return message;
    case 'permission_denied':
      return message;
    case 'capability_missing':
      return message;
    case 'tool_failed':
      return message;
    case 'cancelled':
      return 'Cancelled.';
    case 'unknown':
    default:
      return message;
  }
}
