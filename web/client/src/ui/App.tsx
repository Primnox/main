import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { createPrimnox, isConfigured } from '../setup';
import { createMockPrimnox } from '../dev/mock';
import { config } from '../config';
import { completeInstall, readInstallCallback, type InstallCallback } from '../github/connect';
import { AuthGate } from './AuthGate';
import { VaultGate } from './VaultGate';
import { Settings } from './Settings';
import { Chat } from './Chat';
import { usePrimnox, useRuntime, useSession } from './hooks';

const MOCK = import.meta.env.VITE_MOCK === '1' || !isConfigured();

export function App() {
  return <Shell />;
}

function Shell() {
  const client = useMemo(() => (MOCK ? createMockPrimnox() : createPrimnox()), []);
  const started = useRef(false);
  const [banner, setBanner] = useState<string | null>(
    MOCK ? 'Mock mode — no Supabase / Render / GitHub. Sign in with any email + password.' : null,
  );

  const session = useSession(client.auth);
  const snap = usePrimnox(client);
  const runtime = useRuntime(client);

  const [settingsOpen, setSettingsOpen] = useState(false);
  const [conversationId, setConversationId] = useState<string>(() => client.newConversationId());

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void client.init().catch((e) => setBanner(String(e)));
  }, [client]);

  useEffect(() => {
    if (session.status !== 'authenticated') return;
    let cb: InstallCallback | null;
    try {
      cb = readInstallCallback();
    } catch (e) {
      setBanner(e instanceof Error ? e.message : String(e));
      return;
    }
    if (!cb) return;
    void completeInstall(
      { appSlug: config.githubAppSlug, renderApiBase: config.renderApiBase, accessToken: client.auth.accessToken },
      cb,
    )
      .then(({ repoFullName }) => {
        setBanner(`GitHub connected: ${repoFullName}`);
        window.history.replaceState({}, '', window.location.pathname);
      })
      .catch((e) => setBanner(String(e)));
  }, [session.status, client]);

  useEffect(() => {
    if (!MOCK || snap.vault !== 'unlocked') return;
    if (client.listProviderKeys().length === 0) {
      void client.setProviderKey({ provider: 'openrouter', model: 'echo', apiKey: 'mock' });
    }
  }, [snap.vault, client]);

  const conversations = Object.keys(runtime.conversations);
  const needsVault = snap.vault !== 'unlocked' || snap.pendingRecovery;
  const unlocked = session.status === 'authenticated' && !needsVault;

  let body: ReactElement;
  if (session.status === 'loading') {
    body = <div className="mx-auto mt-24 px-5 text-on-surface-variant">Loading…</div>;
  } else if (session.status !== 'authenticated') {
    body = <AuthGate auth={client.auth} />;
  } else if (needsVault) {
    body = <VaultGate client={client} state={snap.vault} pendingRecovery={snap.pendingRecovery} />;
  } else if (settingsOpen) {
    body = <Settings client={client} auth={client.auth} onClose={() => setSettingsOpen(false)} />;
  } else {
    body = <Chat client={client} conversationId={conversationId} />;
  }

  return (
    <div className="flex h-screen flex-col bg-[var(--bg)] text-on-surface">
      <header className="flex items-center gap-3 border-b border-primary/70 px-4 py-2">
        <span className="font-mono text-[11px] tracking-[0.24em]">
          PRIMNOX <span className="text-primary">WEB</span>
        </span>
        <span
          className={`font-mono text-[9px] uppercase tracking-[0.16em] ${
            snap.online ? 'text-success' : 'text-primary'
          }`}
        >
          {snap.online ? 'online' : 'offline'}
        </span>
        <span className="flex-1" />
        {unlocked && (
          <>
            <button className="px-btn-ghost !px-2 !py-1 text-[10px]" onClick={() => setConversationId(client.newConversationId())}>
              New chat
            </button>
            <button className="px-btn-ghost !px-2 !py-1 text-[10px]" onClick={() => setSettingsOpen((v) => !v)}>
              {settingsOpen ? 'Chat' : 'Settings'}
            </button>
          </>
        )}
      </header>

      {banner && (
        <button
          className="border-b border-dr-rule bg-surface px-4 py-2 text-left font-mono text-[11px] text-on-surface-variant"
          onClick={() => setBanner(null)}
        >
          {banner} <span className="text-primary">dismiss</span>
        </button>
      )}

      <div className="flex min-h-0 flex-1">
        {unlocked && !settingsOpen && conversations.length > 1 && (
          <nav className="flex w-[140px] flex-col gap-1 overflow-y-auto border-r border-dr-rule p-2">
            {conversations.map((id) => (
              <button
                key={id}
                className={`border-l px-2 py-1.5 text-left font-mono text-[10px] ${
                  id === conversationId
                    ? 'border-primary text-primary'
                    : 'border-dr-rule text-on-surface-variant'
                }`}
                onClick={() => setConversationId(id)}
              >
                {id.replace('conv_', '').slice(0, 8)}
              </button>
            ))}
          </nav>
        )}
        <main className="flex min-w-0 flex-1 flex-col overflow-y-auto">{body}</main>
      </div>
    </div>
  );
}
