import { describe, expect, it } from 'vitest';
import { AnyEvent } from './events';
import { ingest, initialState, setCursorToHead, turnsOf } from './reducer';

let seq = 0;
type EvOver = Omit<Partial<AnyEvent>, 'kind'> & { kind: string; payload: unknown };
const ev = (over: EvOver): AnyEvent =>
  ({
    event_id: `evt_${++seq}`,
    sequence: seq,
    ts: Date.now(),
    scope: 'conversation',
    conversation_id: 'conv_1',
    turn_id: 'turn_1',
    ...over,
  }) as AnyEvent;

describe('reducer', () => {
  it('folds a full turn in order', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'turn.created', payload: { turn: { id: 'turn_1', seq_in_conversation: 1 }, user_text: 'hi' } }));
    s = ingest(s, ev({ kind: 'turn.status', payload: { status: 'thinking' } }));
    s = ingest(s, ev({ kind: 'token', payload: { text: 'he' } }));
    s = ingest(s, ev({ kind: 'token', payload: { text: 'llo' } }));
    s = ingest(s, ev({ kind: 'turn.completed', payload: { assistant_text: 'hello', usage: { input_tokens: 3, output_tokens: 2 } } }));

    const [t] = turnsOf(s, 'conv_1');
    expect(t.userText).toBe('hi');
    expect(t.assistantText).toBe('hello');
    expect(t.status).toBe('completed');
    expect(t.usage).toEqual({ input_tokens: 3, output_tokens: 2 });
    expect(s.cursor).toBe(5);
  });

  it('dedupes by event_id', () => {
    seq = 0;
    let s = initialState();
    const a = ev({ kind: 'token', payload: { text: 'x' } });
    s = ingest(s, a);
    s = ingest(s, a);
    expect(turnsOf(s, 'conv_1')[0].assistantText).toBe('x');
    expect(s.cursor).toBe(1);
  });

  it('buffers an ahead-of-cursor event and drains it when the gap closes', () => {
    seq = 0;
    let s = initialState();
    const e1 = ev({ kind: 'token', payload: { text: 'a' } }); // seq 1
    const e2 = ev({ kind: 'token', payload: { text: 'b' } }); // seq 2
    const e3 = ev({ kind: 'token', payload: { text: 'c' } }); // seq 3

    s = ingest(s, e1);
    s = ingest(s, e3); // gap — held
    expect(s.cursor).toBe(1);
    expect(s.buffer).toHaveLength(1);
    expect(turnsOf(s, 'conv_1')[0].assistantText).toBe('a');

    s = ingest(s, e2); // closes the gap, drains e3
    expect(s.cursor).toBe(3);
    expect(s.buffer).toHaveLength(0);
    expect(turnsOf(s, 'conv_1')[0].assistantText).toBe('abc');
  });

  it('drops events at or below the cursor', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'token', payload: { text: 'a' } })); // seq 1
    s = ingest(s, ev({ kind: 'token', payload: { text: 'b' } })); // seq 2
    const stale = ev({ kind: 'token', payload: { text: 'Z' }, event_id: 'evt_stale', sequence: 1 });
    s = ingest(s, stale);
    expect(turnsOf(s, 'conv_1')[0].assistantText).toBe('ab');
  });

  it('ignores an unknown kind but still advances the cursor', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'weird.future.kind', payload: {} }));
    expect(s.cursor).toBe(1);
  });

  it('setCursorToHead jumps past filtered events and clears stale buffer', () => {
    let s = initialState(10);
    s = { ...s, buffer: [{ event_id: 'e', sequence: 12, ts: 0, scope: 'conversation', conversation_id: 'c', turn_id: null, payload: {} } as AnyEvent] };
    s = setCursorToHead(s, 15);
    expect(s.cursor).toBe(15);
    expect(s.buffer).toHaveLength(0);
  });

  it('keeps assistant text on cancel', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'token', payload: { text: 'half ' } }));
    s = ingest(s, ev({ kind: 'token', payload: { text: 'written' } }));
    s = ingest(s, ev({ kind: 'turn.cancelled', payload: { partial_text: 'half written' } }));
    const [t] = turnsOf(s, 'conv_1');
    expect(t.status).toBe('cancelled');
    expect(t.assistantText).toBe('half written');
  });
});
