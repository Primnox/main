/* A tiny observable wrapper around the reducer, shaped for React's
   useSyncExternalStore. Feed it decrypted events (from the Realtime
   subscription or a replay); components read conversation state out. */

import type { AnyEvent, Envelope } from './events';
import { type RuntimeState, ingest, initialState, setCursorToHead, skip } from './reducer';

export class RuntimeStore {
  private state: RuntimeState;
  private readonly listeners = new Set<() => void>();

  constructor(cursor = 0) {
    this.state = initialState(cursor);
  }

  getState = (): RuntimeState => this.state;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private emit(): void {
    for (const l of this.listeners) l();
  }

  /** Fold one decrypted event. No-ops (dedupe / gap-buffer) do not notify. */
  ingest(ev: AnyEvent): void {
    const next = ingest(this.state, ev);
    if (next !== this.state) {
      this.state = next;
      this.emit();
    }
  }

  /** Acknowledge an event that could not be decrypted / was rejected (§4.2),
      advancing the cursor past it without applying anything. */
  skip(envelope: Envelope): void {
    const next = skip(this.state, envelope);
    if (next !== this.state) {
      this.state = next;
      this.emit();
    }
  }

  /** CRS §8.2 — on sync.complete, jump the cursor to head. */
  syncToHead(head: number): void {
    const next = setCursorToHead(this.state, head);
    if (next !== this.state) {
      this.state = next;
      this.emit();
    }
  }
}
