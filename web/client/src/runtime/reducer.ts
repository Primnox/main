/* The client reducer — CRS §8.4, CRS/1.0-W §4.5.

   A pure fold: `ingest(state, event) -> state`. It never infers, synthesizes,
   or repairs state the runtime did not send. Two obligations from CRS §8.4:

     - deduplicate by `event_id`
     - buffer events whose `sequence` runs ahead of the cursor and apply them
       only once the gap closes

   This is what makes "reply half-written / missing / overwriting an older one"
   structurally impossible rather than patched: every token names its turn, and
   nothing is applied out of order. */

import {
  AnyEvent,
  RuntimeEvent,
  TurnError,
  TurnStatus,
  TurnUsage,
  isTerminal,
} from './events';

/** A tool call as the fold tracks it. `callId` correlates `tool.result` back to
    its `tool.call`; the rendered shape in lib/crs.ts drops it. */
export interface ToolCallState {
  callId: string;
  name: string;
  status: string;
  arguments?: unknown;
  summary?: string;
}

export interface PermissionState {
  id: string;
  action: string;
  detail: string;
  options: { id: string; label: string }[];
  auto: boolean;
  resolved: string | null;
}

export interface AssetState {
  id: string;
  name: string;
  kind: string;
}

export interface WorkspaceState {
  id: string;
  title: string;
  kind: string;
  version: number;
}

export interface TurnState {
  id: string;
  conversationId: string;
  seqInConversation: number;
  status: TurnStatus;
  userText: string | null;
  assistantText: string; // append-only accumulation of `token` (CRS §3.6.1)
  error: TurnError | null;
  usage: TurnUsage | null;
  cancelled: boolean;
  /** epoch ms of the `turn.created` event; 0 until it lands */
  createdAt: number;
  /* Artifacts of the turn. Each is folded from its own event kind rather than
     inferred — a turn shows the tools it actually reported running, and an
     empty list means the runtime reported none, not that we lost them. */
  toolCalls: ToolCallState[];
  permissions: PermissionState[];
  assets: AssetState[];
  workspaces: WorkspaceState[];
}

export interface ConversationState {
  id: string;
  turns: Record<string, TurnState>;
  turnOrder: string[];
}

export interface RuntimeState {
  conversations: Record<string, ConversationState>;
  cursor: number; // highest sequence applied
  seen: Set<string>; // event_id dedupe (bounded to `seenCap` most-recent)
  buffer: AnyEvent[]; // events ahead of the cursor, kept sorted by sequence
}

const seenCap = 4096;

export function initialState(cursor = 0): RuntimeState {
  return { conversations: {}, cursor, seen: new Set(), buffer: [] };
}

// ── the fold: apply exactly one in-order event ──────────────────────────

function ensureConversation(state: RuntimeState, id: string): ConversationState {
  let c = state.conversations[id];
  if (!c) {
    c = { id, turns: {}, turnOrder: [] };
    state.conversations[id] = c;
  }
  return c;
}

function ensureTurn(conv: ConversationState, id: string, seqInConversation = 0): TurnState {
  let t = conv.turns[id];
  if (!t) {
    t = {
      id,
      conversationId: conv.id,
      seqInConversation,
      status: 'queued',
      userText: null,
      assistantText: '',
      error: null,
      usage: null,
      cancelled: false,
      createdAt: 0,
      toolCalls: [],
      permissions: [],
      assets: [],
      workspaces: [],
    };
    conv.turns[id] = t;
    conv.turnOrder.push(id);
  }
  return t;
}

