/* Google Gemini — streamGenerateContent with ?alt=sse.

   API-key calls send CORS headers, so this works from the browser. The system
   prompt is `systemInstruction`; history is `contents` with role 'user' |
   'model'. Usage arrives in `usageMetadata` on the final chunk. */

import { parseSSE } from '../sse';
import { ModelRequest, Provider, StreamEvent, codeForStatus } from '../types';

const DEFAULT_BASE = 'https://generativelanguage.googleapis.com/v1beta';

export const geminiProvider: Provider = {
  id: 'gemini',
  defaultBaseUrl: DEFAULT_BASE,
  async *stream(req: ModelRequest): AsyncGenerator<StreamEvent> {
    const base = req.profile.baseUrl ?? DEFAULT_BASE;
    const url =
      `${base}/models/${encodeURIComponent(req.profile.model)}:streamGenerateContent` +
      `?alt=sse&key=${encodeURIComponent(req.profile.apiKey)}`;

    const contents = req.messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: m.content }],
      }));

    const body: Record<string, unknown> = {
      contents,
      generationConfig: {
        temperature: req.profile.temperature,
        maxOutputTokens: req.profile.maxOutputTokens,
      },
    };
    if (req.system) body.systemInstruction = { parts: [{ text: req.system }] };

    let res: Response;
    try {
      res = await fetch(url, {
        method: 'POST',
        signal: req.signal,
        headers: { 'content-type': 'application/json' },
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
      let chunk: GeminiChunk;
      try {
        chunk = JSON.parse(msg.data);
      } catch {
        continue;
      }
      const cand = chunk.candidates?.[0];
      const text = cand?.content?.parts?.map((p) => p.text ?? '').join('') ?? '';
      if (text) yield { type: 'token', text };
      if (cand?.finishReason) finish = cand.finishReason;
      if (chunk.usageMetadata) {
        inputTokens = chunk.usageMetadata.promptTokenCount ?? inputTokens;
        outputTokens = chunk.usageMetadata.candidatesTokenCount ?? outputTokens;
      }
    }

    yield { type: 'usage', inputTokens, outputTokens };
    yield { type: 'done', finishReason: finish };
  },
};

interface GeminiChunk {
  candidates?: Array<{
    content?: { parts?: Array<{ text?: string }> };
    finishReason?: string;
  }>;
  usageMetadata?: { promptTokenCount?: number; candidatesTokenCount?: number };
}
