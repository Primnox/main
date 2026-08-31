/* Supabase-backed AuthClient + a shared client singleton.

   This file is the only place that imports supabase-js. It also exports the
   client for the Realtime source. `MockAuthClient` covers tests and offline
   dev with no project configured. */

import { createClient, type SupabaseClient } from '@supabase/supabase-js';
import { config } from '../config';
import type { AuthClient, Session } from './types';

let client: SupabaseClient | null = null;

export function supabase(): SupabaseClient {
  if (!client) {
    if (!config.supabaseUrl || !config.supabaseAnonKey) {
      throw new Error('Supabase is not configured (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY)');
    }
    client = createClient(config.supabaseUrl, config.supabaseAnonKey, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true },
    });
  }
  return client;
}

const toSession = (s: {
  user: { id: string };
  access_token: string;
  expires_at?: number;
} | null): Session | null =>
  s ? { userId: s.user.id, accessToken: s.access_token, expiresAt: s.expires_at ?? 0 } : null;

export class SupabaseAuthClient implements AuthClient {
  private readonly sb = supabase();

  async getSession(): Promise<Session | null> {
    const { data } = await this.sb.auth.getSession();
    return toSession(data.session);
  }

  onChange(cb: (s: Session | null) => void): () => void {
    const { data } = this.sb.auth.onAuthStateChange((_event, session) => {
      cb(toSession(session));
    });
    return () => data.subscription.unsubscribe();
  }

  async signInWithPassword(email: string, password: string): Promise<Session> {
    const { data, error } = await this.sb.auth.signInWithPassword({ email, password });
    const session = toSession(data.session);
    if (error || !session) throw new Error(error?.message ?? 'sign-in failed');
    return session;
  }

  async signInWithOAuth(provider: 'github', redirectTo: string): Promise<void> {
    const { error } = await this.sb.auth.signInWithOAuth({ provider, options: { redirectTo } });
    if (error) throw new Error(error.message);
  }

  async signOut(): Promise<void> {
    await this.sb.auth.signOut();
  }
}

/** In-memory AuthClient for tests and offline dev. */
export class MockAuthClient implements AuthClient {
  private session: Session | null;
  private readonly subs = new Set<(s: Session | null) => void>();

  constructor(initial: Session | null = null) {
    this.session = initial;
  }

  async getSession(): Promise<Session | null> {
    return this.session;
  }
  onChange(cb: (s: Session | null) => void): () => void {
    this.subs.add(cb);
    return () => this.subs.delete(cb);
  }
  async signInWithPassword(email: string): Promise<Session> {
    this.session = {
      userId: `user_${email}`,
      accessToken: `tok_${Date.now()}`,
      expiresAt: Math.floor(Date.now() / 1000) + 3600,
    };
    this.fire();
    return this.session;
  }
  async signInWithOAuth(): Promise<void> {
    // a real client would redirect; the mock just signs in
    await this.signInWithPassword('oauth@github');
  }
  async signOut(): Promise<void> {
    this.session = null;
    this.fire();
  }
  /** test helper — the session ends and the client notifies (onAuthStateChange) */
  expire(): void {
    this.session = null;
    this.fire();
  }
  /** test helper — the session ends but no notification fires; only a
      getSession() re-read reveals it */
  dropSilently(): void {
    this.session = null;
  }
  /** test helper — supabase-js silently refreshed to a newer token */
  rotate(accessToken: string, expiresInSec = 3600): void {
    this.session = {
      userId: this.session?.userId ?? 'user_rotated',
      accessToken,
      expiresAt: Math.floor(Date.now() / 1000) + expiresInSec,
    };
  }
  private fire(): void {
    for (const s of this.subs) s(this.session);
  }
}