/** Mutates `state` in place with one already-ordered, already-deduped event. */
function apply(state: RuntimeState, ev: AnyEvent): void {
  if (ev.scope !== 'conversation' || !ev.conversation_id) {
    // system / ambient events carry no conversation state to fold here.
    return;
  }
  const conv = ensureConversation(state, ev.conversation_id);
  const e = ev as RuntimeEvent;

  switch (e.kind) {
    case 'turn.created': {
      const p = e.payload;
      const t = ensureTurn(conv, ev.turn_id ?? p.turn.id, p.turn.seq_in_conversation ?? 0);
      t.userText = p.user_text;
      t.status = 'queued';
      if (!t.createdAt) t.createdAt = ev.ts;
      break;
    }
    case 'turn.status': {
      if (!ev.turn_id) break;
      ensureTurn(conv, ev.turn_id).status = e.payload.status;
      break;
    }
    case 'token': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      t.assistantText += e.payload.text; // append-only, never replace
      if (t.status === 'thinking' || t.status === 'queued' || t.status === 'building_context') {
        t.status = 'streaming';
      }
      break;
    }
    case 'turn.completed': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      if (e.payload.assistant_text) t.assistantText = e.payload.assistant_text;
      t.usage = e.payload.usage;
      t.status = 'completed';
      break;
    }
    case 'turn.failed': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      t.error = e.payload;
      t.status = 'failed';
      break;
    }
    case 'turn.cancelled': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      if (e.payload.partial_text) t.assistantText = e.payload.partial_text;
      t.cancelled = true;
      t.status = 'cancelled';
      break;
    }
    case 'tool.call': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      if (!t.toolCalls.some((c) => c.callId === p.call_id)) {
        t.toolCalls.push({
          callId: p.call_id,
          name: p.name,
          status: 'running',
          arguments: p.arguments,
          summary: p.summary,
        });
      }
      break;
    }
    case 'tool.result': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      const call = t.toolCalls.find((c) => c.callId === p.call_id);
      // A result with no call is not synthesized into one: the fold never
      // invents a call the runtime did not announce (CRS §8.4).
      if (!call) break;
      call.status = p.status ?? (p.error ? 'error' : 'ok');
      if (p.summary !== undefined) call.summary = p.summary;
      else if (p.error) call.summary = p.error;
      break;
    }
    case 'permission.request': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      if (!t.permissions.some((x) => x.id === p.id)) {
        t.permissions.push({
          id: p.id,
          action: p.action,
          detail: p.detail,
          options: p.options,
          auto: p.auto ?? false,
          resolved: null,
        });
      }
      break;
    }
    case 'permission.resolved': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      const req = t.permissions.find((x) => x.id === p.id);
      if (req) req.resolved = p.resolution;
      break;
    }
    case 'asset.ready': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      if (!t.assets.some((a) => a.id === p.id)) {
        t.assets.push({ id: p.id, name: p.name, kind: p.kind ?? '' });
      }
      break;
    }
    case 'workspace.created': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      if (!t.workspaces.some((w) => w.id === p.id)) {
        t.workspaces.push({ id: p.id, title: p.title, kind: p.kind, version: p.version ?? 1 });
      }
      break;
    }
    case 'workspace.updated': {
      if (!ev.turn_id) break;
      const t = ensureTurn(conv, ev.turn_id);
      const p = e.payload;
      const w = t.workspaces.find((x) => x.id === p.id);
      // A turn that only EDITED a document still has to show it, or the edit
      // reads as having happened to nothing.
      if (w) {
        w.version = p.version;
        if (p.title !== undefined) w.title = p.title;
        if (p.kind !== undefined) w.kind = p.kind;
      } else {
        t.workspaces.push({
          id: p.id,
          title: p.title ?? 'Document',
          kind: p.kind ?? '',
          version: p.version,
        });
      }
      break;
    }
    default:
      // Unknown kinds are ignored — the cursor still advances (CRS §3.2).
      // `job.*`, `memory.written`, `model.egress` and `asset.failed` are
      // deliberately here: they are ambient or audit records with no surface
      // on a turn, not state this fold dropped.
      break;
  }
}

function remember(state: RuntimeState, id: string): void {
  state.seen.add(id);
  if (state.seen.size > seenCap) {
    // drop the oldest ~10% — Set iteration is insertion-ordered
    const drop = Math.ceil(seenCap * 0.1);
    let i = 0;
    for (const k of state.seen) {
      state.seen.delete(k);
      if (++i >= drop) break;
    }
  }
}

