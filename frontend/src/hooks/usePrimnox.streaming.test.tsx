import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { usePrimnox } from './usePrimnox';

/**
 * Regression guard for "AI responses are dead" — replies that sometimes
 * appeared, sometimes appeared half-written, and sometimes vanished entirely.
 *
 * Two independent causes, both here:
 *
 * 1. Streaming found its target by scanning BACKWARDS through the message
 *    list for the last one from Primnox. That is only correct while nothing
 *    else appends a Primnox message mid-turn — but a permission card, a daily
 *    brief and a proactive nudge all do. The scan would land on THAT message
 *    and overwrite it, destroying it and leaving the real reply stranded on
 *    whatever partial text it had. Any request needing approval (every skill
 *    run, every code execution) hit this.
 *
 * 2. Token batching used requestAnimationFrame, which browsers freeze
 *    completely while the window is minimised, occluded, or on another
 *    virtual desktop. Sending a message and tabbing away while Primnox thinks
 *    is the normal way to use a desktop assistant; tokens then accumulated in
 *    the buffer and were never written to the bubble.
 */

class FakeSocket {
  static last: FakeSocket | null = null;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  readyState = 1;
  close = vi.fn();
  send = vi.fn();
  constructor(public url: string) {
    FakeSocket.last = this;
    setTimeout(() => this.onopen?.(), 0);
  }
  emit(type: string, data: unknown) {
    this.onmessage?.({ data: JSON.stringify({ type, data }) });
  }
}

const socket = () => FakeSocket.last!;
const primnoxTexts = (msgs: any[]) =>
  msgs.filter(m => m.sender?.toUpperCase() === 'PRIMNOX').map(m => m.text);

beforeEach(() => {
  FakeSocket.last = null;
  vi.stubGlobal('WebSocket', FakeSocket as never);
  globalThis.fetch = vi.fn(() =>
    Promise.resolve({ ok: true, json: () => Promise.resolve([]) }),
  ) as never;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function mounted() {
  const view = renderHook(() => usePrimnox());
  await waitFor(() => expect(FakeSocket.last).not.toBeNull());
  await act(async () => { await Promise.resolve(); });
  return view;
}

/** Drives one complete reply: typing placeholder, tokens, final message. */
async function streamReply(text: string) {
  await act(async () => { socket().emit('message', { sender: 'Primnox', text: '', isTyping: true }); });
  await act(async () => { socket().emit('token', { text }); });
  await act(async () => { await new Promise(r => setTimeout(r, 60)); });
  await act(async () => { socket().emit('message', { sender: 'Primnox', text }); });
}

describe('a reply lands in its own bubble', () => {
  it('streams tokens into the bubble and finalises it', async () => {
    const { result } = await mounted();
    await streamReply('Paris is the capital of France.');

    expect(primnoxTexts(result.current.messages)).toEqual(['Paris is the capital of France.']);
  });

  it('writes tokens without waiting for an animation frame', async () => {
    // rAF is frozen while the window is hidden. Nothing here ever calls it,
    // so a stubbed-out rAF must not prevent the text from appearing.
    vi.stubGlobal('requestAnimationFrame', () => 0 as never);
    const { result } = await mounted();

    await act(async () => { socket().emit('message', { sender: 'Primnox', text: '', isTyping: true }); });
    await act(async () => { socket().emit('token', { text: 'hello' }); });
    await act(async () => { await new Promise(r => setTimeout(r, 60)); });

    expect(primnoxTexts(result.current.messages)).toEqual(['hello']);
  });

  it('keeps earlier replies intact across several turns', async () => {
    const { result } = await mounted();
    await streamReply('first answer');
    await act(async () => { socket().emit('message', { sender: 'You', text: 'next question' }); });
    await streamReply('second answer');

    expect(primnoxTexts(result.current.messages)).toEqual(['first answer', 'second answer']);
  });
});

describe('a permission card does not eat the reply', () => {
  it('leaves the card standing and finalises the reply separately', async () => {
    const { result } = await mounted();

    await act(async () => { socket().emit('message', { sender: 'Primnox', text: '', isTyping: true }); });
    await act(async () => { socket().emit('token', { text: 'Building your PDF' }); });
    await act(async () => { await new Promise(r => setTimeout(r, 60)); });
    // Mid-turn, the backend asks for approval — appending another Primnox
    // message. The old backward scan targeted THIS from here on.
    await act(async () => {
      socket().emit('permission_request', { token: 'tok1', action: 'run_python', description: 'Run this?' });
    });
    await act(async () => { socket().emit('message', { sender: 'Primnox', text: 'Done — coffee.pdf is ready.' }); });

    const texts = primnoxTexts(result.current.messages);
    expect(texts).toContain('Done — coffee.pdf is ready.');
    expect(texts.some(t => t?.includes('Run this?'))).toBe(true);
    expect(texts).not.toContain('Building your PDF');
  });

  it('routes tokens arriving after the card to the reply, not the card', async () => {
    const { result } = await mounted();

    await act(async () => { socket().emit('message', { sender: 'Primnox', text: '', isTyping: true }); });
    await act(async () => {
      socket().emit('permission_request', { token: 'tok2', action: 'run_python', description: 'Approve?' });
    });
    await act(async () => { socket().emit('token', { text: 'still writing the answer' }); });
    await act(async () => { await new Promise(r => setTimeout(r, 60)); });

    const texts = primnoxTexts(result.current.messages);
    expect(texts).toContain('still writing the answer');
    expect(texts.some(t => t?.includes('Approve?') && t.includes('still writing'))).toBe(false);
  });
});

describe('a reply with no preceding typing event', () => {
  it('is appended rather than merged into an existing message', async () => {
    // Reminders and tool results arrive cold, with no stream to join.
    const { result } = await mounted();
    await streamReply('an earlier answer');
    await act(async () => { socket().emit('message', { sender: 'Primnox', text: 'Reminder: standup in 5.' }); });

    expect(primnoxTexts(result.current.messages)).toEqual(['an earlier answer', 'Reminder: standup in 5.']);
  });
});

describe('losing the connection mid-reply', () => {
  it('stops the typing animation and says it was cut off', async () => {
    const { result } = await mounted();

    await act(async () => { socket().emit('message', { sender: 'Primnox', text: '', isTyping: true }); });
    await act(async () => { socket().emit('token', { text: 'half an ans' }); });
    await act(async () => { await new Promise(r => setTimeout(r, 60)); });
    await act(async () => { socket().onclose?.(); });

    const last = result.current.messages.at(-1);
    expect(last.isTyping).toBe(false);
    expect(last.text).toContain('half an ans');
    expect(last.text).toContain('disconnected');
  });
});
