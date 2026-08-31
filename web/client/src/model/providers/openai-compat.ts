/* OpenAI-compatible chat completions streaming.

   Covers OpenRouter and Groq (and, via OpenRouter, OpenAI models — Q6). The
   wire format is identical; only the base URL and a couple of headers differ. */

import { parseSSE } from '../sse';
import {
  ModelRequest,
  Provider,
  ProviderId,
  StreamEvent,
  codeForStatus,
} from '../types';

interface Options {
  id: ProviderId;
  defaultBaseUrl: string;
  extraHeaders?: (req: ModelRequest) => Record<string, string>;
}

export function makeOpenAICompatProvider(opts: Options): Provider {
  return {
    id: opts.id,
    defaultBaseUrl: opts.defaultBaseUrl,
    async *stream(req: ModelRequest): AsyncGenerator<StreamEvent> {
      const base = req.profile.baseUrl ?? opts.defaultBaseUrl;
      const messages = req.system
        ? [{ role: 'system', content: req.system }, ...req.messages]
        : req.messages;

      let res: Response;
      try {
        res = await fetch(`${base}/chat/completions`, {
          method: 'POST',
          signal: req.signal,
          headers: {
            'content-type': 'application/json',
            authorization: `Bearer ${req.profile.apiKey}`,
            ...(opts.extraHeaders?.(req) ?? {}),
          },
          body: JSON.stringify({
            model: req.profile.model,
            messages,
            stream: true,
            stream_options: { include_usage: true },
            temperature: req.profile.temperature,
            max_tokens: req.profile.maxOutputTokens,
          }),
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
        yield { type: 'error', code, message: await safeText(res), retryable };
        return;
      }

      let finish = 'stop';
      for await (const msg of parseSSE(res.body, req.signal)) {
        const line = msg.data.trim();
        if (!line || line === '[DONE]') continue;
        let json: OACompletionChunk;
        try {
          json = JSON.parse(line);
        } catch {
          continue;
        }
        const choice = json.choices?.[0];
        const delta = choice?.delta?.content;
        if (delta) yield { type: 'token', text: delta };
        if (choice?.finish_reason) finish = choice.finish_reason;
        if (json.usage) {
          yield {
            type: 'usage',
            inputTokens: json.usage.prompt_tokens ?? 0,
            outputTokens: json.usage.completion_tokens ?? 0,
          };
        }
      }
      yield { type: 'done', finishReason: finish };
    },
  };
}

async function safeText(res: Response): Promise<string> {
  try {
    const t = await res.text();
    return t.slice(0, 500);
  } catch {
    return `HTTP ${res.status}`;
  }
}

interface OACompletionChunk {
  choices?: Array<{
    delta?: { content?: string };
    finish_reason?: string | null;
  }>;
  usage?: { prompt_tokens?: number; completion_tokens?: number };
}
