/* Conversation Runtime client — CRS/1.0 §8.4.
 *
 * The client is a pure fold: reduce(state, event) -> state. It never infers,
 * synthesises or repairs state the runtime did not send (§8.4.3). That single
 * rule is what makes "reply missing / half-written / overwriting an older one"
 * structurally impossible rather than patched, because every token names the
 * turn it belongs to instead of landing in one global buffer.
 */

export const API = 'http://127.0.0.1:4109';
const WS = 'ws://127.0.0.1:4109/ws';

export type TurnStatus =
  | 'queued' | 'building_context' | 'thinking' | 'streaming' | 'tool_running'
  | 'awaiting_input' | 'completed' | 'failed' | 'cancelled';

export const TERMINAL: TurnStatus[] = ['completed', 'failed', 'cancelled'];

/** `attempt` counts deliberate presses of Retry, 1 being the original ask. It
 *  has no ceiling — a user retry makes a new turn (§5.2.3) and nothing caps how
 *  many — so there is no companion max. It is optional because an older backend
 *  will not send it, and a missing count must render as no count rather than
 *  as one. */
export type TurnError = {
  code: string;
  message: string;
  retryable: boolean;
  attempt?: number;
};

export type ToolCall = {
  name: string;
  status: string;
  arguments?: any;
  summary?: string;
};

/** One entry in an asset's lineage. `asset_id` repeats once a version has been
 *  reverted to, because reverting appends rather than rewrites. */
export type AssetVersion = {
  version: number;
  asset_id: string;
  summary: string | null;
  created_by_turn_id: string | null;
  created_at: number;
  original_name: string;
  bytes: number;
  sha256: string;
  status: string;
};

export type AssetVersions = {
  versions: AssetVersion[];
  head: string;
  /** 'keep' means superseded bytes are retained and Revert will work.
   *  'history' means the record survives but the file may not. */
  retention: 'keep' | 'history';
};

/** Mirrors v2/task_state.py. `partial` and `unknown` are load-bearing: an
 *  action whose tool died mid-flight is not a failure and not a success, and
 *  collapsing it into either is the thing the four-valued model prevents. */
export type TaskAction = {
  id: string;
  sequence: number;
  description: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'partial' | 'unknown' | 'skipped';
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  detail: string | null;
};

export type TaskRecord = {
  id: string;
  goal: string;
  status: 'active' | 'blocked' | 'completed' | 'failed' | 'partial' | 'abandoned';
  constraints: string[];
  created_at: string;
  updated_at: string;
  latest_observation: string | null;
  next_actions: string[];
  known: string[];
  actions: TaskAction[];
};

/** A durable belief and where it came from. `origin` is the axis that keeps a
 *  guess from being read as a fact, which is the whole reason to show any of
 *  this rather than just the text. */
export type Fact = {
  id: string;
  text: string;
  kind: string;
  source: 'user' | 'conversation' | 'file' | 'git' | 'os' | 'tool' | 'model' | 'artifact';
  source_ref: string | null;
  origin: 'stated' | 'observed' | 'inferred';
  confidence: number;
  observed_at: string;
  supersedes: string | null;
  superseded_by: string | null;
  stale: number;
  disputed: number;
};

/* One reveal from the Privacy Mirror: the real value, the placeholder the model
   saw in its place, and what kind of thing it was. */
export type ScrubItem = { original: string; placeholder: string; label: string };

/** One sandbox run. A turn may own several (§ExecutionSession). */
export type Artifact = { asset_id: string; name: string; path: string; bytes: number };

export type Execution = {
  id: string;
  runtime: string;
  status: string;
  summary: string;
  output: string[];
  changes: { created: string[]; modified: string[]; deleted: string[] } | null;
  artifacts: Artifact[];
};

export type PermissionRequest = {
  id: string;
  action: string;
  detail: string;
  options: { id: string; label: string }[];
  auto: boolean;
  resolved: string | null;
};

/* A question the model asked mid-turn. Separate from PermissionRequest on
   purpose — see the reducer case for why they must not be conflated. */
export type UserQuestion = {
  id: string;
  question: string;
  options: { id: string; label: string }[];
  answered: string | null;
};

/* Desktop tools, whose calls are rendered by ComputerBlock's timeline rather
   than as generic tool rows. Named here rather than in the component so the
   list sits next to the types it belongs to — and so adding a tool to the
   backend has exactly one place to be reflected. */
