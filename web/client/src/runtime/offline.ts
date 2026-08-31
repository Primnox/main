/* Offline-aware transport wrapper.

   Token POSTs pass straight through — a failed token must fail the turn so text
   ordering stays intact (the origin client is the only writer, CRS/1.0-W §4.3).
   Order-independent, idempotent-by-id writes — `completeTurn`, `cancelTurn`, and
   control `postEvent`s (turn.failed / turn.cancelled / model.egress) — are
   queued to the LocalStore outbox on a network error and replayed by `drain()`
   when connectivity returns. The event log dedupes by the client-supplied id. */

import { newId } from '../ids';
import type { LocalStore, OutboxItem } from '../storage/idb';
import type {
  CompleteTurnArgs,
  PostEventArgs,
  StartTurnArgs,
  Transport,
} from './transport';
import type { EventRow } from './eventcodec';

const QUEUEABLE_KINDS = new Set(['turn.failed', 'turn.cancelled', 'model.egress']);

const isNetworkError = (e: unknown): boolean =>
  e instanceof TypeError || (e instanceof Error && /network|fetch|Failed to fetch/i.test(e.message));

export class OfflineAwareTransport implements Transport {
  constructor(
    private readonly inner: Transport,
    private readonly store: LocalStore,
    private readonly maxAttempts = 8,
  ) {}

  startTurn(a: StartTurnArgs): Promise<{ sequence: number }> {
    return this.inner.startTurn(a); // must reach the server; a failure fails the turn
  }

  async postEvent(a: PostEventArgs): Promise<{ sequence: number }> {
    if (!QUEUEABLE_KINDS.has(a.kind)) return this.inner.postEvent(a);
    try {
      return await this.inner.postEvent(a);
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      await this.store.enqueue({ id: newId('job'), kind: 'postEvent', args: a });
      return { sequence: -1 };
    }
  }

  async completeTurn(a: CompleteTurnArgs): Promise<{ sequence: number }> {
    try {
      return await this.inner.completeTurn(a);
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      await this.store.enqueue({ id: newId('job'), kind: 'completeTurn', args: a });
      return { sequence: -1 };
    }
  }

  async cancelTurn(turnId: string): Promise<void> {
    try {
      await this.inner.cancelTurn(turnId);
    } catch (e) {
      if (!isNetworkError(e)) throw e;
      await this.store.enqueue({ id: newId('job'), kind: 'cancelTurn', args: turnId });
    }
  }

  replay(afterSequence: number): Promise<{ events: EventRow[]; head: number }> {
    return this.inner.replay(afterSequence);
  }

  /** Flush queued writes. Safe to call repeatedly (e.g. on the `online` event). */
  async drain(): Promise<{ sent: number; failed: number }> {
    const items = await this.store.outbox();
    let sent = 0;
    let failed = 0;
    for (const item of items) {
      try {
        await this.dispatch(item);
        await this.store.dequeue(item.id);
        sent++;
      } catch (e) {
        failed++;
        if (!isNetworkError(e) || item.attempts + 1 >= this.maxAttempts) {
          await this.store.dequeue(item.id); // give up on a poison item
        } else {
          await this.store.putOutbox({ ...item, attempts: item.attempts + 1 });
        }
      }
    }
    return { sent, failed };
  }

  private dispatch(item: OutboxItem): Promise<unknown> {
    switch (item.kind) {
      case 'postEvent':
        return this.inner.postEvent(item.args as PostEventArgs);
      case 'completeTurn':
        return this.inner.completeTurn(item.args as CompleteTurnArgs);
      case 'cancelTurn':
        return this.inner.cancelTurn(item.args as string);
      default:
        return Promise.resolve();
    }
  }
}
