/* Identity (CRS/1.0-W §D5, §3.4). Supabase Auth answers "who is this user?";
   it is not on the data path. The rest of the client depends on this small
   interface, not on supabase-js directly, so it stays mockable and testable. */

export type AuthStatus = 'loading' | 'authenticated' | 'unauthenticated' | 'expired';

export interface Session {
  userId: string;
  accessToken: string;
  /** epoch seconds */
  expiresAt: number;
}

export interface AuthClient {
  getSession(): Promise<Session | null>;
  onChange(cb: (s: Session | null) => void): () => void;
  signInWithPassword(email: string, password: string): Promise<Session>;
  /** redirects the browser; resolves only if the redirect could not start */
  signInWithOAuth(provider: 'github', redirectTo: string): Promise<void>;
  signOut(): Promise<void>;
}