export const COMPUTER_TOOLS = new Set([
  'list_windows', 'control_window', 'read_window', 'click_element',
  'type_into', 'click_at', 'scroll_window', 'press_keys', 'end_control',
  'undo_last', 'record_workflow', 'replay_workflow',
]);

/* One thing the agent did to an application that is not Primnox.

   Kept apart from ToolCall even though every one of these arrives as a tool
   call too, because the two answer different questions. A tool call says what
   the model asked the runtime for; this says what happened on the user's
   desktop. The distinction matters here in a way it does not for a sandbox
   execution: nothing in this list can be rolled back by Primnox, so the list
   is the record of an irreversible thing rather than a progress indicator. */
export type ComputerAction = {
  id: string;
  kind: 'read' | 'capture' | 'click' | 'type' | 'scroll' | 'keys' | 'undo';
  description: string;
  status: 'running' | 'done' | 'failed';
  detail: string;
  at: number;
};

/* A window the user approved, and everything done to it under that approval. */
export type ComputerSession = {
  id: string;
  handle: string;
  label: string;
  process: string;
  scope: 'read' | 'act';
  ttlS: number;
  startedAt: number;
  endedAt: number | null;
  endReason: string | null;
  actions: ComputerAction[];
};

export type Turn = {
  id: string;
  status: TurnStatus;
  userText: string;
  assistantText: string;
  /* The model's reasoning, when the provider sends it — Anthropic's extended
     thinking (opt-in, since it's a real request change) or a reasoning
     model's unprompted `reasoning_content`. Kept apart from `assistantText`
     rather than prefixed onto it: it renders in its own collapsed block, so
     mixing the two here would mean re-splitting them in every component that
     reads this field instead of once, in the reducer, where the runtime
     already told them apart. */
  thinking: string;
  partial: boolean;
  error: TurnError | null;
  plan: string | null;
  toolCalls: ToolCall[];
  executions: Execution[];
  workspaces: { id: string; title: string; kind: string; version: number }[];
  assets: { id: string; name: string; kind: string }[];
  /* Every question this turn asked, in the order it asked them. */
  permissions: PermissionRequest[];
  questions: UserQuestion[];
  /* Windows this turn took control of. Several can be live at once — driving
     a browser and a spreadsheet in one task is ordinary — and each renders
     its own timeline, because interleaving two applications into one list
     would make it impossible to see which one an action happened in. */
  computer: ComputerSession[];
  /* What the Privacy Mirror replaced before this turn left the device, and what
     each placeholder stood for. Emitted as `privacy.scrub` only when something
     was actually scrubbed, and only over this socket — the map itself never
     leaves the machine. Empty means nothing matched, which is a different
     statement from "the mirror was off"; the composer badge carries that one. */
  privacyScrub: ScrubItem[];
  createdAt: number;
};

export const emptyTurn = (id: string, userText: string, createdAt: number): Turn => ({
  id, status: 'queued', userText, assistantText: '', thinking: '', partial: false, error: null,
  plan: null, toolCalls: [], executions: [], workspaces: [], assets: [],
  permissions: [], questions: [], computer: [], privacyScrub: [], createdAt,
});

export type ConversationState = {
  id: string | null;
  turns: Turn[];
  /** Global cursor — one number, not a map of per-conversation cursors (§3.1). */
  cursor: number;
  connected: boolean;
  synced: boolean;
  /** Nothing in this conversation is written to disk (§11.2). */
  incognito: boolean;
  /** An incognito conversation the runtime no longer holds. §11.2.3 requires
      this to be said out loud rather than shown as an empty transcript. */
  gone: boolean;
};

export type CrsEvent = {
  event_id: string;
  sequence: number | null;
  ts: number;
  scope: 'conversation' | 'ambient' | 'system';
  conversation_id: string | null;
  turn_id: string | null;
  kind: string;
  payload: any;
};

export const emptyState = (): ConversationState => ({
  id: null, turns: [], cursor: 0, connected: false, synced: false,
  incognito: false, gone: false,
});

const upsert = (turns: Turn[], id: string, patch: (t: Turn) => Turn): Turn[] => {
  const i = turns.findIndex(t => t.id === id);
  if (i === -1) return turns;
  const next = [...turns];
  next[i] = patch(next[i]);
  return next;
};

