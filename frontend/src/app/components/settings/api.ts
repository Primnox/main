/**
 * One definition of the backend origin for the settings screen.
 *
 * `http://localhost:4009` was written out at 19 separate call sites, so changing
 * the port (or pointing the UI at a remote backend) meant a find-and-replace and
 * hoping none were missed. VITE_API_BASE overrides it at build time.
 */
export { API_BASE, apiUrl } from '../../../config';
import { apiUrl } from '../../../config';

/** GET returning parsed JSON, or null on any failure. Settings panels poll
 *  optional endpoints (vault, ollama, cloud backup) that are allowed to be
 *  absent — a rejected promise there would take the whole panel down. */
export async function getJson<T = any>(path: string, timeoutMs = 6000): Promise<T | null> {
  try {
    const res = await fetch(apiUrl(path), { signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

/** POST JSON. Returns the parsed body on success, or null. */
export async function postJson<T = any>(path: string, body?: unknown, timeoutMs = 20000): Promise<T | null> {
  try {
    const res = await fetch(apiUrl(path), {
      method: 'POST',
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (!res.ok) return null;
    const text = await res.text();
    return text ? (JSON.parse(text) as T) : ({} as T);
  } catch {
    return null;
  }
}
