/* PrimnoxClient — the single object the UI holds.

   Composes auth, the vault, provider keys, the event feed, the runtime store,
   the model router, and the turn driver into one API. Everything below the
   surface follows CRS/1.0-W: the browser owns all content, the server sees only
   ciphertext + envelopes. */

import {
  addRecovery,
  changePassphrase,
  createVault,
  unlockVault,
  unlockWithMnemonic,
  type Sealed,
  type VaultBlob,
} from './crypto';
import { newId } from './ids';
import { ModelRouter, type ProviderId } from './model';
import { EventFeed } from './runtime/realtime';
import type { RealtimeSource } from './runtime/realtime';
import { RuntimeStore } from './runtime/store';
import { runTurn, type LocalTurnEvent, type RunTurnResult } from './runtime/turn';
import type { Transport } from './runtime/transport';
import { OfflineAwareTransport } from './runtime/offline';
import type { LocalStore } from './storage/idb';
import type { SessionStore } from './auth/session';
import { ProviderKeyStore, type ProviderEntry } from './vault/keys';
import { fetchVault, putVault, type VaultRemoteDeps } from './vault/remote';
import type { TurnRecord } from './context/bundle';

export type VaultState = 'no-vault' | 'locked' | 'unlocked';

export interface PrimnoxSnapshot {
  vault: VaultState;
  /** true between createVault() and acknowledgeRecovery() — the mnemonic must
      be shown and confirmed once before the app proceeds (resolved Q9) */
  pendingRecovery: boolean;
  online: boolean;
  deviceId: string;
}

export interface PrimnoxConfig {
  renderApiBase: string;
  githubAppSlug: string;
  systemPrompt: string;
}

export interface PrimnoxDeps {
  config: PrimnoxConfig;
  auth: SessionStore;
  transport: Transport;
  realtime: RealtimeSource;
  store: LocalStore;
}

const DEFAULT_SYSTEM_PROMPT =
  'You are Primnox, a personal AI environment running on the user\'s own machine. ' +
  'Be plain, specific, and non-euphemistic. When something fails, say what happened.';

export class PrimnoxClient {
  readonly runtime = new RuntimeStore();

  private readonly deps: PrimnoxDeps;
  private readonly router = new ModelRouter();
  private readonly offline: OfflineAwareTransport | null;

  private dek: CryptoKey | null = null;
  private vaultBlob: VaultBlob | null = null;
  private keysCt: Sealed | null = null;
  private keys = new ProviderKeyStore();
  private feed: EventFeed | null = null;
  private deviceId = '';

  private readonly aborts = new Map<string, AbortController>();
  private readonly listeners = new Set<() => void>();
  private snapshot: PrimnoxSnapshot = {
    vault: 'no-vault',
    pendingRecovery: false,
    online: true,
    deviceId: '',
  };

  constructor(deps: PrimnoxDeps) {
    this.deps = deps;
    this.offline = deps.transport instanceof OfflineAwareTransport ? deps.transport : null;
  }

  get auth(): SessionStore {
    return this.deps.auth;
  }
  get githubAppSlug(): string {
    return this.deps.config.githubAppSlug;
  }
  get renderApiBase(): string {
    return this.deps.config.renderApiBase;
  }