/** The fold. Unknown kinds are ignored but still advance the cursor (§3.2) —
 *  which is what makes adding an event kind backward-compatible. */
export function reduce(state: ConversationState, e: CrsEvent): ConversationState {
  const seq = e.sequence;
  const cursor = seq != null && seq > state.cursor ? seq : state.cursor;
  const s = { ...state, cursor };

  if (e.scope !== 'conversation' || !e.turn_id) return s;
  if (state.id && e.conversation_id !== state.id) return s;

  const id = e.turn_id;

  switch (e.kind) {
    case 'turn.created':
      if (s.turns.some(t => t.id === id)) return s;
      return {
        ...s,
        turns: [...s.turns, emptyTurn(id, e.payload?.user_message?.text ?? '', e.ts)],
      };

    case 'turn.status':
      return { ...s, turns: upsert(s.turns, id, t => ({ ...t, status: e.payload.status })) };

    // Append-only. A token event never replaces text already delivered (§3.6.1).
    case 'token':
      return { ...s, turns: upsert(s.turns, id, t => ({ ...t, assistantText: t.assistantText + e.payload.text })) };

    // Same append-only rule, separate field — see Turn.thinking's own comment
    // for why this never touches assistantText.
    case 'thinking':
      return { ...s, turns: upsert(s.turns, id, t => ({ ...t, thinking: t.thinking + e.payload.text })) };

    // Replace rather than append: the runtime emits the whole map once, after
    // the turn's last model call, so a second event is a corrected view of the
    // same turn rather than more reveals to add to it.
    case 'privacy.scrub':
      return {
        ...s,
        turns: upsert(s.turns, id, t => ({ ...t, privacyScrub: e.payload?.mapping ?? [] })),
      };

    case 'turn.completed':
      return {
        ...s,
        turns: upsert(s.turns, id, t => ({
          ...t,
          status: 'completed',
          partial: false,
          // Trust the runtime's final text over the accumulated stream.
          assistantText: e.payload?.assistant_message?.text ?? t.assistantText,
        })),
      };

    // A failure is its own kind, never an assistant message (§10.1).
    case 'turn.failed':
      return {
        ...s,
        turns: upsert(s.turns, id, t => ({
          ...t,
          status: 'failed',
          error: { code: e.payload.code, message: e.payload.message, retryable: !!e.payload.retryable,
                   attempt: typeof e.payload.attempt === 'number' ? e.payload.attempt : undefined },
        })),
      };

    case 'turn.cancelled':
      return {
        ...s,
        turns: upsert(s.turns, id, t => ({
          ...t,
          status: 'cancelled',
          partial: true,
          assistantText: e.payload?.partial_text || t.assistantText,
        })),
      };

    // The model's reasoning is a first-class event, not prose to be scraped
    // out of the token stream.
    case 'plan.proposed':
      return { ...s, turns: upsert(s.turns, id, t => ({ ...t, plan: e.payload.plan })) };

    case 'tool.call':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        toolCalls: [...t.toolCalls, {
          name: e.payload.name, status: 'running', arguments: e.payload.arguments,
        }],
      })) };

    case 'tool.result':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        toolCalls: t.toolCalls.map((c, i) => i === t.toolCalls.length - 1
          ? { ...c, status: e.payload.status || 'done', summary: e.payload.summary }
          : c),
      })) };

    // ── Sandbox. The frontend needs no bespoke execution logic — these fold
    // exactly like tokens do, which is the point of the sandbox speaking the
    // same event protocol as chat.
    case 'sandbox.created':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        executions: [...t.executions, {
          id: e.payload.execution_id, runtime: e.payload.runtime,
          status: 'running', summary: e.payload.summary ?? '', output: [],
          changes: null, artifacts: [],
        }],
      })) };

    case 'sandbox.stdout':
    case 'sandbox.stderr':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        executions: t.executions.map(x => x.id === e.payload.execution_id
          ? { ...x, output: [...x.output, e.payload.line].slice(-500) }
          : x),
      })) };

    case 'sandbox.snapshot':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        executions: t.executions.map(x => x.id === e.payload.execution_id
          ? { ...x, changes: e.payload.changes, artifacts: e.payload.artifacts ?? [] }
          : x),
      })) };

    case 'sandbox.completed':
    case 'sandbox.failed':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        executions: t.executions.map(x => x.id === e.payload.execution_id
          ? { ...x, status: e.kind === 'sandbox.completed' ? 'completed' : 'failed' }
          : x),
      })) };

    case 'workspace.created':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        workspaces: [...t.workspaces, {
          id: e.payload.workspace_id, title: e.payload.title,
          kind: e.payload.kind, version: e.payload.version ?? 1,
        }],
      })) };

    case 'workspace.updated':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        workspaces: t.workspaces.some(w => w.id === e.payload.workspace_id)
          ? t.workspaces.map(w => w.id === e.payload.workspace_id
              ? { ...w, version: e.payload.version } : w)
          : [...t.workspaces, {
              id: e.payload.workspace_id, title: e.payload.workspace_id,
              kind: 'doc', version: e.payload.version,
            }],
      })) };

    case 'asset.ready':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        assets: [...t.assets, {
          id: e.payload.asset_id, name: e.payload.name, kind: e.payload.kind,
        }],
      })) };

    // A turn asks as many times as it uses tools. Keeping one question per
    // turn meant the second grant erased the record of the first — and the
    // record is the entire justification for approving anything silently.
    case 'permission.request':
      return { ...s, turns: upsert(s.turns, id, t => (
        t.permissions.some(p => p.id === e.payload.job_id) ? t : {
          ...t,
          permissions: [...t.permissions, {
            id: e.payload.job_id, action: e.payload.action, detail: e.payload.detail,
            options: e.payload.options ?? [], auto: !!e.payload.auto, resolved: null,
          }],
        }
      )) };

    case 'permission.resolved':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        permissions: t.permissions.map(p =>
          p.id === e.payload.job_id ? { ...p, resolved: e.payload.choice } : p),
      })) };

    /* A question the model asked because it did not know something. Carried in
       its own list, not `permissions`: a permission is a safety decision about
       something about to run, a question is the model admitting a gap. They
       park a turn identically and must never look alike — approving a shell
       command and choosing which file was meant are not the same act. */
    case 'question.asked':
      return { ...s, turns: upsert(s.turns, id, t => (
        t.questions.some(q => q.id === e.payload.job_id) ? t : {
          ...t,
          questions: [...t.questions, {
            id: e.payload.job_id, question: e.payload.question,
            options: e.payload.options ?? [], answered: null,
          }],
        }
      )) };

    /* ── Computer Use. Folded like executions are, with one difference that
       matters: an action arrives TWICE, once as `running` and again when it
       settles, and the second must update the first rather than append. The
       backend emits both on purpose — an action that hangs is exactly the one
       the user needs to see — so appending blindly would show every click
       twice and make a stall look like a repeat. */
    case 'computer.session.started':
      return { ...s, turns: upsert(s.turns, id, t => (
        t.computer.some(c => c.id === e.payload.session_id) ? t : {
          ...t,
          computer: [...t.computer, {
            id: e.payload.session_id, handle: e.payload.handle,
            label: e.payload.label, process: e.payload.process ?? '',
            scope: e.payload.scope, ttlS: e.payload.ttl_s ?? 0,
            startedAt: Date.now(), endedAt: null, endReason: null, actions: [],
          }],
        }
      )) };

    case 'computer.action':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        computer: t.computer.map(c => c.id !== e.payload.session_id ? c : {
          ...c,
          actions: c.actions.some(a => a.id === e.payload.id)
            ? c.actions.map(a => a.id === e.payload.id
                ? { ...a, status: e.payload.status, description: e.payload.description,
                    detail: e.payload.detail ?? '' }
                : a)
            : [...c.actions, {
                id: e.payload.id, kind: e.payload.kind,
                description: e.payload.description, status: e.payload.status,
                detail: e.payload.detail ?? '', at: e.payload.at,
              }],
        }),
      })) };

    case 'computer.session.ended':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        computer: t.computer.map(c => c.id === e.payload.session_id
          ? { ...c, endedAt: Date.now(), endReason: e.payload.reason ?? 'finished' }
          : c),
      })) };

    case 'question.resolved':
      return { ...s, turns: upsert(s.turns, id, t => ({
        ...t,
        questions: t.questions.map(q =>
          q.id === e.payload.job_id ? { ...q, answered: e.payload.choice } : q),
      })) };

    default:
      return s;
  }
}

