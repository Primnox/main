/* Event feed (CRS §8.1, CRS/1.0-W §4.5).

   Subscribe to the Realtime stream first (so nothing is missed), then replay
   the gap since `fromSequence` over HTTP, then drain anything that arrived
   during the replay. Every row is decrypted with the DEK and handed to the
   store; a row that fails decryption or the §4.2 carve-out is acknowledged via
   `store.skip` so the cursor never stalls. */

import { decryptEvent, type EventRow } from './eventcodec';
import type { Envelope } from './events';
import type { RuntimeStore } from './store';
import type { Transport } from './transport';

export interface RealtimeSource {
  /** deliver each new `events` row for the current user; returns unsubscribe */
  onInsert(cb: (row: EventRow) => void): () => void;
}

export interface EventFeedDeps {
  store: RuntimeStore;
  transport: Transport;
  realtime: RealtimeSource;
  dek: CryptoKey;
  onDecryptError?: (row: EventRow, err: unknown) => void;
}

const envelopeOf = (row: EventRow): Envelope => ({
  event_id: row.event_id,
  sequence: Number(row.sequence),
  ts: Number(row.ts),
  scope: row.scope,
  conversation_id: row.conversation_id,
  turn_id: row.turn_id,
  kind: row.kind as Envelope['kind'],
});

export class EventFeed {
  private unsub: (() => void) | null = null;
  private started = false;
  private replaying = false;
  private buffered: EventRow[] = [];
  private inflight = 0;
  private idleWaiters: Array<() => void> = [];

  constructor(private readonly deps: EventFeedDeps) {}

  /** Resolves when every live row received so far has been applied. */
  whenIdle(): Promise<void> {
    if (this.inflight === 0) return Promise.resolve();
    return new Promise((resolve) => this.idleWaiters.push(resolve));
  }

  async start(fromSequence = 0): Promise<void> {
    if (this.started) return;
    this.started = true;

    this.replaying = true;
    this.unsub = this.deps.realtime.onInsert((row) => {
      if (this.replaying) this.buffered.push(row);
      else void this.track(this.apply(row));
    });

    const { events, head } = await this.deps.transport.replay(fromSequence);
    for (const row of events) await this.apply(row);
    this.deps.store.syncToHead(head); // CRS §8.2

    this.replaying = false;
    const drain = this.buffered;
    this.buffered = [];
    for (const row of drain) await this.apply(row);
  }

  stop(): void {
    this.unsub?.();
    this.unsub = null;
    this.started = false;
  }

  private async apply(row: EventRow): Promise<void> {
    try {
      this.deps.store.ingest(await decryptEvent(this.deps.dek, row));
    } catch (e) {
      this.deps.onDecryptError?.(row, e);
      this.deps.store.skip(envelopeOf(row));
    }
  }

  private track(p: Promise<void>): Promise<void> {
    this.inflight++;
    return p.finally(() => {
      if (--this.inflight === 0) {
        const waiters = this.idleWaiters;
        this.idleWaiters = [];
        for (const w of waiters) w();
      }
    });
  }
}

/* In-memory Realtime for tests / offline dev — a MockTransport can push its
   appended rows straight through this. */
export class MockRealtimeSource implements RealtimeSource {
  private listeners = new Set<(row: EventRow) => void>();
  onInsert(cb: (row: EventRow) => void): () => void {
    this.listeners.add(cb);
    return () => this.listeners.delete(cb);
  }
  emit(row: EventRow): void {
    for (const l of this.listeners) l(row);
  }
}
