import { describe, expect, it } from 'vitest';
import { createVault } from '../crypto/vault';
import { ModelRouter } from '../model';
import type { ModelRequest, Provider, ProviderId, StreamEvent } from '../model';
import { decryptEvent } from './eventcodec';
import { ingest, initialState, turnsOf } from './reducer';
import { MockTransport } from './transport';
import { runTurn, type LocalTurnEvent } from './turn';

const FAST = { alg: 'argon2id', m: 1024, t: 1, p: 1 } as const;
const profile = { provider: 'openrouter', model: 'm', apiKey: 'k' } as const;
const baseInput = {
  conversationId: 'conv_1',
  userText: 'hello',
  context: { systemPrompt: 'sys', history: [] },
};

function routerYielding(events: StreamEvent[]): ModelRouter {
  const p: Provider = {
    id: 'openrouter',
    defaultBaseUrl: '',
    async *stream(_req: ModelRequest) {
      for (const e of events) yield e;
    },
  };
  return new ModelRouter({ providers: { openrouter: p } as Record<ProviderId, Provider> });
}

/** replay the mock transport's log through decrypt + reduce, as a real client would */
async function foldMock(transport: MockTransport, dek: CryptoKey) {
  let state = initialState();
  const { events } = await transport.replay(0);
  for (const row of events) {
    state = ingest(state, await decryptEvent(dek, row));
  }
  return state;
}

describe('runTurn (end to end through crypto + reducer)', () => {
  it('drives a full turn and the log folds back to the right conversation state', async () => {
    const { dek } = await createVault('p', FAST);
    const transport = new MockTransport();
    const seen: LocalTurnEvent[] = [];

    const res = await runTurn(
      {
        router: routerYielding([
          { type: 'token', text: 'Hel' },
          { type: 'token', text: 'lo' },
          { type: 'usage', inputTokens: 5, outputTokens: 2 },
          { type: 'done', finishReason: 'stop' },
        ]),
        transport,
        dek,
        profile,
        onEvent: (e) => seen.push(e),
      },
      baseInput,
    );

    expect(res).toMatchObject({ ok: true, text: 'Hello', usage: { input: 5, output: 2 } });
    expect(seen.map((e) => e.type)).toEqual(['status', 'status', 'status', 'token', 'token', 'done']);

    const state = await foldMock(transport, dek);
    const [t] = turnsOf(state, 'conv_1');
    expect(t!.userText).toBe('hello');
    expect(t!.assistantText).toBe('Hello');
    expect(t!.status).toBe('completed');
    expect(t!.usage).toEqual({ input_tokens: 5, output_tokens: 2 });
  });

  it('posts turn.failed and stops on a provider error; the fold shows failed', async () => {
    const { dek } = await createVault('p', FAST);
    const transport = new MockTransport();

    const res = await runTurn(
      {
        router: routerYielding([
          { type: 'token', text: 'partial' },
          { type: 'error', code: 'provider_rate_limited', message: 'slow down', retryable: true },
        ]),
        transport,
        dek,
        profile,
      },
      baseInput,
    );

    expect(res).toMatchObject({ ok: false, error: { code: 'provider_rate_limited', retryable: true } });

    const state = await foldMock(transport, dek);
    const [t] = turnsOf(state, 'conv_1');
    expect(t!.assistantText).toBe('partial');
    expect(t!.status).toBe('failed');
    expect(t!.error).toMatchObject({ code: 'provider_rate_limited', retryable: true });
  });

  it('on abort: posts turn.cancelled with partial text, cancels, and the fold agrees', async () => {
    const { dek } = await createVault('p', FAST);
    const transport = new MockTransport();
    const ac = new AbortController();

    const p: Provider = {
      id: 'openrouter',
      defaultBaseUrl: '',
      async *stream() {
        yield { type: 'token', text: 'half ' } as StreamEvent;
        ac.abort();
        yield { type: 'token', text: 'more' } as StreamEvent;
      },
    };
    const router = new ModelRouter({ providers: { openrouter: p } as Record<ProviderId, Provider> });

    const res = await runTurn({ router, transport, dek, profile }, { ...baseInput, signal: ac.signal });
    expect(res).toMatchObject({ ok: false, cancelled: true });
    expect(transport.cancelled).toContain(res.turnId);

    const state = await foldMock(transport, dek);
    const [t] = turnsOf(state, 'conv_1');
    expect(t!.status).toBe('cancelled');
    expect(t!.assistantText).toBe('half ');
  });

  it('a wrong DEK cannot read the turn log', async () => {
    const { dek } = await createVault('p', FAST);
    const { dek: otherDek } = await createVault('other', FAST);
    const transport = new MockTransport();
    await runTurn(
      { router: routerYielding([{ type: 'token', text: 'x' }, { type: 'done', finishReason: 'stop' }]), transport, dek, profile },
      baseInput,
    );
    const { events } = await transport.replay(0);
    await expect(decryptEvent(otherDek, events[0]!)).rejects.toThrow();
  });

  it('refuses cleanly when the profile has no key', async () => {
    const { dek } = await createVault('p', FAST);
    const res = await runTurn(
      { router: routerYielding([{ type: 'done', finishReason: 'stop' }]), transport: new MockTransport(), dek, profile: { provider: 'openrouter', model: 'm', apiKey: '' } },
      baseInput,
    );
    expect(res).toMatchObject({ ok: false, error: { code: 'provider_auth' } });
  });
});