type Handlers = {
  onEvent: (e: CrsEvent) => void;
  onStatus: (s: { connected: boolean; synced: boolean }) => void;
  getCursor: () => number;
  getConversations: () => string[];
  onResyncRequired: () => void;
};

/** Socket with dedupe (§8.4.1) and out-of-order buffering (§8.4.2). */
export class CrsSocket {
  private ws: WebSocket | null = null;
  private seen = new Set<string>();
  private pending = new Map<number, CrsEvent>();
  private expected = 0;
  private retry = 0;
  private closed = false;

  constructor(private h: Handlers) {}

  connect() {
    this.closed = false;
    const ws = new WebSocket(WS);
    this.ws = ws;

    ws.onopen = () => {
      this.retry = 0;
      this.expected = this.h.getCursor() + 1;
      this.h.onStatus({ connected: true, synced: false });
      // §8.1 — the handshake. One cursor, plus the conversations we have open.
      ws.send(JSON.stringify({
        type: 'hello',
        last_event_seen: this.h.getCursor(),
        conversations: this.h.getConversations(),
        want_ambient: false,
      }));
    };

    ws.onmessage = (raw) => {
      let e: CrsEvent;
      try { e = JSON.parse(raw.data); } catch { return; }

      if (e.kind === 'sync.required') { this.h.onResyncRequired(); return; }

      if (e.kind === 'sync.complete') {
        // §8.2.2 — adopt `head`, not the highest sequence actually received.
        // Events filtered out were for conversations we do not have open;
        // their effects are already durable in the state tables.
        const head = e.payload?.head ?? this.h.getCursor();
        this.expected = head + 1;
        this.flush(head);
        this.h.onStatus({ connected: true, synced: true });
        return;
      }

      if (this.seen.has(e.event_id)) return;      // §8.4.1
      this.seen.add(e.event_id);
      if (this.seen.size > 5000) this.seen = new Set([...this.seen].slice(-2500));

      if (e.sequence == null) { this.h.onEvent(e); return; }   // ambient

      if (e.sequence < this.expected) return;
      if (e.sequence > this.expected) { this.pending.set(e.sequence, e); return; }  // §8.4.2

      this.h.onEvent(e);
      this.expected = e.sequence + 1;
      this.drain();
    };

    ws.onclose = () => {
      this.h.onStatus({ connected: false, synced: false });
      if (this.closed) return;
      // Backoff, capped. Reconnect is normal, not exceptional.
      const delay = Math.min(1000 * 2 ** this.retry++, 10000);
      setTimeout(() => this.connect(), delay);
    };

    ws.onerror = () => ws.close();
  }

