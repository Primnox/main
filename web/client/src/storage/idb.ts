/* IndexedDB, with an in-memory fallback for SSR / tests / private-mode.

   Two small stores:
     kv     — deviceId, cursor, cached sealed vault + keys blobs, last conversation
     outbox — writes that failed while offline, drained when connectivity returns

   Everything cached here is either non-sensitive (deviceId, cursor) or already
   ciphertext (the sealed blobs). Plaintext keys are never persisted. */

const DB_NAME = 'primnox-web';
const DB_VERSION = 1;

export interface OutboxItem {
  id: string;
  kind: 'postEvent' | 'completeTurn' | 'cancelTurn';
  args: unknown;
  ts: number;
  attempts: number;
}

interface Backend {
  kvGet<T>(key: string): Promise<T | undefined>;
  kvSet(key: string, value: unknown): Promise<void>;
  kvDel(key: string): Promise<void>;
  outboxAdd(item: OutboxItem): Promise<void>;
  outboxAll(): Promise<OutboxItem[]>;
  outboxDel(id: string): Promise<void>;
}

class MemoryBackend implements Backend {
  private kv = new Map<string, unknown>();
  private outbox = new Map<string, OutboxItem>();
  async kvGet<T>(key: string) {
    return this.kv.get(key) as T | undefined;
  }
  async kvSet(key: string, value: unknown) {
    this.kv.set(key, value);
  }
  async kvDel(key: string) {
    this.kv.delete(key);
  }
  async outboxAdd(item: OutboxItem) {
    this.outbox.set(item.id, item);
  }
  async outboxAll() {
    return [...this.outbox.values()].sort((a, b) => a.ts - b.ts);
  }
  async outboxDel(id: string) {
    this.outbox.delete(id);
  }
}

class IdbBackend implements Backend {
  private dbp: Promise<IDBDatabase>;
  constructor() {
    this.dbp = new Promise((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = () => {
        const db = req.result;
        if (!db.objectStoreNames.contains('kv')) db.createObjectStore('kv');
        if (!db.objectStoreNames.contains('outbox')) db.createObjectStore('outbox', { keyPath: 'id' });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }
  private async run<T>(
    store: string,
    mode: IDBTransactionMode,
    fn: (s: IDBObjectStore) => IDBRequest,
  ): Promise<T> {
    const db = await this.dbp;
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      req.onsuccess = () => resolve(req.result as T);
      req.onerror = () => reject(req.error);
    });
  }
  kvGet<T>(key: string) {
    return this.run<T | undefined>('kv', 'readonly', (s) => s.get(key));
  }
  async kvSet(key: string, value: unknown) {
    await this.run('kv', 'readwrite', (s) => s.put(value, key));
  }
  async kvDel(key: string) {
    await this.run('kv', 'readwrite', (s) => s.delete(key));
  }
  async outboxAdd(item: OutboxItem) {
    await this.run('outbox', 'readwrite', (s) => s.put(item));
  }
  async outboxAll() {
    const all = await this.run<OutboxItem[]>('outbox', 'readonly', (s) => s.getAll());
    return (all ?? []).sort((a, b) => a.ts - b.ts);
  }
  async outboxDel(id: string) {
    await this.run('outbox', 'readwrite', (s) => s.delete(id));
  }
}

function pickBackend(): Backend {
  try {
    if (typeof indexedDB !== 'undefined') return new IdbBackend();
  } catch {
    /* private mode can throw on open */
  }
  return new MemoryBackend();
}

export class LocalStore {
  private readonly be: Backend;
  constructor(backend?: Backend) {
    this.be = backend ?? pickBackend();
  }

  get<T>(key: string): Promise<T | undefined> {
    return this.be.kvGet<T>(key);
  }
  set(key: string, value: unknown): Promise<void> {
    return this.be.kvSet(key, value);
  }
  del(key: string): Promise<void> {
    return this.be.kvDel(key);
  }

  enqueue(item: Omit<OutboxItem, 'ts' | 'attempts'>): Promise<void> {
    return this.be.outboxAdd({ ...item, ts: Date.now(), attempts: 0 });
  }
  /** Write a full item as-is (used to bump `attempts` on a retry). */
  putOutbox(item: OutboxItem): Promise<void> {
    return this.be.outboxAdd(item);
  }
  outbox(): Promise<OutboxItem[]> {
    return this.be.outboxAll();
  }
  dequeue(id: string): Promise<void> {
    return this.be.outboxDel(id);
  }
}
