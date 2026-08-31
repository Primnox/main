import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamOf } from './sse';
import { makeOpenAICompatProvider } from './providers/openai-compat';
import { anthropicProvider } from './providers/anthropic';
import { geminiProvider } from './providers/gemini';
import { ModelRequest, StreamEvent } from './types';

const req = (over: Partial<ModelRequest> = {}): ModelRequest => ({
  system: 'be brief',
  messages: [{ role: 'user', content: 'hi' }],
  profile: { provider: 'openrouter', model: 'x', apiKey: 'k' },
  ...over,
});

function mockFetch(chunks: string[], init: ResponseInit = { status: 200 }) {
  globalThis.fetch = vi.fn(async () => new Response(streamOf(chunks), init)) as typeof fetch;
}

async function drain(gen: AsyncGenerator<StreamEvent>) {
  const events: StreamEvent[] = [];
  for await (const e of gen) events.push(e);
  return events;
}
const text = (events: StreamEvent[]) =>
  events.filter((e) => e.type === 'token').map((e) => (e as { text: string }).text).join('');

afterEach(() => vi.restoreAllMocks());

describe('openai-compat provider', () => {
  const p = makeOpenAICompatProvider({ id: 'openrouter', defaultBaseUrl: 'https://x/v1' });

  it('streams tokens, usage and a finish reason', async () => {
    mockFetch([
      'data: {"choices":[{"delta":{"content":"Hel"}}]}\n\n',
      'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}\n\n',
      'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n',
      'data: [DONE]\n\n',
    ]);
    const events = await drain(p.stream(req()));
    expect(text(events)).toBe('Hello');
    expect(events).toContainEqual({ type: 'usage', inputTokens: 10, outputTokens: 2 });
    expect(events.at(-1)).toEqual({ type: 'done', finishReason: 'stop' });
  });

  it('maps a 401 to provider_auth, not retryable', async () => {
    mockFetch(['nope'], { status: 401 });
    const events = await drain(p.stream(req()));
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: 'error', code: 'provider_auth', retryable: false });
  });

  it('maps a 429 to provider_rate_limited, retryable', async () => {
    mockFetch(['slow down'], { status: 429 });
    const [e] = await drain(p.stream(req()));
    expect(e).toMatchObject({ type: 'error', code: 'provider_rate_limited', retryable: true });
  });
});

describe('anthropic provider', () => {
  it('translates the typed event stream', async () => {
    mockFetch([
      'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":7}}}\n\n',
      'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hi"}}\n\n',
      'event: message_delta\ndata: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":3}}\n\n',
      'event: message_stop\ndata: {"type":"message_stop"}\n\n',
    ]);
    const events = await drain(anthropicProvider.stream(req({ profile: { provider: 'anthropic', model: 'claude', apiKey: 'k' } })));
    expect(text(events)).toBe('Hi');
    expect(events).toContainEqual({ type: 'usage', inputTokens: 7, outputTokens: 3 });
    expect(events.at(-1)).toEqual({ type: 'done', finishReason: 'end_turn' });
  });

  it('sends the direct-browser-access header', async () => {
    const spy = vi.fn(
      (_url: string, _init: RequestInit): Promise<Response> =>
        Promise.resolve(
          new Response(streamOf(['event: message_stop\ndata: {"type":"message_stop"}\n\n']), {
            status: 200,
          }),
        ),
    );
    globalThis.fetch = spy as unknown as typeof fetch;
    await drain(anthropicProvider.stream(req({ profile: { provider: 'anthropic', model: 'c', apiKey: 'k' } })));
    const init = spy.mock.calls[0]![1];
    const headers = init.headers as Record<string, string>;
    expect(headers['anthropic-dangerous-direct-browser-access']).toBe('true');
    expect(headers['x-api-key']).toBe('k');
  });
});

describe('gemini provider', () => {
  it('reads candidates parts and usageMetadata', async () => {
    mockFetch([
      'data: {"candidates":[{"content":{"parts":[{"text":"Hey"}]}}]}\n\n',
      'data: {"candidates":[{"content":{"parts":[{"text":" there"}]},"finishReason":"STOP"}],"usageMetadata":{"promptTokenCount":5,"candidatesTokenCount":2}}\n\n',
    ]);
    const events = await drain(geminiProvider.stream(req({ profile: { provider: 'gemini', model: 'gemini-1.5-flash', apiKey: 'k' } })));
    expect(text(events)).toBe('Hey there');
    expect(events).toContainEqual({ type: 'usage', inputTokens: 5, outputTokens: 2 });
    expect(events.at(-1)).toEqual({ type: 'done', finishReason: 'STOP' });
  });
});
