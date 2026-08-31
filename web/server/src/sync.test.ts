import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { GitHubClient, RepoFile } from './github.js';
import { SyncQueue, type PendingRow, type SyncDeps } from './sync.js';

class MockGitHub implements GitHubClient {
  files = new Map<string, string>();
  commits: Array<{ files: RepoFile[]; message: string }> = [];
  failNext = false;
  repoFullName() {
    return 'cyanexani/primnox-chat';
  }
  async readFile(path: string) {
    return this.files.get(path) ?? null;
  }
  async putFiles(files: RepoFile[], message: string) {
    if (this.failNext) {
      this.failNext = false;
      throw new Error('GitHub 503');
    }
    for (const f of files) this.files.set(f.path, f.content);
    this.commits.push({ files, message });
    return { commitSha: `sha_${this.commits.length}` };
  }
}

const row = (seq: number, conv: string, kind = 'token'): PendingRow => ({
  event_id: `evt_${seq}`,
  sequence: String(seq),
  ts: String(1_700_000_000_000 + seq),
  scope: 'conversation',
  conversation_id: conv,
  turn_id: 'turn_1',
  kind,
  payload_ct: { v: 1, alg: 'A256GCM', iv: 'i', ct: `c${seq}` },
});

function makeQueue(over: Partial<SyncDeps> = {}) {
  const gh = new MockGitHub();
  let lastSynced = 0;
  const pending: PendingRow[] = [];
  const state: { head: number; repoHead: string }[] = [];

  const q = new SyncQueue({
    debounceMs: 50,
    githubFor: async () => gh,
    readLastSynced: async () => lastSynced,
    loadPending: async (_u, after) => {
      const rows = pending.filter((r) => Number(r.sequence) > after);
      return { rows, head: rows.length ? Number(rows[rows.length - 1]!.sequence) : after };
    },
    writeState: async (_u, head, repoHead) => {
      lastSynced = head;
      state.push({ head, repoHead });
    },
    log: () => {},
    ...over,
  });

  return { q, gh, pending, state, setLastSynced: (n: number) => (lastSynced = n) };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('SyncQueue', () => {
  it('debounces a burst of schedules into one commit', async () => {
    const { q, gh, pending } = makeQueue();
    pending.push(row(1, 'conv_a'), row(2, 'conv_a'));

    q.schedule('u1');
    q.schedule('u1');
    q.schedule('u1');

    await vi.advanceTimersByTimeAsync(60);
    expect(gh.commits).toHaveLength(1);
    expect(gh.commits[0]!.message).toContain('events 1..2');
  });

  it('writes append-only NDJSON per conversation plus a manifest', async () => {
    const { q, gh, pending } = makeQueue();
    pending.push(row(1, 'conv_a'), row(2, 'conv_b'), row(3, 'conv_a'));

    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60);

    const a = gh.files.get('conversations/conv_a/events.ndjson')!;
    expect(a.trim().split('\n')).toHaveLength(2);
    expect(JSON.parse(a.trim().split('\n')[0]!).event_id).toBe('evt_1');
    expect(gh.files.get('conversations/conv_b/events.ndjson')!.trim().split('\n')).toHaveLength(1);
    expect(JSON.parse(gh.files.get('manifest.json')!).last_synced_seq).toBe(3);
  });

  it('appends to an existing conversation file on the next sync', async () => {
    const { q, gh, pending, setLastSynced } = makeQueue();
    gh.files.set('conversations/conv_a/events.ndjson', JSON.stringify(row(1, 'conv_a')) + '\n');
    setLastSynced(1);
    pending.push(row(1, 'conv_a'), row(2, 'conv_a'));

    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60);

    expect(gh.files.get('conversations/conv_a/events.ndjson')!.trim().split('\n')).toHaveLength(2);
  });

  it('a GitHub failure never throws upward and leaves state unadvanced', async () => {
    const { q, gh, pending, state } = makeQueue();
    gh.failNext = true;
    pending.push(row(1, 'conv_a'));

    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60); // must not reject
    expect(state).toHaveLength(0); // did not record progress

    // next run succeeds and catches up
    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60);
    expect(gh.commits).toHaveLength(1);
    expect(state[0]!.head).toBe(1);
  });

  it('is a no-op when GitHub is not connected', async () => {
    const { q, pending, state } = makeQueue({ githubFor: async () => null });
    pending.push(row(1, 'conv_a'));
    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60);
    expect(state).toHaveLength(0);
  });

  it('is a no-op when there is nothing new', async () => {
    const { q, gh } = makeQueue();
    q.schedule('u1');
    await vi.advanceTimersByTimeAsync(60);
    expect(gh.commits).toHaveLength(0);
  });
});