  /** Apply anything buffered that is now contiguous. */
  private drain() {
    while (this.pending.has(this.expected)) {
      const e = this.pending.get(this.expected)!;
      this.pending.delete(this.expected);
      this.h.onEvent(e);
      this.expected = e.sequence! + 1;
    }
  }

  /** After sync.complete, release buffered events at or below head. */
  private flush(head: number) {
    [...this.pending.keys()].sort((a, b) => a - b).forEach(seq => {
      if (seq <= head) {
        this.h.onEvent(this.pending.get(seq)!);
        this.pending.delete(seq);
      }
    });
    this.drain();
  }

  resubscribe() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({
        type: 'hello',
        last_event_seen: this.h.getCursor(),
        conversations: this.h.getConversations(),
        want_ambient: false,
      }));
    }
  }

  close() { this.closed = true; this.ws?.close(); }
}

// ── HTTP ────────────────────────────────────────────────────────────────────
const json = async (r: Response) => {
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
};

export const api = {
  listConversations: () => fetch(`${API}/conversations`).then(json),
  createConversation: (title = 'New Chat', incognito = false) =>
    fetch(`${API}/conversations`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, incognito }),
    }).then(json),
  /** Rename, pin, file or archive — all one row, so all one call. */
  updateConversation: (id: string, patch: {
    title?: string; pinned?: boolean; folder_id?: string | null; archived?: boolean;
  }) => fetch(`${API}/conversations/${id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  }).then(json),
  /** Permanent. Archiving is a PATCH; this is the one that does not come back. */
  closeConversation: (id: string) =>
    fetch(`${API}/conversations/${id}`, { method: 'DELETE' }).then(json),

  folders: () => fetch(`${API}/folders`).then(json),
  createFolder: (name: string) =>
    fetch(`${API}/folders`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(json),
  renameFolder: (id: string, name: string) =>
    fetch(`${API}/folders/${id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }).then(json),
  deleteFolder: (id: string) =>
    fetch(`${API}/folders/${id}`, { method: 'DELETE' }).then(json),
  /** §3.3.3 — opening a conversation is a state read, never a replay. */
  history: (id: string) => fetch(`${API}/conversations/${id}/history`).then(json),
  send: (conversationId: string, text: string, assetIds: string[] = []) =>
    fetch(`${API}/conversations/${conversationId}/turns`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, asset_ids: assetIds }),
    }).then(json),
  /** §9.1 — the whole point of the turn having a name. */
  cancel: (turnId: string) => fetch(`${API}/turns/${turnId}`, { method: 'DELETE' }).then(json),
  /** §5.2.3 — creates a new turn referencing the failed one, never reopens it. */
  retry: (turnId: string) => fetch(`${API}/turns/${turnId}/retry`, { method: 'POST' }).then(json),

  health: () => fetch(`${API}/health`).then(json),

  /** Returns as soon as the bytes are hashed; extraction is a job (§2.5). */
  upload: (file: File, conversationId?: string) => {
    const body = new FormData();
    body.append('file', file);
    if (conversationId) body.append('conversation_id', conversationId);
    return fetch(`${API}/assets`, { method: 'POST', body }).then(json);
  },
  asset: (id: string) => fetch(`${API}/assets/${id}`).then(json),
  /** A description of an asset shaped for display. Read-only: there is no
      counterpart that writes, here or on the server. */
  preview: (id: string) => fetch(`${API}/assets/${id}/preview`).then(json),

  workspaces: () => fetch(`${API}/workspaces`).then(json),
  workspace: (id: string, version?: number) =>
    fetch(`${API}/workspaces/${id}${version ? `?version=${version}` : ''}`).then(json),
  /** Undo as a forward move — the reverted version is never destroyed. */
  revert: (id: string, version: number) =>
    fetch(`${API}/workspaces/${id}/revert`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    }).then(json),

  /* Assets get the same two calls documents have had all along. `versions` is
     empty for anything never regenerated, which is most files — the caller
     draws nothing rather than a one-entry history. `retention` comes back with
     it so Revert is only offered when the bytes are actually still there. */
  assetVersions: (id: string): Promise<AssetVersions> =>
    fetch(`${API}/assets/${id}/versions`).then(json),
  revertAsset: (id: string, version: number) =>
    fetch(`${API}/assets/${id}/revert`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ version }),
    }).then(json),

  /* Tasks. The backend has tracked these since v2/task_state.py landed; until
     the routes existed there was no way to ask. */
  tasks: (): Promise<{ tasks: TaskRecord[] }> => fetch(`${API}/tasks`).then(json),
  task: (id: string): Promise<TaskRecord> => fetch(`${API}/tasks/${id}`).then(json),
  resumeTask: (): Promise<{ task: TaskRecord | null }> =>
    fetch(`${API}/tasks/resume`).then(json),
  retargetTask: (id: string, goal: string) =>
    fetch(`${API}/tasks/${id}/retarget`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal }),
    }).then(json),
  /** Omit `status` to let the backend derive an honest one from what ran. */
  finishTask: (id: string, status?: string) =>
    fetch(`${API}/tasks/${id}/finish`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(status ? { status } : {}),
    }).then(json),

  /* Facts, with the provenance that makes a claim checkable. */
  facts: (params: { project?: string; subject?: string; limit?: number } = {}):
    Promise<{ facts: Fact[] }> => {
    const q = new URLSearchParams();
    if (params.project) q.set('project', params.project);
    if (params.subject) q.set('subject', params.subject);
    if (params.limit) q.set('limit', String(params.limit));
    const qs = q.toString();
    return fetch(`${API}/facts${qs ? `?${qs}` : ''}`).then(json);
  },
  searchFacts: (query: string, limit = 8): Promise<{ facts: Fact[] }> =>
    fetch(`${API}/facts/search?q=${encodeURIComponent(query)}&limit=${limit}`).then(json),

  resolvePermission: (requestId: string, choice: string) =>
    fetch(`${API}/permissions/${requestId}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ choice }),
    }).then(json),

  executions: (turnId: string) => fetch(`${API}/turns/${turnId}/executions`).then(json),
  trace: (turnId: string) => fetch(`${API}/turns/${turnId}/trace`).then(json),

  /* Declared tunables. The backend already returns each knob's bounds, type,
     resolved value, where that value came from, and a sentence on what moving
     it costs — so the UI renders the registry rather than restating it. */
  tunables: (): Promise<{ tunables: Tunable[] }> =>
    fetch(`${API}/tunables`).then(json),
  setTunables: (values: Record<string, number>) =>
    fetch(`${API}/tunables`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tunables: values }),
    }).then(json),
  resetTunable: (key?: string) =>
    fetch(`${API}/tunables/reset`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(key ? { key } : {}),
    }).then(json),

  /* What routing currently believes. `chain` is the order this instant — the
     active provider first, then the fallbacks ranked by health — and
     `circuits` is what has actually been observed of each endpoint. Read-only
     apart from the reset, which is what "I just fixed it, try again now"
     means to a breaker that is still counting down. */
  modelHealth: (): Promise<ModelHealth> =>
    fetch(`${API}/models/health`).then(json),

  /* Its own call rather than a field on /models, because the probe is a
  /* The gateway Primnox routes hosted traffic through. Its own call because
     the probe is a network request to a port that is often not listening —
     on a fresh machine "not installed" is the expected answer, not an error,
     and the settings screen has to render it either way. */
  omnirouteStatus: (): Promise<OmniRouteStatus> =>
    fetch(`${API}/models/omniroute`).then(json),
  models: (): Promise<any> => fetch(`${API}/models`).then(json),
  useModel: (name: string, model: string) =>
    fetch(`${API}/models/${encodeURIComponent(name)}/model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    }).then(json),

  /* Probe an endpoint and key WITHOUT saving them. Finding out a credential is
     wrong should not cost a saved profile and a failed conversation. */
  testConnection: (base_url: string, api_key = ''): Promise<ConnectionTest> =>
    fetch(`${API}/models/test`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url, api_key }),
    }).then(json),
  testProfile: (name: string): Promise<ConnectionTest> =>
    fetch(`${API}/models/${encodeURIComponent(name)}/test`, { method: 'POST' }).then(json),

  /* Guides ship with the backend as markdown rather than living on a website:
     everything they describe is state on this machine, and a website cannot
     see any of it. The index carries no bodies — it renders as a menu. */
  /* Mission Control's header. Measured values only — see
     settings/telemetry.py for what is deliberately absent and why. */
  telemetry: (): Promise<Telemetry> => fetch(`${API}/models/telemetry`).then(json),
  capabilities: (): Promise<{ providers: Capability[] }> =>
    fetch(`${API}/models/capabilities`).then(json),
  testAllProfiles: (): Promise<{ results: (ConnectionTest & { profile: string })[] }> =>
    fetch(`${API}/models/test-all`, { method: 'POST' }).then(json),

  guides: (): Promise<{ guides: GuideMeta[] }> => fetch(`${API}/guides`).then(json),
  guide: (slug: string): Promise<Guide> =>
    fetch(`${API}/guides/${encodeURIComponent(slug)}`).then(json),
  resetModelHealth: (key?: string): Promise<ModelHealth> =>
    fetch(`${API}/models/health/reset`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(key ? { key } : {}),
    }).then(json),
};

