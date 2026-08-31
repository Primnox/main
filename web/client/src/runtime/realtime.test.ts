import { describe, expect, it } from 'vitest';
import { createVault } from '../crypto/vault';
import { ModelRouter } from '../model';
import type { ModelRequest, Provider, ProviderId, StreamEvent } from '../model';
import { EventFeed, MockRealtimeSource } from './realtime';
import { RuntimeStore } from './store';
import { MockTransport } from './transport';
import { turnsOf } from './reducer';
import { runTurn } from './turn';

const FAST = { alg: 'argon2id', m: 1024, t: 1, p: 1 } as const;
const profile = { provider: 'openrouter', model: 'm', apiKey: 'k' } as const;

const router = (events: StreamEvent[]) =>
  new ModelRouter({
    providers: {
      openrouter: {
        id: 'openrouter',
        defaultBaseUrl: '',
        async *stream(_r: ModelRequest) {
          for (const e of events) yield e;
        },
      } as Provider,
    } as Record<ProviderId, Provider>,
  });

describe('EventFeed', () => {
  it('replays a turn log into the store and reaches the completed state', async () => {
    const { dek } = await createVault('p', FAST);
    const transport = new MockTransport();
    await runTurn(
      { router: router([{ type: 'token', text: 'Hi' }, { type: 'done', finishReason: 'stop' }]), transport, dek, profile },
      { conversationId: 'conv_1', userText: 'yo', context: { systemPrompt: 's', history: [] } },
    );

    const store = new RuntimeStore();
    const feed = new EventFeed({ store, transport, realtime: new MockRealtimeSource(), dek });
    await feed.start(0);

    const [t] = turnsOf(store.getState(), 'conv_1');
    expect(t!.userText).toBe('yo');
    expect(t!.assistantText).toBe('Hi');
    expect(t!.status).toBe('completed');
    expect(store.getState().cursor).toBeGreaterThanOrEqual(3);
  });

  it('applies live rows that arrive after start, in order', async () => {
    const { dek } = await createVault('p', FAST);
    const transport = new MockTransport();
    const realtime = new MockRealtimeSource();
    const store = new RuntimeStore();
    const feed = new EventFeed({ store, transport, realtime, dek });
    await feed.start(0);

    // drive a turn and mirror each appended row into the live stream
    const before = transport.rows.length;
    await runTurn(
      { router: router([{ type: 'token', text: 'A' }, { type: 'token', text: 'B' }, { type: 'done', finishReason: 'stop' }]), transport, dek, profile },
      { conversationId: 'conv_1', userText: 'go', context: { systemPrompt: 's', history: [] } },
    );
    for (const row of transport.rows.slice(before)) realtime.emit(row);
    await new Promise((r) => setTimeout(r, 0));

    const [t] = turnsOf(store.getState(), 'conv_1');
    expect(t!.assistantText).toBe('AB');
    expect(t!.status).toBe('completed');
  });

  it('skips an undecryptable row without stalling the cursor', async () => {
    const { dek } = await createVault('p', FAST);
    const { dek: wrong } = await createVault('wrong', FAST);
    const transport = new MockTransport();
    await runTurn(
      { router: router([{ type: 'token', text: 'x' }, { type: 'done', finishReason: 'stop' }]), transport, dek, profile },
      { conversationId: 'conv_1', userText: 'q', context: { systemPrompt: 's', history: [] } },
    );

    const errors: unknown[] = [];
    const store = new RuntimeStore();
    const feed = new EventFeed({
      store,
      transport,
      realtime: new MockRealtimeSource(),
      dek: wrong,
      onDecryptError: (_row, e) => errors.push(e),
    });
    await feed.start(0);

    expect(errors.length).toBeGreaterThan(0);
    // cursor advanced past every row even though none could be read
    expect(store.getState().cursor).toBe(transport.rows.length);
  });
});
