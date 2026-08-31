/* AES-256-GCM AEAD (CRS/1.0-W §4.2, §5).

   One sealed shape for everything that leaves the browser: event payloads,
   message bodies, memory, canvas updates, vault key-wraps. A fresh 96-bit IV
   per call. AAD binds a blob to its envelope (e.g. "msg:<id>/body") so a
   ciphertext cannot be silently moved to another row. Versioned for rotation. */

import { b64ToBytes, bytesToB64, fromUtf8, randomBytes, utf8 } from './bytes';

export interface Sealed {
  v: 1;
  alg: 'A256GCM';
  iv: string; // b64, 12 bytes
  ct: string; // b64, ciphertext || GCM tag
}

export function isSealed(x: unknown): x is Sealed {
  return (
    !!x &&
    typeof x === 'object' &&
    (x as Sealed).v === 1 &&
    (x as Sealed).alg === 'A256GCM' &&
    typeof (x as Sealed).iv === 'string' &&
    typeof (x as Sealed).ct === 'string'
  );
}

// TS 5.7+ types Uint8Array as generic over ArrayBufferLike, which no longer
// matches DOM's BufferSource. Our buffers are always plain ArrayBuffer-backed,
// so a type-only assertion at the WebCrypto boundary is safe.
const bs = (b: Uint8Array): BufferSource => b as unknown as BufferSource;

export async function seal(
  key: CryptoKey,
  plaintext: Uint8Array,
  aad?: Uint8Array,
): Promise<Sealed> {
  const iv = randomBytes(12);
  const params: AesGcmParams = { name: 'AES-GCM', iv: bs(iv) };
  if (aad) params.additionalData = bs(aad);
  const ct = await crypto.subtle.encrypt(params, key, bs(plaintext));
  return { v: 1, alg: 'A256GCM', iv: bytesToB64(iv), ct: bytesToB64(new Uint8Array(ct)) };
}

export async function open(
  key: CryptoKey,
  sealed: Sealed,
  aad?: Uint8Array,
): Promise<Uint8Array> {
  if (!isSealed(sealed)) throw new Error('not a sealed blob');
  const params: AesGcmParams = { name: 'AES-GCM', iv: bs(b64ToBytes(sealed.iv)) };
  if (aad) params.additionalData = bs(aad);
  // subtle.decrypt throws OperationError on a bad key / tag / AAD mismatch.
  const pt = await crypto.subtle.decrypt(params, key, bs(b64ToBytes(sealed.ct)));
  return new Uint8Array(pt);
}

// ── string / JSON convenience, with a string AAD context ──────────────────

export const sealString = (k: CryptoKey, s: string, aadCtx?: string): Promise<Sealed> =>
  seal(k, utf8(s), aadCtx ? utf8(aadCtx) : undefined);

export const openString = async (k: CryptoKey, s: Sealed, aadCtx?: string): Promise<string> =>
  fromUtf8(await open(k, s, aadCtx ? utf8(aadCtx) : undefined));

export const sealJSON = (k: CryptoKey, value: unknown, aadCtx?: string): Promise<Sealed> =>
  sealString(k, JSON.stringify(value), aadCtx);

export const openJSON = async <T>(k: CryptoKey, s: Sealed, aadCtx?: string): Promise<T> =>
  JSON.parse(await openString(k, s, aadCtx)) as T;
