import { useEffect, useState } from 'react';

/* Seconds since a timestamp, ticking while `live`.
 *
 * This exists because a spinner cannot say what it appears to say.
 *
 * The original note here claimed a spinner "keeps turning if the socket
 * dropped" — that a CSS animation runs regardless of whether work is happening.
 * On this app that was worse than imprecise, it was backwards: the global
 * reduced-motion reset set `animation-iteration-count: 1` with a 0.01ms
 * duration on every element, which does not slow a spinner but FREEZES it after
 * one instant rotation. With Reduce Motion enabled the spinner never moved at
 * all, so the interface looked hung at precisely the moment it was working.
 * That is fixed at the source (`.px-spin` in tailwind.css).
 *
 * The reason for a count stands either way, and is the stronger one: a spinner
 * looks the same whether tokens are arriving or the provider has hung. "Working"
 * and "wedged" render identically. On a local 7B that partially offloads to CPU,
 * slow replies are the normal case rather than the edge one.
 *
 * A number that increments can only increment if React is still rendering and
 * the turn is still open. That is the part a user can actually trust.
 *
 * One interval per live turn, cleared the moment it terminates: turns are
 * usually one-at-a-time, and a stray timer on a finished turn would keep the
 * component re-rendering for the life of the conversation.
 */
export function useElapsed(since: number, live: boolean): number {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!live) return;
    // Set immediately as well as on the interval, so reopening a conversation
    // with a turn already in flight shows the real age rather than 0.
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [live, since]);

  if (!since) return 0;
  return Math.max(0, Math.floor((now - since) / 1000));
}

/** `8s`, `1m 04s`. Seconds stay visible past a minute — the question being
 *  answered is "is this moving", and a value that only changes once a minute
 *  answers it no better than the spinner did. */
export function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${String(s).padStart(2, '0')}s`;
}
