/* The event log (CRS §3, §4.2; CRS/1.0-W §4.1–§4.3).

   One append bumps the single global counter row and inserts the event in the
   same transaction — the counter is gapless because a rollback takes the
   increment with it. `payload_ct` is opaque; this process never inspects or can
   read it. Fan-out is Supabase Realtime on the `events` table (Q8), so there is
   nothing to push from here.

   `appendEvent` can run standalone (opens its own tx) or inside a caller's
   transaction (pass `client`) so a state change and its event commit together
   (CRS §4.2). The client supplies `eventId` (CRS §1.1) so its AAD can bind the
   payload to that id before the round-trip. */

import { uuidv7 } from 'uuidv7';
import type { Client } from './db.js';
import { pool, tx } from './db.js';

export type Scope = 'conversation' | 'ambient' | 'system';

export interface SealedBlob {
  v: 1;
  alg: 'A256GCM';
  iv: string;
  ct: string;
}

/* Almost always a SealedBlob the client produced. The one exception
   (CRS/1.0-W §4.2, §4.4) is a server-originated lifecycle event — the
   watchdog's `turn.failed` — whose payload is a cleartext
   `{ code, message, retryable }`: control metadata, never user content. */
export type EventPayload = SealedBlob | Record<string, unknown>;

export interface AppendInput {
  eventId?: string; // client-supplied (CRS §1.1); generated if absent
  scope: Scope;
  conversationId: string | null;
  turnId: string | null;
  kind: string;
  payload: EventPayload;
}

export interface Appended {
  eventId: string;
  sequence: string; // bigint as string
  ts: number;
}

async function appendOn(c: Client, userId: string, input: AppendInput): Promise<Appended> {
  const seq = await c.query<{ value: string }>(
    'UPDATE event_seq SET value = value + 1 WHERE id = 1 RETURNING value',
  );
  const sequence = seq.rows[0]!.value;
  const eventId = input.eventId ?? `evt_${uuidv7()}`;
  const ts = Date.now();
  await c.query(
    `INSERT INTO events
       (event_id, sequence, ts, scope, conversation_id, turn_id, kind, user_id, payload_ct)
     VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
    [
      eventId,
      sequence,
      ts,
      input.scope,
      input.conversationId,
      input.turnId,
      input.kind,
      userId,
      JSON.stringify(input.payload),
    ],
  );
  return { eventId, sequence, ts };
}

/** Append one event for `userId`. Pass `client` to run inside an open tx. */
export function appendEvent(
  userId: string,
  input: AppendInput,
  client?: Client,
): Promise<Appended> {
  return client ? appendOn(client, userId, input) : tx((c) => appendOn(c, userId, input));
}

export interface EventRow {
  event_id: string;
  sequence: string;
  ts: string;
  scope: Scope;
  conversation_id: string | null;
  turn_id: string | null;
  kind: string;
  payload_ct: unknown;
}

/** CRS §8.1 replay — events for this user with sequence > `after`, in order. */
export async function replayAfter(userId: string, after: number, limit = 1000): Promise<EventRow[]> {
  const { rows } = await pool.query<EventRow>(
    `SELECT event_id, sequence, ts, scope, conversation_id, turn_id, kind, payload_ct
       FROM events
      WHERE user_id = $1 AND sequence > $2
      ORDER BY sequence ASC
      LIMIT $3`,
    [userId, after, limit],
  );
  return rows;
}