  // ── observable ───────────────────────────────────────────────────────

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };
  getSnapshot = (): PrimnoxSnapshot => this.snapshot;

  private emit(patch: Partial<PrimnoxSnapshot>): void {
    this.snapshot = { ...this.snapshot, ...patch };
    for (const l of this.listeners) l();
  }

  // ── lifecycle ────────────────────────────────────────────────────────

  async init(): Promise<void> {
    this.deviceId =
      (await this.deps.store.get<string>('deviceId')) ??
      (typeof crypto.randomUUID === 'function' ? `dev_${crypto.randomUUID()}` : newId('job'));
    await this.deps.store.set('deviceId', this.deviceId);
    this.emit({ deviceId: this.deviceId, online: typeof navigator === 'undefined' || navigator.onLine });

    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => this.onOnline());
      window.addEventListener('offline', () => this.emit({ online: false }));
    }

    await this.deps.auth.init();
    if (this.deps.auth.getSnapshot().status === 'authenticated') await this.refreshVault();
  }

  private async onOnline(): Promise<void> {
    this.emit({ online: true });
    await this.offline?.drain().catch(() => undefined);
  }

  private vaultRemote(): VaultRemoteDeps {
    return {
      base: this.deps.config.renderApiBase,
      accessToken: this.deps.auth.accessToken,
      store: this.deps.store,
    };
  }

  /** Load the sealed vault + keys blobs after sign-in. */
  async refreshVault(): Promise<void> {
    const { blob, keysCt } = await fetchVault(this.vaultRemote());
    this.vaultBlob = blob;
    this.keysCt = keysCt;
    this.emit({ vault: blob ? 'locked' : 'no-vault' });
  }

  // ── vault ────────────────────────────────────────────────────────────

  /** First run. Forces recovery-mnemonic capture (resolved Q9). */
  async createVault(passphrase: string): Promise<{ mnemonic: string }> {
    const created = await createVault(passphrase);
    const withRecovery = await addRecovery(passphrase, created.blob);
    this.vaultBlob = withRecovery.blob;
    this.dek = created.dek;
    this.keys = new ProviderKeyStore();
    this.keysCt = await this.keys.seal(this.dek);
    await putVault(this.vaultRemote(), this.vaultBlob, this.keysCt);
    await this.startFeed();
    this.emit({ vault: 'unlocked', pendingRecovery: true });
    return { mnemonic: withRecovery.mnemonic };
  }

  /** The user confirmed they saved the recovery phrase. */
  acknowledgeRecovery(): void {
    this.emit({ pendingRecovery: false });
  }

  async unlock(passphrase: string): Promise<void> {
    if (!this.vaultBlob) throw new Error('no vault to unlock');
    await this.afterUnlock(await unlockVault(passphrase, this.vaultBlob));
  }

  async unlockWithMnemonic(mnemonic: string): Promise<void> {
    if (!this.vaultBlob) throw new Error('no vault to unlock');
    await this.afterUnlock(await unlockWithMnemonic(mnemonic, this.vaultBlob));
  }

  async changePassphrase(oldPass: string, newPass: string): Promise<void> {
    if (!this.vaultBlob) throw new Error('no vault');
    this.vaultBlob = await changePassphrase(oldPass, newPass, this.vaultBlob);
    await putVault(this.vaultRemote(), this.vaultBlob, this.keysCt);
  }

  lock(): void {
    this.dek = null;
    this.feed?.stop();
    this.feed = null;
    this.keys = new ProviderKeyStore();
    this.emit({ vault: this.vaultBlob ? 'locked' : 'no-vault' });
  }

  private async afterUnlock(dek: CryptoKey): Promise<void> {
    this.dek = dek;
    this.keys = this.keysCt
      ? await ProviderKeyStore.unseal(dek, this.keysCt).catch(() => new ProviderKeyStore())
      : new ProviderKeyStore();
    await this.startFeed();
    this.emit({ vault: 'unlocked' });
  }

  private async startFeed(): Promise<void> {
    if (!this.dek || this.feed) return;
    const from = (await this.deps.store.get<number>('cursor')) ?? 0;
    this.feed = new EventFeed({
      store: this.runtime,
      transport: this.deps.transport,
      realtime: this.deps.realtime,
      dek: this.dek,
      onDecryptError: (row, err) =>
        console.warn(`[feed] dropped event ${row.event_id} (${row.kind}):`, err),
    });
    this.runtime.subscribe(() => {
      void this.deps.store.set('cursor', this.runtime.getState().cursor);
    });
    await this.feed.start(from);
  }

  // ── provider keys ────────────────────────────────────────────────────

  listProviderKeys(): ProviderEntry[] {
    return this.keys.list();
  }

  async setProviderKey(entry: Omit<ProviderEntry, 'addedAt'>): Promise<void> {
    this.requireDek();
    this.keys.set(entry);
    await this.persistKeys();
  }

  async removeProviderKey(provider: ProviderId): Promise<void> {
    this.requireDek();
    this.keys.remove(provider);
    await this.persistKeys();
  }

  private async persistKeys(): Promise<void> {
    this.keysCt = await this.keys.seal(this.requireDek());
    if (this.vaultBlob) await putVault(this.vaultRemote(), this.vaultBlob, this.keysCt);
  }

  private defaultProvider(): ProviderId | null {
    const order: ProviderId[] = ['openrouter', 'anthropic', 'gemini', 'groq'];
    return order.find((p) => this.keys.has(p)) ?? null;
  }

  // ── chat ─────────────────────────────────────────────────────────────

  async send(
    conversationId: string,
    userText: string,
    opts: {
      provider?: ProviderId;
      history?: TurnRecord[];
      onEvent?: (e: LocalTurnEvent) => void;
    } = {},
  ): Promise<RunTurnResult> {
    const dek = this.requireDek();
    const provider = opts.provider ?? this.defaultProvider();
    if (!provider) {
      return { ok: false, turnId: '', error: { code: 'provider_auth', message: 'add a model key first', retryable: false } };
    }
    const profile = this.keys.profile(provider)!;

    const ac = new AbortController();
    const result = await runTurn(
      {
        router: this.router,
        transport: this.deps.transport,
        dek,
        profile,
        originDeviceId: this.deviceId,
        onEvent: opts.onEvent,
      },
      {
        conversationId,
        userText,
        context: { systemPrompt: this.deps.config.systemPrompt || DEFAULT_SYSTEM_PROMPT, history: opts.history ?? [] },
        signal: ac.signal,
        onStart: (turnId) => this.aborts.set(turnId, ac),
      },
    );
    if (result.turnId) this.aborts.delete(result.turnId);
    // let the feed fold the turn's events into the runtime store before we return
    await this.feed?.whenIdle().catch(() => undefined);
    return result;
  }

  cancel(turnId: string): void {
    this.aborts.get(turnId)?.abort();
  }

  newConversationId(): string {
    return newId('conv');
  }

  private requireDek(): CryptoKey {
    if (!this.dek) throw new Error('vault is locked');
    return this.dek;
  }
}
