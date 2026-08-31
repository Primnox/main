import { useState } from 'react';
import type { SessionStore } from '../auth/session';

const field =
  'w-full border border-dr-rule-firm bg-[var(--bg)] px-2.5 py-2 font-mono text-[13px] text-on-surface outline-none focus-visible:border-primary';

export function AuthGate({ auth }: { auth: SessionStore }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = (fn: () => Promise<unknown>) => async () => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto mt-24 w-full max-w-[420px] px-5">
      <h2 className="px-eyebrow mb-1">[ Sign in ]</h2>
      <p className="mb-5 font-mono text-[12px] text-on-surface-variant">
        Identity only. Your passphrase and data never reach this server.
      </p>

      <label className="px-label mb-1 block" htmlFor="email">
        Email
      </label>
      <input id="email" className={field} type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />

      <label className="px-label mb-1 mt-4 block" htmlFor="pw">
        Password
      </label>
      <input
        id="pw"
        className={field}
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        onKeyDown={(e) => e.key === 'Enter' && void run(() => auth.signInWithPassword(email, password))()}
        autoComplete="current-password"
      />

      <div className="mt-5 flex gap-2">
        <button className="px-btn" disabled={busy || !email || !password} onClick={run(() => auth.signInWithPassword(email, password))}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
        <button
          className="px-btn-ghost"
          disabled={busy}
          onClick={run(() => auth.signInWithGitHub(window.location.origin + window.location.pathname))}
        >
          Continue with GitHub
        </button>
      </div>

      {error && <div className="mt-4 border border-primary/60 p-2 font-mono text-[11.5px] text-primary">{error}</div>}
    </div>
  );
}