type ApplyFn = (state: RuntimeState, ev: AnyEvent) => void;
const noop: ApplyFn = () => {};

/** Marks a buffered event that must be acknowledged but never applied (a row
    that failed decryption while a sequence gap was open). */
const SKIP_PAYLOAD = Symbol('crs-w:skip');

/**
 * Ordering machinery shared by `ingest` and `skip`: dedupe by `event_id`, drop
 * anything at/below the cursor, buffer anything ahead of it, and on an in-order
 * event run `applyFn` then drain the buffer. Returns a new top-level state
 * object when something advanced (so React re-renders); nested conversation
 * objects are mutated in place.
 */
function step(prev: RuntimeState, ev: AnyEvent, applyFn: ApplyFn): RuntimeState {
  if (state_has(prev, ev.event_id)) return prev; // dedupe (CRS §8.4.1)
  if (ev.sequence <= prev.cursor) return prev; // already covered — drop

  const state: RuntimeState = {
    conversations: prev.conversations,
    cursor: prev.cursor,
    seen: prev.seen,
    buffer: prev.buffer,
  };

  if (ev.sequence > state.cursor + 1) {
    // gap — hold it (CRS §8.4.2). Buffered events keep an applied? marker so a
    // later drain runs the right function for each.
    if (!state.buffer.some((b) => b.event_id === ev.event_id)) {
      state.buffer = [...state.buffer, ev].sort((a, b) => a.sequence - b.sequence);
    }
    return state;
  }

  applyFn(state, ev);
  remember(state, ev.event_id);
  state.cursor = ev.sequence;

  if (state.buffer.length) {
    const keep: AnyEvent[] = [];
    let drained = false;
    for (const b of state.buffer) {
      if (b.sequence === state.cursor + 1 && !state.seen.has(b.event_id)) {
        if ((b as { payload: unknown }).payload !== SKIP_PAYLOAD) apply(state, b);
        remember(state, b.event_id);
        state.cursor = b.sequence;
        drained = true;
      } else if (b.sequence > state.cursor) {
        keep.push(b);
      }
    }
    if (drained) state.buffer = keep;
  }

  return state;
}

/**
 * Fold one decrypted event into the state.
 */
export function ingest(prev: RuntimeState, ev: AnyEvent): RuntimeState {
  return step(prev, ev, apply);
}

/**
 * Acknowledge an event's `sequence` without applying it — for a row that could
 * not be decrypted or was rejected by the §4.2 carve-out. The cursor must still
 * advance or reconnect would stall forever (CRS §3.2 / §3.1.3 rationale).
 */
export function skip(prev: RuntimeState, envelope: Omit<AnyEvent, 'payload'>): RuntimeState {
  return step(prev, { ...envelope, payload: SKIP_PAYLOAD } as unknown as AnyEvent, noop);
}

function state_has(state: RuntimeState, id: string): boolean {
  return state.seen.has(id) || state.buffer.some((b) => b.event_id === id);
}

/** CRS §8.2 — on `sync.complete` the cursor jumps to `head`, not to the
    highest sequence received. Buffered events at or below head are dropped. */
export function setCursorToHead(prev: RuntimeState, head: number): RuntimeState {
  if (head <= prev.cursor) return prev;
  return {
    ...prev,
    cursor: head,
    buffer: prev.buffer.filter((b) => b.sequence > head),
  };
}

// ── read helpers ───────────────────────────────────────────────────────

export function turnsOf(state: RuntimeState, conversationId: string): TurnState[] {
  const c = state.conversations[conversationId];
  if (!c) return [];
  return c.turnOrder.map((id) => c.turns[id]);
}

export function openTurns(state: RuntimeState): TurnState[] {
  const out: TurnState[] = [];
  for (const c of Object.values(state.conversations)) {
    for (const id of c.turnOrder) {
      const t = c.turns[id];
      if (!isTerminal(t.status)) out.push(t);
    }
  }
  return out;
}
