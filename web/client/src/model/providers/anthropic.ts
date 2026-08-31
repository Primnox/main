/* Anthropic Messages API, streamed.

   Requires the explicit browser opt-in header
   `anthropic-dangerous-direct-browser-access: true` (§10.2). System prompt is a
   top-level field, not a message. SSE events are typed:
   message_start / content_block_delta / message_delta / message_stop / error. */

import { parseSSE } from '../sse';
import { ModelRequest, Provider, StreamEvent, codeForStatus } from '../types';

const DEFAULT_BASE = 'https://api.anthropic.com/v1';

export const anthropicProvider: Provider = {
  id: 'anthropic',
  defaultBaseUrl: DEFAULT_BASE,
  async *stream(req: ModelRequest): AsyncGenerator<StreamEvent> {
    const base = req.profile.baseUrl ?? DEFAULT_BASE;
    const body = {
      model: req.profile.model,
      system: req.system,
      max_tokens: req.profile.maxOutputTokens ?? 4096,
      temperature: req.profile.temperature,
      stream: true,
      messages: req.messages
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .map((m) => ({ role: m.role, content: m.content })),
    };

    let res: Response;
    try {
      res = await fetch(`${base}/messages`, {
        method: 'POST',
        signal: req.signal,
        headers: {
          'content-type': 'application/json',
          'x-api-key': req.profile.apiKey,
          'anthropic-version': '2023-06-01',
          'anthropic-dangerous-direct-browser-access': 'true',
        },
        body: JSON.stringify(body),
      });
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        yield { type: 'error', code: 'cancelled_by_user', message: 'cancelled', retryable: false };
        return;
      }
      yield { type: 'error', code: 'provider_unreachable', message: String(e), retryable: true };
      return;
    }

    if (!res.ok || !res.body) {
      const { code, retryable } = codeForStatus(res.status);
      let message = `HTTP ${res.status}`;
      try {
        message = (await res.text()).slice(0, 500);
      } catch {
        /* ignore */
      }
      yield { type: 'error', code, message, retryable };
      return;
    }

    let inputTokens = 0;
    let outputTokens = 0;
    let finish = 'stop';

    for await (const msg of parseSSE(res.body, req.signal)) {
      if (!msg.data) continue;
      let ev: AnthropicEvent;
      try {
        ev = JSON.parse(msg.data);
      } catch {
        continue;
      }
      switch (ev.type) {
        case 'message_start':
          inputTokens = ev.message?.usage?.input_tokens ?? 0;
          break;
        case 'content_block_delta':
          if (ev.delta?.type === 'text_delta' && ev.delta.text) {
            yield { type: 'token', text: ev.delta.text };
          }
          break;
        case 'message_delta':
          if (ev.usage?.output_tokens) outputTokens = ev.usage.output_tokens;
          if (ev.delta?.stop_reason) finish = ev.delta.stop_reason;
          break;
        case 'error':
          yield {
            type: 'error',
            code: 'internal',
            message: ev.error?.message ?? 'anthropic stream error',
            retryable: true,
          };
          return;
        default:
          break;
      }
    }

    yield { type: 'usage', inputTokens, outputTokens };
    yield { type: 'done', finishReason: finish };
  },
};

interface AnthropicEvent {
  type: string;
  message?: { usage?: { input_tokens?: number } };
  delta?: { type?: string; text?: string; stop_reason?: string };
  usage?: { output_tokens?: number };
  error?: { message?: string };
}
