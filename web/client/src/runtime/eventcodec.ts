/* Event payload crypto (CRS/1.0-W §4.2, §4.5).

   `sealEventPayload` — the turn driver seals a JSON payload under the DEK,
   bound by AAD to the event's client-generated id + kind.

   `decryptEvent` — the feed turns a raw DB/Realtime row into a decrypted
   `AnyEvent` for the reducer. It enforces the §4.2 carve-out: only
   `turn.failed` / `turn.status` / `sync.complete` may arrive unsealed (a
   server-originated control payload with no key to seal); `token`, `message`,
   `tool.*`, `memory.*`, `workspace.*` MUST be sealed or the event is rejected. */

import { type Sealed, fromUtf8, isSealed, open, seal, utf8 } from '../crypto';
import { aadFor } from '../crypto/aad';
import type { AnyEvent, EventKind, Scope } from './events';

export interface EventRow {
  event_id: string;
  sequence: number | string;
  ts: number | string;
  scope: Scope;
  conversation_id: string | null;
  turn_id: string | null;
  kind: string;
  payload_ct: unknown;
}

const CLEARTEXT_CONTROL: ReadonlySet<string> = new Set([
  'turn.failed',
  'turn.status',
  'sync.complete',
]);

const MUST_SEAL: ReadonlySet<string> = new Set([
  'token',
  'message',
  'tool.call',
  'tool.result',
  'permission.request',
  'permission.resolved',
  'memory.written',
  'workspace.created',
  'workspace.updated',
  'asset.ready',
]);

export async function sealEventPayload(
  dek: CryptoKey,
  eventId: string,
  kind: string,
  payload: unknown,
): Promise<Sealed> {
  return seal(dek, utf8(JSON.stringify(payload)), utf8(aadFor.event(eventId, kind)));
}

export async function decryptEvent(dek: CryptoKey, row: EventRow): Promise<AnyEvent> {
  const env = {
    event_id: row.event_id,
    sequence: Number(row.sequence),
    ts: Number(row.ts),
    scope: row.scope,
    conversation_id: row.conversation_id,
    turn_id: row.turn_id,
    kind: row.kind as EventKind,
  };

  const raw = coercePayload(row.payload_ct);

  if (isSealed(raw)) {
    const pt = await open(dek, raw, utf8(aadFor.event(row.event_id, row.kind)));
    return { ...env, payload: JSON.parse(fromUtf8(pt)) as unknown };
  }

  // unsealed — allowed only for the control carve-out, and never from a client
  if (MUST_SEAL.has(row.kind)) {
    throw new EventCryptoError(
      `event ${row.event_id} (${row.kind}) arrived unsealed — rejected (CRS/1.0-W §4.2)`,
    );
  }
  if (CLEARTEXT_CONTROL.has(row.kind) && raw && typeof raw === 'object') {
    return { ...env, payload: raw as Record<string, unknown> };
  }
  throw new EventCryptoError(
    `event ${row.event_id} (${row.kind}) payload is neither sealed nor an accepted control payload`,
  );
}

export class EventCryptoError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'EventCryptoError';
  }
}

/** Realtime delivers jsonb as a parsed object; some transports hand back a
    string. Normalize to an object/value. */
function coercePayload(x: unknown): unknown {
  if (typeof x === 'string') {
    try {
      return JSON.parse(x);
    } catch {
      return x;
    }
  }
  return x;
}