/** One endpoint's observed history — mirrors health.Circuit.as_dict(). */
export type Circuit = {
  key: string;
  /** OmniRoute's three states. `half_open` means the next call is a probe. */
  state: 'closed' | 'open' | 'half_open';
  open: boolean;
  opens_in_s: number;
  trips: number;
  calls: number;
  failures: number;
  consecutive_failures: number;
  error_rate: number;
  success_rate: number | null;
  latency_ms: number | null;
  /** The penalty score: state, not success rate. See models/health.py. */
  health_score: number;
  /** The last failure was one time does not fix — a dead key, an empty balance. */
  terminal: boolean;
  reason: string;
  last_error: string;
};

/** One candidate in the chain, scored — mirrors routing.Explanation. */
export type RouteStep = {
  provider: string;
  model: string;
  key: string;
  score: number;
  eligible: boolean;
  reasons: string[];
  factors: Record<string, number>;
  origin: 'active' | 'profile';
  local: boolean;
  error?: string;
};

/** The gateway's status — mirrors settings.models.omniroute_status().
 *  `configured` distinguishes "running with providers behind it" from
 *  "running with nothing behind it", which a status code cannot. */
export type OmniRouteStatus = {
  running: boolean;
  host: string;
  model_count: number;
  /** The auto/* routing modes. Picking one keeps the fallback; picking a
   *  named model pins the turn to a single provider and gives that up. */
  channels: string[];
  models?: string[];
  configured: boolean;
  install: string;
  dashboard: string;
};

