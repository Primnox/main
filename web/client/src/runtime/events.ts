/* CRS/1.0-W event model.

   The envelope is exactly CRS §3.2 and stays cleartext (§4.2). Payloads
   reaching the reducer are ALREADY DECRYPTED — decryption is a layer above
   the fold (§4.5). `privacy.scrub` is retired for web; `model.egress`
   (counts, no content) replaces it as the egress audit record (§4.6). */

export type Scope = 'conversation' | 'ambient' | 'system';

export type EventKind =
  | 'turn.created'
  | 'turn.status'
  | 'turn.completed'
  | 'turn.failed'
  | 'turn.cancelled'
  | 'token'
  | 'job.started'
  | 'job.progress'
  | 'job.completed'
  | 'tool.call'
  | 'tool.result'
  | 'permission.request'
  | 'permission.resolved'
  | 'asset.ready'
  | 'asset.failed'
  | 'workspace.created'
  | 'workspace.updated'
  | 'memory.written'
  | 'model.egress'
  | 'sync.complete';

export type TurnStatus =
  | 'queued'
  | 'building_context'
  | 'thinking'
  | 'streaming'
  | 'tool_running'
  | 'awaiting_input'
  | 'completed'
  | 'failed'
  | 'cancelled';

export const TERMINAL: readonly TurnStatus[] = ['completed', 'failed', 'cancelled'] as const;
export const isTerminal = (s: TurnStatus): boolean => TERMINAL.includes(s);

export interface Envelope {
  event_id: string;
  sequence: number;
  ts: number;
  scope: Scope;
  conversation_id: string | null;
  turn_id: string | null;
  kind: EventKind;
}

// ── payloads (decrypted) ────────────────────────────────────────────────

export interface TurnError {
  code: string;
  message: string;
  retryable: boolean;
  attempt?: number;
}

export interface TurnUsage {
  input_tokens: number;
  output_tokens: number;
}

export interface KnownPayloads {
  'turn.created': { turn: { id: string; seq_in_conversation?: number }; user_text: string };
  'turn.status': { status: TurnStatus; detail?: string };
  'turn.completed': { assistant_text: string; usage: TurnUsage };
  'turn.failed': TurnError;
  'turn.cancelled': { partial_text: string };
  token: { text: string };
  'model.egress': { provider: string; model: string; input_tokens: number };
  'sync.complete': { head: number };
}

type PayloadFor<K extends EventKind> = K extends keyof KnownPayloads
  ? KnownPayloads[K]
  : Record<string, unknown>;

type EventOfKind<K extends EventKind> = Envelope & { kind: K; payload: PayloadFor<K> };

/** Discriminated union over `kind` — `switch (e.kind)` narrows `e.payload`. */
export type RuntimeEvent = { [K in EventKind]: EventOfKind<K> }[EventKind];

export type AnyEvent = Envelope & { payload: unknown };
