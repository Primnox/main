/* Provider key vault (CRS/1.0-W §D3, §5).

   BYO model keys are vault data like anything else: sealed under the DEK,
   written to `vault/keys.enc` in the user's repo and mirrored to Supabase, and
   decrypted in the browser per session — held in memory, never persisted in
   the clear. Phase 1 keeps one active entry per provider. */

import { type Sealed, fromUtf8, open, seal, utf8 } from '../crypto';
import { aadFor } from '../crypto/aad';
import type { ModelProfile, ProviderId } from '../model';

export interface ProviderEntry {
  provider: ProviderId;
  model: string;
  apiKey: string;
  baseUrl?: string;
  label?: string;
  addedAt: number;
}

interface KeyBundle {
  v: 1;
  entries: Partial<Record<ProviderId, ProviderEntry>>;
}

export class ProviderKeyStore {
  private bundle: KeyBundle;

  constructor(bundle?: KeyBundle) {
    this.bundle = bundle ?? { v: 1, entries: {} };
  }

  static async unseal(dek: CryptoKey, sealed: Sealed): Promise<ProviderKeyStore> {
    const pt = await open(dek, sealed, utf8(aadFor.providerKeys()));
    const bundle = JSON.parse(fromUtf8(pt)) as KeyBundle;
    return new ProviderKeyStore(bundle);
  }

  seal(dek: CryptoKey): Promise<Sealed> {
    return seal(dek, utf8(JSON.stringify(this.bundle)), utf8(aadFor.providerKeys()));
  }

  set(entry: Omit<ProviderEntry, 'addedAt'>): void {
    this.bundle.entries[entry.provider] = { ...entry, addedAt: Date.now() };
  }

  remove(provider: ProviderId): void {
    delete this.bundle.entries[provider];
  }

  get(provider: ProviderId): ProviderEntry | undefined {
    return this.bundle.entries[provider];
  }

  has(provider: ProviderId): boolean {
    return this.bundle.entries[provider] !== undefined;
  }

  list(): ProviderEntry[] {
    return Object.values(this.bundle.entries).filter((e): e is ProviderEntry => !!e);
  }

  /** A ModelProfile the turn driver can use, or undefined if that provider has no key. */
  profile(provider: ProviderId): ModelProfile | undefined {
    const e = this.get(provider);
    if (!e) return undefined;
    return {
      provider: e.provider,
      model: e.model,
      apiKey: e.apiKey,
      ...(e.baseUrl ? { baseUrl: e.baseUrl } : {}),
    };
  }
}