/** Mission Control's header — mirrors settings.telemetry.snapshot().
 *  No tokens-per-second and no quality score: neither is measured, and a
 *  dashboard number nobody measured is a number nobody should act on. */
export type Telemetry = {
  providers: number;
  local_loaded: number;
  loaded_models: { name: string; vram_gb: number; expires_at: string }[];
  requests_today: number;
  turns: { today: number; completed: number; failed: number; cancelled: number; live: number };
  success_rate: number | null;
  latency_ms: number | null;
  open_circuits: number;
  active: string | null;
  local_active: boolean;
  scrubbing: boolean;
  healthy: boolean;
};

/** What a configured provider can do — from the capability registry the
 *  gateway consults, never from a benchmark Primnox has not run. */
export type Capability = {
  name: string;
  model: string;
  local: boolean;
  tool_calling: 'native' | 'emulated' | 'none';
  vision: 'native' | 'emulated' | 'none';
  json_mode: boolean;
  streaming: boolean;
  context_window: number;
  max_output: number;
  parallel_tool_calls: boolean;
  latency_ms: number | null;
  calls: number;
};

/** A guide's front matter, without its body — mirrors guides.index(). */
export type GuideMeta = {
  slug: string;
  title: string;
  summary: string;
  order: number;
};

export type Guide = GuideMeta & { body: string };

