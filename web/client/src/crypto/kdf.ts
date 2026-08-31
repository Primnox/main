/* Passphrase → KEK (CRS/1.0-W §5).

   Argon2id via hash-wasm (WASM, no native build). The KEK never leaves the
   browser and is never serialized — it exists only as a non-extractable
   AES-GCM CryptoKey used to wrap/unwrap the DEK.

   `m` is memory in KiB. The default (19 MiB, t=2, p=1) follows the OWASP
   Argon2id floor; final tuning against target-hardware unlock time is Q1. */

import { argon2id } from 'hash-wasm';
import { b64ToBytes, bytesToB64, randomBytes, utf8, wipe } from './bytes';

export interface KdfParams {
  alg: 'argon2id';
  m: number; // memory, KiB
  t: number; // iterations
  p: number; // parallelism
  saltB64: string;
}

export type KdfCost = Omit<KdfParams, 'saltB64'>;

export const DEFAULT_KDF: KdfCost = { alg: 'argon2id', m: 19_456, t: 2, p: 1 };

export function newKdfParams(cost: KdfCost = DEFAULT_KDF): KdfParams {
  return { ...cost, saltB64: bytesToB64(randomBytes(16)) };
}

async function deriveRaw(passphrase: string, params: KdfParams): Promise<Uint8Array> {
  if (params.alg !== 'argon2id') throw new Error(`unsupported kdf: ${params.alg}`);
  const pw = utf8(passphrase.normalize('NFKC'));
  const out = await argon2id({
    password: pw,
    salt: b64ToBytes(params.saltB64),
    parallelism: params.p,
    iterations: params.t,
    memorySize: params.m,
    hashLength: 32,
    outputType: 'binary',
  });
  wipe(pw);
  return out as Uint8Array;
}

/** Import 32 raw bytes as a non-extractable AES-GCM key. */
export async function importAesKey(
  raw: Uint8Array,
  usages: KeyUsage[] = ['encrypt', 'decrypt'],
): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    raw as unknown as BufferSource,
    { name: 'AES-GCM' },
    false,
    usages,
  );
}

/** Derive the Key-Encryption-Key from the passphrase. */
export async function deriveKek(passphrase: string, params: KdfParams): Promise<CryptoKey> {
  const raw = await deriveRaw(passphrase, params);
  try {
    return await importAesKey(raw);
  } finally {
    wipe(raw);
  }
}
