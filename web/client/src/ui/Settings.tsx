import { useEffect, useState } from 'react';
import type { PrimnoxClient } from '../client';
import type { ProviderId } from '../model';
import { config } from '../config';
import { beginInstall, disconnectGitHub, githubStatus } from '../github/connect';
import type { SessionStore } from '../auth/session';

const PROVIDERS: { id: ProviderId; label: string; hint: string }[] = [
  { id: 'openrouter', label: 'OpenRouter', hint: 'e.g. anthropic/claude-3.5-sonnet, openai/gpt-4o' },
  { id: 'anthropic', label: 'Anthropic', hint: 'e.g. claude-3-5-sonnet-latest' },
  { id: 'gemini', label: 'Google Gemini', hint: 'e.g. gemini-1.5-flash' },
  { id: 'groq', label: 'Groq', hint: 'e.g. llama-3.1-70b-versatile' },
];

const field =
  'w-full border border-dr-rule-firm bg-[var(--bg)] px-2.5 py-2 font-mono text-[13px] text-on-surface outline-none focus-visible:border-primary';

export function Settings({
  client,
  auth,
  onClose,
}: {
  client: PrimnoxClient;
  auth: SessionStore;
  onClose: () => void;
}) {
  const [provider, setProvider] = useState<ProviderId>('openrouter');
  const [model, setModel] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [keys, setKeys] = useState(client.listProviderKeys());
  const [gh, setGh] = useState<{ status: string; repoFullName: string | null }>({ status: 'unknown', repoFullName: null });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ghDeps = { appSlug: config.githubAppSlug, renderApiBase: config.renderApiBase, accessToken: auth.accessToken };

  useEffect(() => {
    githubStatus(ghDeps).then(setGh).catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addKey = async () => {
    setBusy(true);
    setError(null);
    try {
      await client.setProviderKey({ provider, model: model.trim(), apiKey: apiKey.trim() });
      setKeys(client.listProviderKeys());
      setApiKey('');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeKey = async (p: ProviderId) => {
    await client.removeProviderKey(p);
    setKeys(client.listProviderKeys());
  };

  const hint = PROVIDERS.find((p) => p.id === provider)!.hint;

  return (
    <div className="mx-auto w-full max-w-[560px] px-5 pb-12 pt-6">
      <div className="flex items-baseline justify-between">
        <h2 className="px-eyebrow">[ Settings ]</h2>
        <button className="px-btn-ghost" onClick={onClose}>
          Close
        </button>
      </div>

      <section className="px-panel mt-4 p-4">
        <h3 className="px-label mb-1">Model keys</h3>
        <p className="mb-3 font-mono text-[11.5px] text-on-surface-variant">
          Stored encrypted in your vault. Sent directly to the provider — never to Primnox.
        </p>
        <label className="px-label mb-1 block">Provider</label>
        <select className={field} value={provider} onChange={(e) => setProvider(e.target.value as ProviderId)}>
          {PROVIDERS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
        <label className="px-label mb-1 mt-3 block">Model</label>
        <input className={field} value={model} onChange={(e) => setModel(e.target.value)} placeholder={hint} />
        <label className="px-label mb-1 mt-3 block">API key</label>
        <input className={field} type="password" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
        <button className="px-btn mt-4" disabled={busy || !model || !apiKey} onClick={addKey}>
          Save key
        </button>

        {keys.length > 0 && (
          <ul className="mt-4">
            {keys.map((k) => (
              <li
                key={k.provider}
                className="flex items-center justify-between gap-2 border-t border-dr-rule py-2 font-mono text-[11px] text-on-surface-variant"
              >
                <span>
                  {k.provider} · {k.model} · ••••{k.apiKey.slice(-4)}
                </span>
                <button className="px-btn-ghost !px-2 !py-0.5 text-[10px]" onClick={() => void removeKey(k.provider)}>
                  remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="px-panel mt-4 p-4">
        <h3 className="px-label mb-1">GitHub</h3>
        <p className="mb-3 font-mono text-[11.5px] text-on-surface-variant">
          A least-privilege App on one repo holds your encrypted archive. Render keeps the token; it
          only ever writes ciphertext.
        </p>
        {gh.status === 'connected' ? (
          <>
            <p className="font-mono text-[11px] text-on-surface-variant">
              connected · <span className="text-success">{gh.repoFullName}</span>
            </p>
            <button
              className="px-btn-ghost mt-3"
              onClick={async () => {
                await disconnectGitHub(ghDeps);
                setGh({ status: 'disconnected', repoFullName: null });
              }}
            >
              Disconnect
            </button>
          </>
        ) : (
          <button className="px-btn" onClick={() => beginInstall(config.githubAppSlug)}>
            Connect GitHub
          </button>
        )}
      </section>

      <section className="px-panel mt-4 p-4">
        <h3 className="px-label mb-1">Session</h3>
        <div className="mt-2 flex gap-2">
          <button className="px-btn-ghost" onClick={() => client.lock()}>
            Lock vault
          </button>
          <button className="px-btn-ghost" onClick={() => void auth.signOut()}>
            Sign out
          </button>
        </div>
      </section>

      {error && <div className="mt-4 border border-primary/60 p-2 font-mono text-[11.5px] text-primary">{error}</div>}
    </div>
  );
}