/** One probe of an endpoint — mirrors settings.connections.probe(). */
export type ConnectionTest = {
  ok: boolean;
  /** A failure type from the ported classifier, or 'not_json' / 'no_endpoint'. */
  reason: string;
  error: string;
  latency_ms: number;
  models: string[];
  status: number | null;
  /** Null when the probe tested an endpoint that is not a saved profile. */
  profile?: string | null;
};

export type ModelHealth = {
  circuits: Circuit[];
  chain: RouteStep[];
  attempts_allowed: number;
};

/** One row of `GET /tunables` — mirrors tunables.describe() exactly. */
export type Tunable = {
  key: string;
  value: number;
  default: number;
  min: number;
  max: number;
  /** Python's type name: `int` or `float`. Decides the control's step. */
  type: 'int' | 'float';
  /** Where the live value came from. `environment` outranks a stored value, so
   *  a knob resolved that way cannot be changed from this screen. */
  source: 'default' | 'saved' | 'environment';
  env: string;
  summary: string;
  cost: string;
};

/** Rehydrate turns from a history read (state tables), not from events. */
export function turnsFromHistory(rows: any[]): Turn[] {
  return rows.map(r => ({
    ...emptyTurn(r.turn_id, r.user_message?.text ?? '', r.user_message?.created_at ?? 0),
    status: r.status as TurnStatus,
    assistantText: r.assistant_message?.text ?? '',
    partial: !!r.assistant_message?.partial,
    error: r.error,
    // Durable, unlike the tool rows around them — so a reopened conversation
    // still offers the documents it produced.
    assets: (r.assets ?? []).map((a: any) => ({
      id: a.id, name: a.name, kind: a.kind,
    })),
    // Durable for the same reason, and missed for years because nothing
    // rendered them: a document the model authored is a row in
    // `turn_workspaces`, so it survives a reload and the canvas comes back
    // with the turn that made it.
    workspaces: (r.workspaces ?? []).map((w: any) => ({
      id: w.id, title: w.title, kind: w.kind, version: w.version,
    })),
    // A question this turn is still parked on. The `permission.request` event
    // that announced it is behind our cursor after a reload, so the history
    // read carries it instead — otherwise the turn shows "waiting for you"
    // with no way to answer.
    permissions: r.permission
      ? [{
          id: r.permission.id, action: r.permission.action,
          detail: r.permission.detail, options: r.permission.options ?? [],
          auto: false, resolved: null,
        }]
      : [],
  }));
}
