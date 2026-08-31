/* GitHub sync queue (CRS/1.0-W §W2).

   After a turn reaches a terminal state, a debounced per-user job mirrors the
   new `events` rows into the user's repo as append-only NDJSON per conversation
   (envelopes cleartext, payloads still ciphertext) plus a cleartext manifest.
   All files land in one commit.

   It is idempotent (keyed on `sync_state.last_synced_seq`) and MUST NEVER throw
   upward — a GitHub outage cannot fail a turn. */

import type { GitHubClient, RepoFile } from './github.js';

export interface PendingRow {
  event_id: string;
  sequence: string;
  ts: string;
  scope: string;
  conversation_id: string | null;
  turn_id: string | null;
  kind: string;
  payload_ct: unknown;
}

export interface SyncDeps {
  debounceMs: number;
  /** an authed client for the user's repo, or null if GitHub is not connected */
  githubFor(userId: string): Promise<GitHubClient | null>;
  /** current `sync_state.last_synced_seq` for the user */
  readLastSynced(userId: string): Promise<number>;
  /** events for the user with sequence > afterSeq, ascending, plus the head */
  loadPending(userId: string, afterSeq: number): Promise<{ rows: PendingRow[]; head: number }>;
  /** persist progress */
  writeState(userId: string, head: number, repoHead: string): Promise<void>;
  log?: (msg: string, extra?: unknown) => void;
}

export class SyncQueue {
  private readonly timers = new Map<string, ReturnType<typeof setTimeout>>();
  private readonly running = new Set<string>();
  private readonly redo = new Set<string>();

  constructor(private readonly deps: SyncDeps) {}

  /** Called when a turn completes. Coalesces bursts into one run. */
  schedule(userId: string): void {
    const existing = this.timers.get(userId);
    if (existing) clearTimeout(existing);
    const t = setTimeout(() => {
      this.timers.delete(userId);
      void this.run(userId);
    }, this.deps.debounceMs);
    if (typeof t.unref === 'function') t.unref();
    this.timers.set(userId, t);
  }

  /** Run any pending timers now and wait for in-flight work — for shutdown. */
  async flush(userId: string): Promise<void> {
    const t = this.timers.get(userId);
    if (t) {
      clearTimeout(t);
      this.timers.delete(userId);
    }
    await this.run(userId);
  }

  private async run(userId: string): Promise<void> {
    if (this.running.has(userId)) {
      this.redo.add(userId);
      return;
    }
    this.running.add(userId);
    try {
      await this.syncOnce(userId);
    } catch (e) {
      this.log(`sync failed for ${userId}`, e); // §W2 — swallow, never propagate
    } finally {
      this.running.delete(userId);
      if (this.redo.delete(userId)) this.schedule(userId);
    }
  }

  private async syncOnce(userId: string): Promise<void> {
    const gh = await this.deps.githubFor(userId);
    if (!gh) return; // GitHub not connected — nothing to do

    const lastSynced = await this.deps.readLastSynced(userId);
    const { rows, head } = await this.deps.loadPending(userId, lastSynced);
    if (rows.length === 0) return;

    const byConv = new Map<string, PendingRow[]>();
    for (const row of rows) {
      const key = row.conversation_id ?? '_system';
      (byConv.get(key) ?? byConv.set(key, []).get(key)!).push(row);
    }

    const files: RepoFile[] = [];
    for (const [convId, evs] of byConv) {
      const path = `conversations/${convId}/events.ndjson`;
      const existing = (await gh.readFile(path)) ?? '';
      const appended =
        existing + evs.map((e) => JSON.stringify(e)).join('\n') + '\n';
      files.push({ path, content: appended });
    }

    files.push({
      path: 'manifest.json',
      content: JSON.stringify(
        {
          format: 'primnox-web/events-ndjson/v1',
          last_synced_seq: head,
          updated_at: new Date().toISOString(),
          note: 'Encrypted Primnox data. Event payloads are AES-256-GCM ciphertext.',
        },
        null,
        2,
      ),
    });

    const { commitSha } = await gh.putFiles(
      files,
      `sync: events ${lastSynced + 1}..${head} (${rows.length})`,
    );
    await this.deps.writeState(userId, head, commitSha);
    this.log(`synced ${rows.length} events for ${userId} -> ${commitSha.slice(0, 8)}`);
  }

  private log(msg: string, extra?: unknown): void {
    (this.deps.log ?? ((m, e) => console.info(`[sync] ${m}`, e ?? '')))(msg, extra);
  }
}
