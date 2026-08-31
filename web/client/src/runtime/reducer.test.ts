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

describe('reducer — turn artifacts', () => {
  it('folds a tool call and the result that answers it', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'tool.call', payload: { call_id: 'c1', name: 'search', summary: 'primnox' } }));
    expect(turnsOf(s, 'conv_1')[0].toolCalls).toEqual([
      { callId: 'c1', name: 'search', status: 'running', arguments: undefined, summary: 'primnox' },
    ]);

    s = ingest(s, ev({ kind: 'tool.result', payload: { call_id: 'c1', status: 'ok', summary: '3 hits' } }));
    const [t] = turnsOf(s, 'conv_1');
    expect(t.toolCalls).toHaveLength(1);
    expect(t.toolCalls[0].status).toBe('ok');
    expect(t.toolCalls[0].summary).toBe('3 hits');
  });

  it('matches a result to its own call when two calls share a name', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'tool.call', payload: { call_id: 'a', name: 'read' } }));
    s = ingest(s, ev({ kind: 'tool.call', payload: { call_id: 'b', name: 'read' } }));
    s = ingest(s, ev({ kind: 'tool.result', payload: { call_id: 'b', error: 'nope' } }));

    const calls = turnsOf(s, 'conv_1')[0].toolCalls;
    expect(calls.map((c) => c.status)).toEqual(['running', 'error']);
    expect(calls[1].summary).toBe('nope');
  });

  it('never synthesizes a call from an orphan result', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'tool.result', payload: { call_id: 'ghost', status: 'ok' } }));
    expect(turnsOf(s, 'conv_1')[0].toolCalls).toEqual([]);
    expect(s.cursor).toBe(1); // still acknowledged
  });

  it('folds a permission request and its resolution', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({
      kind: 'permission.request',
      payload: { id: 'p1', action: 'fs.write', detail: 'write notes.md', options: [{ id: 'allow_once', label: 'Allow once' }] },
    }));
    expect(turnsOf(s, 'conv_1')[0].permissions[0]).toMatchObject({ id: 'p1', auto: false, resolved: null });

    s = ingest(s, ev({ kind: 'permission.resolved', payload: { id: 'p1', resolution: 'allow_once' } }));
    expect(turnsOf(s, 'conv_1')[0].permissions[0].resolved).toBe('allow_once');
  });

  it('folds a ready asset', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'asset.ready', payload: { id: 'a1', name: 'report.pdf', kind: 'pdf' } }));
    expect(turnsOf(s, 'conv_1')[0].assets).toEqual([{ id: 'a1', name: 'report.pdf', kind: 'pdf' }]);
  });

  it('bumps the version of a workspace it already knows', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'workspace.created', payload: { id: 'w1', title: 'Draft', kind: 'markdown' } }));
    expect(turnsOf(s, 'conv_1')[0].workspaces[0]).toEqual({ id: 'w1', title: 'Draft', kind: 'markdown', version: 1 });

    s = ingest(s, ev({ kind: 'workspace.updated', payload: { id: 'w1', version: 2, title: 'Draft v2' } }));
    const ws = turnsOf(s, 'conv_1')[0].workspaces;
    expect(ws).toHaveLength(1);
    expect(ws[0]).toMatchObject({ version: 2, title: 'Draft v2' });
  });

  it('shows a workspace a turn only edited', () => {
    seq = 0;
    let s = initialState();
    // No workspace.created in this turn — the document was authored earlier.
    s = ingest(s, ev({ kind: 'workspace.updated', payload: { id: 'w9', version: 4 } }));
    expect(turnsOf(s, 'conv_1')[0].workspaces).toEqual([
      { id: 'w9', title: 'Document', kind: '', version: 4 },
    ]);
  });

  it('keeps artifacts on the turn that reported them', () => {
    seq = 0;
    let s = initialState();
    s = ingest(s, ev({ kind: 'tool.call', payload: { call_id: 'c1', name: 'search' } }));
    s = ingest(s, ev({ kind: 'tool.call', payload: { call_id: 'c2', name: 'write' }, turn_id: 'turn_2' }));

    const turns = turnsOf(s, 'conv_1');
    expect(turns).toHaveLength(2);
    expect(turns[0].toolCalls.map((c) => c.name)).toEqual(['search']);
    expect(turns[1].toolCalls.map((c) => c.name)).toEqual(['write']);
  });

  it('folds artifacts that arrived out of order once the gap closes', () => {
    seq = 0;
    let s = initialState();
    const call = ev({ kind: 'tool.call', payload: { call_id: 'c1', name: 'search' } }); // seq 1
    const token = ev({ kind: 'token', payload: { text: 'ok' } });                       // seq 2
    const result = ev({ kind: 'tool.result', payload: { call_id: 'c1', status: 'ok' } }); // seq 3

    s = ingest(s, call);
    s = ingest(s, result); // ahead of cursor — held
    expect(turnsOf(s, 'conv_1')[0].toolCalls[0].status).toBe('running');

    s = ingest(s, token); // closes the gap, drains the result
    expect(s.cursor).toBe(3);
    expect(turnsOf(s, 'conv_1')[0].toolCalls[0].status).toBe('ok');
  });
});
