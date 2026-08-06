/**
 * Single source of truth for the backend origin.
 *
 * `http://localhost:4009` was written out as a literal in 34 places across 14
 * files. Changing the port, running two instances side by side, or pointing the
 * UI at a backend on another host meant a find-and-replace across the codebase
 * and hoping none were missed.
 *
 * Override at build time with VITE_API_BASE (e.g. VITE_API_BASE=http://127.0.0.1:5000).
 */
export const API_BASE: string =
  (import.meta as any).env?.VITE_API_BASE || 'http://localhost:4009';

/** WebSocket origin, derived from API_BASE so the two can never disagree. */
export const WS_BASE: string = API_BASE.replace(/^http/, 'ws');

/** Build an absolute backend URL from a path: apiUrl('/api/notes'). */
export const apiUrl = (path: string): string =>
  `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
