/* Model Router types (CRS/1.0-W §5, §10).

   The router runs in the browser and calls providers directly. One normalized
   `StreamEvent` shape regardless of provider wire format — the runtime owns the
   contract, providers adapt to it (CRS §13.1). */

export type Role = 'system' | 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  role: Role;
  content: string;
  /** set on role: 'tool' — which call this result answers */
  toolCallId?: string;
  name?: string;
}

export type ProviderId = 'openrouter' | 'anthropic' | 'gemini' | 'groq';

export interface ModelProfile {
  provider: ProviderId;
  model: string;
  apiKey: string;
  /** override the provider's default base URL */
  baseUrl?: string;
  maxOutputTokens?: number;
  temperature?: number;
}

export interface ModelRequest {
  system?: string;
  messages: ChatMessage[];
  profile: ModelProfile;
  signal?: AbortSignal;
}

export type StreamEvent =
  | { type: 'token'; text: string }
  | { type: 'usage'; inputTokens: number; outputTokens: number }
  | { type: 'done'; finishReason: string }
  | { type: 'error'; code: ErrorCode; message: string; retryable: boolean };

/** Aligned with CRS §10.2 error codes. */
export type ErrorCode =
  | 'provider_unreachable'
  | 'provider_rate_limited'
  | 'provider_auth'
  | 'provider_quota'
  | 'model_unavailable'
  | 'context_overflow'
  | 'cancelled_by_user'
  | 'internal';

export interface Provider {
  id: ProviderId;
  defaultBaseUrl: string;
  stream(req: ModelRequest): AsyncGenerator<StreamEvent>;
}

/** Map an HTTP status from a provider to a CRS error code. */
export function codeForStatus(status: number): { code: ErrorCode; retryable: boolean } {
  if (status === 401 || status === 403) return { code: 'provider_auth', retryable: false };
  if (status === 402) return { code: 'provider_quota', retryable: false };
  if (status === 404) return { code: 'model_unavailable', retryable: false };
  if (status === 429) return { code: 'provider_rate_limited', retryable: true };
  if (status >= 500) return { code: 'provider_unreachable', retryable: true };
  return { code: 'internal', retryable: false };
}
