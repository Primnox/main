/* Byte / base64 / utf-8 helpers. Base64 (not base64url) is used everywhere a
   blob is stored as JSON. `btoa`/`atob` are global in modern browsers and in
   Node >= 18. */

export function bytesToB64(b: Uint8Array): string {
  let s = '';
  const chunk = 0x8000;
  for (let i = 0; i < b.length; i += chunk) {
    s += String.fromCharCode(...b.subarray(i, i + chunk));
  }
  return btoa(s);
}

export function b64ToBytes(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export const utf8 = (s: string): Uint8Array => new TextEncoder().encode(s);
export const fromUtf8 = (b: Uint8Array): string => new TextDecoder().decode(b);

export function randomBytes(n: number): Uint8Array {
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return b;
}

/** Best-effort scrub of key material we are done with. JS gives no real
    guarantee, but zeroing the one buffer we hold is still worth doing. */
export function wipe(b: Uint8Array): void {
  b.fill(0);
}
