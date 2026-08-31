/* The vault (CRS/1.0-W §5, §W1).

   passphrase --Argon2id--> KEK --unwrap--> DEK --AES-256-GCM--> all content

   The DEK is random, generated once, and never changes for the life of the
   vault. Changing the passphrase re-wraps the DEK under a new KEK; it does not
   re-encrypt data. The VaultBlob holds only ciphertext and a public salt, so
   it is safe to store in Supabase and in the user's GitHub repo (§6). No
   server ever sees the KEK, the DEK, or the passphrase (§W1). */

import { bytesToB64, randomBytes, wipe } from './bytes';
import { DEFAULT_KDF, KdfCost, KdfParams, deriveKek, importAesKey, newKdfParams } from './kdf';
import { Sealed, open, seal } from './aead';
import { newMnemonic, recoveryKekFromMnemonic } from './mnemonic';

export interface VaultBlob {
  v: 1;
  kdf: KdfParams; // passphrase KDF — salt rotates on passphrase change
  wrappedDek: Sealed; // seal(KEK, DEK, DEK_AAD)
  wrappedDekRecovery?: Sealed; // seal(recoveryKEK, DEK, DEK_RECOVERY_AAD)
  recoverySaltB64?: string; // HKDF salt for recoveryKEK — never rotated
  keyVersion: number;
}

const DEK_AAD = new TextEncoder().encode('primnox-web/dek/v1');
const DEK_RECOVERY_AAD = new TextEncoder().encode('primnox-web/dek-recovery/v1');

async function unwrapWithKek(kek: CryptoKey, wrapped: Sealed, aad: Uint8Array): Promise<Uint8Array> {
  try {
    return await open(kek, wrapped, aad);
  } catch {
    throw new Error('wrong passphrase or corrupt vault');
  }
}

/** Create a fresh vault. Returns the DEK ready for use plus the blob to persist. */
export async function createVault(
  passphrase: string,
  cost: KdfCost = DEFAULT_KDF,
): Promise<{ dek: CryptoKey; blob: VaultBlob }> {
  const kdf = newKdfParams(cost);
  const kek = await deriveKek(passphrase, kdf);
  const dekBytes = randomBytes(32);
  try {
    const wrappedDek = await seal(kek, dekBytes, DEK_AAD);
    const dek = await importAesKey(dekBytes);
    return { dek, blob: { v: 1, kdf, wrappedDek, keyVersion: 1 } };
  } finally {
    wipe(dekBytes);
  }
}

/** Unlock with the passphrase. Throws on a wrong passphrase. */
export async function unlockVault(passphrase: string, blob: VaultBlob): Promise<CryptoKey> {
  const kek = await deriveKek(passphrase, blob.kdf);
  const dekBytes = await unwrapWithKek(kek, blob.wrappedDek, DEK_AAD);
  try {
    return await importAesKey(dekBytes);
  } finally {
    wipe(dekBytes);
  }
}

/** Re-wrap the DEK under a new passphrase. Data is untouched. */
export async function changePassphrase(
  oldPassphrase: string,
  newPassphrase: string,
  blob: VaultBlob,
  cost: KdfCost = DEFAULT_KDF,
): Promise<VaultBlob> {
  const oldKek = await deriveKek(oldPassphrase, blob.kdf);
  const dekBytes = await unwrapWithKek(oldKek, blob.wrappedDek, DEK_AAD);
  try {
    const kdf = newKdfParams(cost);
    const newKek = await deriveKek(newPassphrase, kdf);
    const wrappedDek = await seal(newKek, dekBytes, DEK_AAD);
    // wrappedDekRecovery + recoverySaltB64 are deliberately left untouched:
    // the DEK and the recovery-KEK are both unchanged.
    return { ...blob, kdf, wrappedDek, keyVersion: blob.keyVersion + 1 };
  } finally {
    wipe(dekBytes);
  }
}

/** Add (or replace) the recovery wrap. Returns the new blob and the phrase to
    show the user exactly once. */
export async function addRecovery(
  passphrase: string,
  blob: VaultBlob,
): Promise<{ blob: VaultBlob; mnemonic: string }> {
  const kek = await deriveKek(passphrase, blob.kdf);
  const dekBytes = await unwrapWithKek(kek, blob.wrappedDek, DEK_AAD);
  try {
    const mnemonic = newMnemonic();
    const recoverySaltB64 = bytesToB64(randomBytes(16));
    const rKek = await recoveryKekFromMnemonic(mnemonic, recoverySaltB64);
    const wrappedDekRecovery = await seal(rKek, dekBytes, DEK_RECOVERY_AAD);
    return { blob: { ...blob, wrappedDekRecovery, recoverySaltB64 }, mnemonic };
  } finally {
    wipe(dekBytes);
  }
}

export function hasRecovery(blob: VaultBlob): boolean {
  return !!blob.wrappedDekRecovery && !!blob.recoverySaltB64;
}

/** Unlock with the recovery mnemonic instead of the passphrase. */
export async function unlockWithMnemonic(mnemonic: string, blob: VaultBlob): Promise<CryptoKey> {
  if (!hasRecovery(blob)) throw new Error('no recovery configured for this vault');
  const rKek = await recoveryKekFromMnemonic(mnemonic, blob.recoverySaltB64!);
  let dekBytes: Uint8Array;
  try {
    dekBytes = await open(rKek, blob.wrappedDekRecovery!, DEK_RECOVERY_AAD);
  } catch {
    throw new Error('invalid recovery phrase');
  }
  try {
    return await importAesKey(dekBytes);
  } finally {
    wipe(dekBytes);
  }
}

/** Recover: unwrap via the mnemonic, then re-wrap under a new passphrase. */
export async function resetPassphraseWithMnemonic(
  mnemonic: string,
  newPassphrase: string,
  blob: VaultBlob,
  cost: KdfCost = DEFAULT_KDF,
): Promise<VaultBlob> {
  if (!hasRecovery(blob)) throw new Error('no recovery configured for this vault');
  const rKek = await recoveryKekFromMnemonic(mnemonic, blob.recoverySaltB64!);
  let dekBytes: Uint8Array;
  try {
    dekBytes = await open(rKek, blob.wrappedDekRecovery!, DEK_RECOVERY_AAD);
  } catch {
    throw new Error('invalid recovery phrase');
  }
  try {
    const kdf = newKdfParams(cost);
    const newKek = await deriveKek(newPassphrase, kdf);
    const wrappedDek = await seal(newKek, dekBytes, DEK_AAD);
    return { ...blob, kdf, wrappedDek, keyVersion: blob.keyVersion + 1 };
  } finally {
    wipe(dekBytes);
  }
}
