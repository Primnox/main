/* Client → Render transport (CRS/1.0-W §3.2, §4.3).

   The browser generates all ids (CRS §1.1) and sends only ciphertext + envelope
   facts. Every call carries the Supabase access token; Render derives identity
   from it. `replay` backs CRS §8.1 reconnect. */

import type { Sealed } from '../crypto';
import type { EventRow } from './eventcodec';

export type EventPayload = Sealed | Record<string, unknown>;

export interface StartTurnArgs {
  turnId: string;
  conversationId: string;
  userMessageId: string;
  userMessage: Sealed; // sealed with aadFor.message(userMessageId)
  turnCreatedEventId: string;
  turnCreated: Sealed; // sealed with aadFor.event(turnCreatedEventId, 'turn.created')
  assetIds?: string[];
  originDeviceId?: string;
}

export interface PostEventArgs {
  eventId: string;
  turnId: string;
  conversationId: string;
  kind: string;
  payload: EventPayload;
}

export interface CompleteTurnArgs {
  turnId: string;
  conversationId: string;
  assistantMessageId: string;
  assistantMessage: Sealed; // sealed with aadFor.message(assistantMessageId)
  completionEventId: string;
  completion: Sealed; // sealed with aadFor.event(completionEventId, 'turn.completed')
}

export interface Transport {
  startTurn(a: StartTurnArgs): Promise<{ sequence: number }>;
  postEvent(a: PostEventArgs): Promise<{ sequence: number }>;
  completeTurn(a: CompleteTurnArgs): Promise<{ sequence: number }>;
  cancelTurn(turnId: string): Promise<void>;
  replay(afterSequence: number): Promise<{ events: EventRow[]; head: number }>;
}

export class HttpError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'HttpError';
  }
}

export class HttpTransport implements Transport {
  constructor(
    private readonly base: string,
    private readonly getToken: () => string | Promise<string>,
  ) {}

  private async req<T>(path: string, init: RequestInit): Promise<T> {
    const token = await this.getToken();
    const res = await fetch(`${this.base}${path}`, {
      ...init,
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${token}`,
        ...(init.headers ?? {}),
      },
    });
    if (!res.ok) {
      let message = `HTTP ${res.status}`;
      try {
        const body = (await res.json()) as { error?: string };
        if (body?.error) message = body.error;
      } catch {
        /* non-JSON error body */
      }
      throw new HttpError(res.status, message);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  async startTurn(a: StartTurnArgs): Promise<{ sequence: number }> {
    const r = await this.req<{ sequence: string | number }>(
      `/conversations/${encodeURIComponent(a.conversationId)}/turns`,
      {
        method: 'POST',
        body: JSON.stringify({
          turn_id: a.turnId,
          user_message_id: a.userMessageId,
          user_message: a.userMessage,
          turn_created_event_id: a.turnCreatedEventId,
          turn_created: a.turnCreated,
          asset_ids: a.assetIds ?? [],
          origin_device_id: a.originDeviceId ?? null,
        }),
      },
    );
    return { sequence: Number(r.sequence) };
  }

  async postEvent(a: PostEventArgs): Promise<{ sequence: number }> {
    const r = await this.req<{ sequence: string | number }>(
      `/turns/${encodeURIComponent(a.turnId)}/events`,
      {
        method: 'POST',
        body: JSON.stringify({
          event_id: a.eventId,
          kind: a.kind,
          turn_id: a.turnId,
          conversation_id: a.conversationId,
          payload: a.payload,
        }),
      },
    );
    return { sequence: Number(r.sequence) };
  }

  async completeTurn(a: CompleteTurnArgs): Promise<{ sequence: number }> {
    const r = await this.req<{ sequence: string | number }>(
      `/turns/${encodeURIComponent(a.turnId)}/complete`,
      {
        method: 'POST',
        body: JSON.stringify({
          conversation_id: a.conversationId,
          assistant_message_id: a.assistantMessageId,
          assistant_message: a.assistantMessage,
          completion_event_id: a.completionEventId,
          completion: a.completion,
        }),
      },
    );
    return { sequence: Number(r.sequence) };
  }

  async cancelTurn(turnId: string): Promise<void> {
    await this.req(`/turns/${encodeURIComponent(turnId)}`, { method: 'DELETE' });
  }

  async replay(afterSequence: number): Promise<{ events: EventRow[]; head: number }> {
    const r = await this.req<{ events: EventRow[]; sync: { head: number } }>(
      `/replay?after=${afterSequence}`,
      { method: 'GET' },
    );
    return { events: r.events, head: r.sync.head };
  }
}

/* In-memory transport with a real event log — usable as an offline backend for
   dev and for round-trip tests through decryptEvent + the reducer. `pipeTo`
   links it to a MockRealtimeSource so appended rows fan out like the real
   Supabase Realtime stream. */
export class MockTransport implements Transport {
  private seq = 0;
  readonly rows: EventRow[] = [];
  readonly turns: string[] = [];
  readonly completed: string[] = [];
  readonly cancelled: string[] = [];
  private sink: ((row: EventRow) => void) | null = null;

  pipeTo(sink: { emit: (row: EventRow) => void }): void {
    this.sink = (row) => sink.emit(row);
  }

  private append(row: Omit<EventRow, 'sequence' | 'ts'>): number {
    const sequence = ++this.seq;
    const full: EventRow = { ...row, sequence, ts: Date.now() };
    this.rows.push(full);
    this.sink?.(full);
    return sequence;
  }

  async startTurn(a: StartTurnArgs): Promise<{ sequence: number }> {
    this.turns.push(a.turnId);
    return {
      sequence: this.append({
        event_id: a.turnCreatedEventId,
        scope: 'conversation',
        conversation_id: a.conversationId,
        turn_id: a.turnId,
        kind: 'turn.created',
        payload_ct: a.turnCreated,
      }),
    };
  }

  async postEvent(a: PostEventArgs): Promise<{ sequence: number }> {
    return {
      sequence: this.append({
        event_id: a.eventId,
        scope: 'conversation',
        conversation_id: a.conversationId,
        turn_id: a.turnId,
        kind: a.kind,
        payload_ct: a.payload,
      }),
    };
  }

  async completeTurn(a: CompleteTurnArgs): Promise<{ sequence: number }> {
    this.completed.push(a.turnId);
    return {
      sequence: this.append({
        event_id: a.completionEventId,
        scope: 'conversation',
        conversation_id: a.conversationId,
        turn_id: a.turnId,
        kind: 'turn.completed',
        payload_ct: a.completion,
      }),
    };
  }

  async cancelTurn(turnId: string): Promise<void> {
    this.cancelled.push(turnId);
  }

  async replay(afterSequence: number): Promise<{ events: EventRow[]; head: number }> {
    return {
      events: this.rows.filter((r) => Number(r.sequence) > afterSequence),
      head: this.seq,
    };
  }
}
