/* Origin-disconnect watchdog (CRS/1.0-W §4.4).

   A turn's stream is driven by the browser tab that started it. If that tab
   dies mid-stream, nothing else will finish the turn — so this sweep fails any
   non-terminal turn that has gone quiet for longer than the grace window,
   preserving whatever partial assistant text already reached the log (the
   `token` events stay; the client reconstructs the partial reply by folding
   them, CRS §9.3 / §10.3.2).

   The `turn.failed` it writes carries a CLEARTEXT `{ code, message, retryable }`
   — control metadata, not user content — because the server holds no key. */

import { pool, tx } from './db.js';
import { appendEvent } from './events.js';

interface StaleTurn {
  id: string;
  conversation_id: string;
  user_id: string;
}

export interface WatchdogHandle {
  stop(): void;
}

export function startWatchdog(graceSeconds: number, intervalMs = 15_000): WatchdogHandle {
  const timer = setInterval(() => {
    void sweep(graceSeconds).catch((e) => {
      console.error('[watchdog] sweep failed', e);
    });
  }, intervalMs);
  // don't keep the process alive just for the watchdog
  if (typeof timer.unref === 'function') timer.unref();
  return { stop: () => clearInterval(timer) };
}

async function sweep(graceSeconds: number): Promise<void> {
  // non-terminal turns whose most recent event is older than the grace window
  // (or that never emitted one), older than the grace window since creation.
  const { rows } = await pool.query<StaleTurn>(
    `
    SELECT t.id, t.conversation_id, t.user_id
      FROM turns t
     WHERE t.status IN ('queued','building_context','thinking','streaming','tool_running')
       AND t.created_at < now() - make_interval(secs => $1)
       AND COALESCE(
             (SELECT max(e.ts) FROM events e WHERE e.turn_id = t.id),
             0
           ) < (extract(epoch from now()) * 1000) - ($1 * 1000)
     LIMIT 100
    `,
    [graceSeconds],
  );

  for (const turn of rows) {
    try {
      await tx(async (c) => {
        const upd = await c.query(
          `UPDATE turns
              SET status = 'failed', error_code = 'origin_disconnected', completed_at = now()
            WHERE id = $1
              AND status IN ('queued','building_context','thinking','streaming','tool_running')`,
          [turn.id],
        );
        if (upd.rowCount === 0) return; // someone finished it first
      });
      await appendEvent(turn.user_id, {
        scope: 'conversation',
        conversationId: turn.conversation_id,
        turnId: turn.id,
        kind: 'turn.failed',
        payload: {
          code: 'origin_disconnected',
          message: 'the tab that started this turn disconnected before it finished',
          retryable: true,
        },
      });
      console.info(`[watchdog] failed stale turn ${turn.id} (origin_disconnected)`);
    } catch (e) {
      console.error(`[watchdog] could not fail turn ${turn.id}`, e);
    }
  }
}
