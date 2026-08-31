import { describe, expect, it } from 'vitest';
import { LocalStore } from '../storage/idb';
import { MockTransport } from './transport';
import { OfflineAwareTransport } from './offline';

const sealed = { v: 1, alg: 'A256GCM', iv: 'i', ct: 'c' } as const;

class FlakyTransport extends MockTransport {
  offline = true;
  override async completeTurn(a: Parameters<MockTransport['completeTurn']>[0]) {
    if (this.offline) throw new TypeError('Failed to fetch');
    return super.completeTurn(a);
  }
  override async postEvent(a: Parameters<MockTransport['postEvent']>[0]) {
    if (this.offline) throw new TypeError('Failed to fetch');
    return super.postEvent(a);
  }
}

const completeArgs = () => ({
  turnId: 'turn_1',
  conversationId: 'conv_1',
  assistantMessageId: 'msg_a',
  assistantMessage: sealed,
  completionEventId: 'evt_c',
  completion: sealed,
});

describe('OfflineAwareTransport', () => {
  it('queues completeTurn on a network error and drains it when back online', async () => {
    const inner = new FlakyTransport();
    const store = new LocalStore();
    const t = new OfflineAwareTransport(inner, store);

    const r = await t.completeTurn(completeArgs());
    expect(r.sequence).toBe(-1); // optimistic
    expect((await store.outbox()).map((i) => i.kind)).toEqual(['completeTurn']);

    inner.offline = false;
    const drained = await t.drain();
    expect(drained.sent).toBe(1);
    expect(await store.outbox()).toHaveLength(0);
    expect(inner.completed).toContain('turn_1');
  });

  it('queues a control postEvent (turn.failed) but never a token', async () => {
    const inner = new FlakyTransport();
    const store = new LocalStore();
    const t = new OfflineAwareTransport(inner, store);

    await t.postEvent({ eventId: 'evt_1', turnId: 'turn_1', conversationId: 'conv_1', kind: 'turn.failed', payload: sealed });
    expect(await store.outbox()).toHaveLength(1);

    await expect(
      t.postEvent({ eventId: 'evt_2', turnId: 'turn_1', conversationId: 'conv_1', kind: 'token', payload: sealed }),
    ).rejects.toThrow(/fetch/i); // tokens must fail loudly
  });

  it('re-throws non-network errors instead of queueing', async () => {
    const inner = new MockTransport();
    inner.completeTurn = async () => {
      throw new Error('malformed id');
    };
    const store = new LocalStore();
    const t = new OfflineAwareTransport(inner, store);
    await expect(t.completeTurn(completeArgs())).rejects.toThrow(/malformed/);
    expect(await store.outbox()).toHaveLength(0);
  });

  it('drops a poison item after maxAttempts drains', async () => {
    const inner = new MockTransport();
    inner.completeTurn = async () => {
      throw new TypeError('Failed to fetch');
    };
    const store = new LocalStore();
    const t = new OfflineAwareTransport(inner, store, 3);
    await store.enqueue({ id: 'job_x', kind: 'completeTurn', args: completeArgs() });

    await t.drain(); // attempts 0 -> 1, kept
    expect((await store.outbox())[0]!.attempts).toBe(1);
    await t.drain(); // 1 -> 2, kept
    await t.drain(); // 2 -> 3 == maxAttempts, dropped
    expect(await store.outbox()).toHaveLength(0);
  });
});
