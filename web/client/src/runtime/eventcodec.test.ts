import { describe, expect, it } from 'vitest';
import { createVault } from '../crypto/vault';
import { decryptEvent, sealEventPayload, type EventRow } from './eventcodec';

const FAST = { alg: 'argon2id', m: 1024, t: 1, p: 1 } as const;

const row = (over: Partial<EventRow>): EventRow => ({
  event_id: 'evt_1',
  sequence: 1,
  ts: Date.now(),
  scope: 'conversation',
  conversation_id: 'conv_1',
  turn_id: 'turn_1',
  kind: 'token',
  payload_ct: null,
  ...over,
});

describe('eventcodec', () => {
  it('round-trips a sealed payload bound by AAD to event id + kind', async () => {
    const { dek } = await createVault('p', FAST);
    const sealed = await sealEventPayload(dek, 'evt_9', 'token', { text: 'hi' });
    const ev = await decryptEvent(dek, row({ event_id: 'evt_9', kind: 'token', payload_ct: sealed }));
    expect(ev).toMatchObject({ event_id: 'evt_9', kind: 'token', payload: { text: 'hi' } });
  });

  it('fails if the event id in the row does not match the sealed AAD', async () => {
    const { dek } = await createVault('p', FAST);
    const sealed = await sealEventPayload(dek, 'evt_9', 'token', { text: 'hi' });
    await expect(
      decryptEvent(dek, row({ event_id: 'evt_TAMPERED', kind: 'token', payload_ct: sealed })),
    ).rejects.toThrow();
  });

  it('fails if the kind does not match the sealed AAD', async () => {
    const { dek } = await createVault('p', FAST);
    const sealed = await sealEventPayload(dek, 'evt_9', 'token', { text: 'hi' });
    await expect(
      decryptEvent(dek, row({ event_id: 'evt_9', kind: 'tool.call', payload_ct: sealed })),
    ).rejects.toThrow();
  });

  it('accepts an unsealed control payload for turn.failed (§4.2 carve-out)', async () => {
    const { dek } = await createVault('p', FAST);
    const ev = await decryptEvent(
      dek,
      row({
        kind: 'turn.failed',
        payload_ct: { code: 'origin_disconnected', message: 'tab closed', retryable: true },
      }),
    );
    expect(ev.payload).toMatchObject({ code: 'origin_disconnected', retryable: true });
  });

  it('accepts an unsealed control payload delivered as a JSON string', async () => {
    const { dek } = await createVault('p', FAST);
    const ev = await decryptEvent(
      dek,
      row({ kind: 'sync.complete', payload_ct: JSON.stringify({ head: 42 }) }),
    );
    expect(ev.payload).toEqual({ head: 42 });
  });

  it('REJECTS an unsealed payload for token', async () => {
    const { dek } = await createVault('p', FAST);
    await expect(
      decryptEvent(dek, row({ kind: 'token', payload_ct: { text: 'sneaky cleartext' } })),
    ).rejects.toThrow(/unsealed/i);
  });

  it('REJECTS an unsealed payload for memory.written', async () => {
    const { dek } = await createVault('p', FAST);
    await expect(
      decryptEvent(dek, row({ kind: 'memory.written', payload_ct: { text: 'x' } })),
    ).rejects.toThrow(/unsealed/i);
  });
});
