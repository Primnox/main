/* Session state machine. Wraps an AuthClient and exposes:
     - a status the UI renders (loading / authenticated / unauthenticated / expired)
     - `accessToken()`, the token provider HttpTransport needs
   It is an observable store shaped for React's useSyncExternalStore. */

import type { AuthClient, AuthStatus, Session } from './types';

export interface SessionSnapshot {
  status: AuthStatus;
  session: Session | null;
}

const REFRESH_SKEW_MS = 10_000;

export class SessionStore {
  private status: AuthStatus = 'loading';
  private session: Session | null = null;
  private snapshot: SessionSnapshot = { status: 'loading', session: null };
  private readonly listeners = new Set<() => void>();
  private offChange: (() => void) | null = null;

  constructor(private readonly client: AuthClient) {}

  async init(): Promise<void> {
    this.session = await this.client.getSession();
    this.set(this.session ? 'authenticated' : 'unauthenticated');
    this.offChange = this.client.onChange((s) => {
      const wasAuthed = this.status === 'authenticated';
      this.session = s;
      if (s) this.set('authenticated');
      else this.set(wasAuthed ? 'expired' : 'unauthenticated');
    });
  }

  dispose(): void {
    this.offChange?.();
    this.offChange = null;
    this.listeners.clear();
  }

  getSnapshot = (): SessionSnapshot => this.snapshot;
  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  /** For HttpTransport. Throws if not authenticated. Re-reads the client if the
      current token is within the refresh skew (supabase-js auto-refreshes; we
      just pick up the fresher token). */
  accessToken = async (): Promise<string> => {
    if (!this.session) throw new Error('not authenticated');
    if (this.session.expiresAt * 1000 - Date.now() < REFRESH_SKEW_MS) {
      this.session = await this.client.getSession();
      if (!this.session) {
        this.set('expired');
        throw new Error('session expired');
      }
    }
    return this.session.accessToken;
  };

  signInWithPassword(email: string, password: string): Promise<Session> {
    return this.client.signInWithPassword(email, password).then((s) => {
      this.session = s;
      this.set('authenticated');
      return s;
    });
  }

  signInWithGitHub(redirectTo: string): Promise<void> {
    return this.client.signInWithOAuth('github', redirectTo);
  }

  async signOut(): Promise<void> {
    await this.client.signOut();
    this.session = null;
    this.set('unauthenticated');
  }

  private set(status: AuthStatus): void {
    if (status === this.status && this.snapshot.session === this.session) return;
    this.status = status;
    this.snapshot = { status, session: this.session };
    for (const l of this.listeners) l();
  }
}
