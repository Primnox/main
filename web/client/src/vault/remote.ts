/* Fetch / persist the sealed vault blob + sealed provider-keys blob
   (CRS/1.0-W §5, §W1, §D3).

   Everything here is ciphertext or non-secret metadata; storing it on
   Render/Supabase leaks nothing. It is also cached in the LocalStore so a
   returning device can prompt for the passphrase before the network is up. */

import type { Sealed, VaultBlob } from '../crypto';
import type { LocalStore } from '../storage/idb';

const VAULT_CACHE = 'vaultBlob';
const KEYS_CACHE = 'keysBlob';

interface WireVault {
  kdf: VaultBlob['kdf'];
  wrapped_dek: VaultBlob['wrappedDek'];
  wrapped_dek_recovery?: VaultBlob['wrappedDekRecovery'] | null;
  recovery_salt_b64?: string | null;
  keys_ct?: Sealed | null;
  key_version: number;
}

const toBlob = (w: WireVault): VaultBlob => ({
  v: 1,
  kdf: w.kdf,
  wrappedDek: w.wrapped_dek,
  ...(w.wrapped_dek_recovery ? { wrappedDekRecovery: w.wrapped_dek_recovery } : {}),
  ...(w.recovery_salt_b64 ? { recoverySaltB64: w.recovery_salt_b64 } : {}),
  keyVersion: w.key_version,
});

const toWire = (b: VaultBlob, keysCt: Sealed | null): WireVault => ({
  kdf: b.kdf,
  wrapped_dek: b.wrappedDek,
  wrapped_dek_recovery: b.wrappedDekRecovery ?? null,
  recovery_salt_b64: b.recoverySaltB64 ?? null,
  keys_ct: keysCt,
  key_version: b.keyVersion,
});

export interface VaultRemoteDeps {
  base: string;
  accessToken: () => Promise<string>;
  store: LocalStore;
}

export interface RemoteVault {
  blob: VaultBlob | null;
  keysCt: Sealed | null;
}

export async function fetchVault(deps: VaultRemoteDeps): Promise<RemoteVault> {
  try {
    const res = await fetch(`${deps.base}/vault`, {
      headers: { authorization: `Bearer ${await deps.accessToken()}` },
    });
    if (res.ok) {
      const wire = (await res.json()) as WireVault | null;
      const blob = wire ? toBlob(wire) : null;
      const keysCt = wire?.keys_ct ?? null;
      if (blob) await deps.store.set(VAULT_CACHE, blob);
      if (keysCt) await deps.store.set(KEYS_CACHE, keysCt);
      return { blob, keysCt };
    }
  } catch {
    /* offline — fall back to cache */
  }
  return {
    blob: (await deps.store.get<VaultBlob>(VAULT_CACHE)) ?? null,
    keysCt: (await deps.store.get<Sealed>(KEYS_CACHE)) ?? null,
  };
}

export async function putVault(
  deps: VaultRemoteDeps,
  blob: VaultBlob,
  keysCt: Sealed | null,
): Promise<void> {
  await deps.store.set(VAULT_CACHE, blob);
  if (keysCt) await deps.store.set(KEYS_CACHE, keysCt);
  const res = await fetch(`${deps.base}/vault`, {
    method: 'PUT',
    headers: {
      'content-type': 'application/json',
      authorization: `Bearer ${await deps.accessToken()}`,
    },
    body: JSON.stringify(toWire(blob, keysCt)),
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { error?: string };
    throw new Error(body.error ?? `vault save failed (${res.status})`);
  }
}
