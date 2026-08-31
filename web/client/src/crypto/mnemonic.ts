/* Recovery mnemonic (CRS/1.0-W §5, resolved Q9).

   A 24-word BIP-39 phrase encodes a 256-bit recovery secret. That secret is
   run through HKDF-SHA256 to a recovery-KEK, which wraps a second copy of the
   DEK. Losing the passphrase but keeping the phrase → unwrap, set a new
   passphrase. Losing both → the data is unrecoverable, and setup says so. */

import { generateMnemonic, mnemonicToEntropy, validateMnemonic } from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english';
import { b64ToBytes, utf8 } from './bytes';
import { importAesKey } from './kdf';

const RECOVERY_INFO = utf8('primnox-web/recovery-kek/v1');

export function newMnemonic(): string {
  return generateMnemonic(wordlist, 256);
}

export function normalizeMnemonic(m: string): string {
  return m.trim().toLowerCase().replace(/\s+/g, ' ');
}

export function isValidMnemonic(m: string): boolean {
  return validateMnemonic(normalizeMnemonic(m), wordlist);
}

/** recovery-KEK = HKDF-SHA256(entropy(mnemonic), salt=recoverySalt). The salt
    is stored per-vault and never rotated on passphrase change. */
export async function recoveryKekFromMnemonic(
  mnemonic: string,
  recoverySaltB64: string,
): Promise<CryptoKey> {
  const norm = normalizeMnemonic(mnemonic);
  if (!validateMnemonic(norm, wordlist)) throw new Error('invalid recovery phrase');
  const entropy = mnemonicToEntropy(norm, wordlist); // 32 bytes
  const bs = (b: Uint8Array): BufferSource => b as unknown as BufferSource;
  const ikm = await crypto.subtle.importKey('raw', bs(entropy), 'HKDF', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits(
    { name: 'HKDF', hash: 'SHA-256', salt: bs(b64ToBytes(recoverySaltB64)), info: bs(RECOVERY_INFO) },
    ikm,
    256,
  );
  return importAesKey(new Uint8Array(bits));
}
