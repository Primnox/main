import { describe, expect, it, vi } from 'vitest';
import { ModelRouter, approxTokens } from './router';
import { Provider, ProviderId, StreamEvent } from './types';

const fakeProvider = (id: ProviderId, events: StreamEvent[]): Provider => ({
  id,
  defaultBaseUrl: 'https://fake',
  async *stream() {
    for (const e of events) yield e;
  },
});

async function drain(gen: AsyncGenerator<StreamEvent>) {
  const out: StreamEvent[] = [];
  for await (const e of gen) out.push(e);
  return out;
}

describe('ModelRouter', () => {
  it('routes to the named provider and passes events through', async () => {
    const router = new ModelRouter({
      providers: {
        openrouter: fakeProvider('openrouter', [{ type: 'token', text: 'ok' }, { type: 'done', finishReason: 'stop' }]),
      } as Record<ProviderId, Provider>,
    });
    const out = await drain(
      router.stream({ messages: [{ role: 'user', content: 'x' }], profile: { provider: 'openrouter', model: 'm', apiKey: 'k' } }),
    );
    expect(out.map((e) => e.type)).toEqual(['token', 'done']);
  });

  it('errors cleanly when no adapter exists for the provider', async () => {
    const router = new ModelRouter({ providers: {} as Record<ProviderId, Provider> });
    const [e] = await drain(
      router.stream({ messages: [], profile: { provider: 'gemini', model: 'm', apiKey: 'k' } }),
    );
    expect(e).toMatchObject({ type: 'error', code: 'model_unavailable', retryable: false });
  });

  it('refuses to call a provider with no key unlocked (§4.6)', async () => {
    const spy = vi.fn();
    const router = new ModelRouter({
      providers: { openrouter: { id: 'openrouter', defaultBaseUrl: '', stream: spy } } as unknown as Record<ProviderId, Provider>,
    });
    const [e] = await drain(
      router.stream({ messages: [], profile: { provider: 'openrouter', model: 'm', apiKey: '' } }),
    );
    expect(e).toMatchObject({ type: 'error', code: 'provider_auth' });
    expect(spy).not.toHaveBeenCalled();
  });

  it('emits the model.egress fact before streaming (counts only)', async () => {
    const facts: Array<{ provider: string; approxInputTokens: number }> = [];
    const router = new ModelRouter({
      providers: { anthropic: fakeProvider('anthropic', [{ type: 'done', finishReason: 'stop' }]) } as Record<ProviderId, Provider>,
      onEgress: (f) => facts.push(f),
    });
    await drain(
      router.stream({
        system: 'x'.repeat(40),
        messages: [{ role: 'user', content: 'y'.repeat(40) }],
        profile: { provider: 'anthropic', model: 'claude', apiKey: 'k' },
      }),
    );
    expect(facts).toHaveLength(1);
    expect(facts[0]).toMatchObject({ provider: 'anthropic' });
    expect(facts[0]!.approxInputTokens).toBeGreaterThan(0);
  });
});

describe('approxTokens', () => {
  it('is roughly chars/4', () => {
    expect(approxTokens({ system: '', messages: [{ role: 'user', content: 'a'.repeat(40) }] })).toBe(11);
  });
});
