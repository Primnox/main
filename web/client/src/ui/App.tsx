import { useCallback, useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { FolderPlus, Pin, Plus, Search, X } from 'lucide-react';
import { createPrimnox, isConfigured } from '../setup';
import { createMockPrimnox } from '../dev/mock';
import { config } from '../config';
import { completeInstall, readInstallCallback, type InstallCallback } from '../github/connect';
import { ChatsContext, type ChatActions } from '../lib/contexts';
import { groupByDay } from '../lib/groupByDay';
import { turnsOf } from '../runtime/reducer';
import { AppRail, type Section } from '../components/AppRail';
import { ContextSidebar } from '../components/ContextSidebar';
import { ChatRow } from '../components/ChatRow';
import { ListSkeleton } from '../components/ui';
import { AuthGate } from './AuthGate';
import { VaultGate } from './VaultGate';
import { Settings } from './Settings';
import { Chat } from './Chat';
import { usePrimnox, useRuntime, useSession } from './hooks';
import { loadMeta, saveMeta, titleFrom, type ConversationMeta } from './conversations';

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

  const [section, setSection] = useState<Section>('chat');
  const [chatsOpen, setChats] = useState(true);
  const [chatQuery, setChatQuery] = useState('');
  const [conversationId, setConversationId] = useState<string>(() => client.newConversationId());
  const [meta, setMeta] = useState<Record<string, ConversationMeta>>(() => loadMeta());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);

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

  const update = useCallback((next: Record<string, ConversationMeta>) => {
    setMeta(next);
    saveMeta(next);
  }, []);

  /* A conversation earns a row once it has a turn. Titling from the first user
     message rather than at creation is why: an empty conversation has nothing
     to be called, and a list full of "New Chat" is a list you cannot read. */
  const rows = useMemo(() => {
    const ids = Object.keys(runtime.conversations);
    const out: ConversationMeta[] = [];
    for (const id of ids) {
      const turns = turnsOf(runtime, id);
      if (turns.length === 0) continue;
      const stored = meta[id];
      out.push(
        stored ?? {
          id,
          title: titleFrom(turns[0]?.userText),
          pinned: false,
          archived: false,
          created_at: turns[0]?.createdAt || Date.now(),
        },
      );
    }
    return out
      .filter((c) => !c.archived)
      .sort((a, b) => b.created_at - a.created_at);
  }, [runtime, meta]);

  const pinned = useMemo(() => rows.filter((c) => c.pinned), [rows]);
  const loose = useMemo(() => rows.filter((c) => !c.pinned), [rows]);

  const matches = useMemo(() => {
    const q = chatQuery.trim().toLowerCase();
    if (!q) return null;
    return rows.filter((c) => c.title.toLowerCase().includes(q));
  }, [rows, chatQuery]);

  const patch = useCallback(
    (id: string, fields: Partial<ConversationMeta>) => {
      const base =
        meta[id] ?? rows.find((c) => c.id === id) ?? {
          id, title: 'New Chat', pinned: false, archived: false, created_at: Date.now(),
        };
      update({ ...meta, [id]: { ...base, ...fields } });
    },
    [meta, rows, update],
  );

  const chatActions: ChatActions = useMemo(
    () => ({
      activeId: conversationId,
      // Folders are a desktop feature backed by a server-side table. Web has no
      // store for them, so the list is flat rather than pretending otherwise.
      folders: [],
      editingId,
      menuId,
      draggingId: null,
      setDragging: () => {},
      open: (id) => { setConversationId(id); setChatQuery(''); },
      setMenu: setMenuId,
      beginRename: setEditingId,
      commitRename: (id, title) => {
        patch(id, { title: title.trim() || 'New Chat' });
        setEditingId(null);
      },
      togglePin: (c) => patch(c.id, { pinned: !c.pinned }),
      move: () => {},
      archive: (id) => patch(id, { archived: true }),
      remove: (c) => patch(c.id, { archived: true }),
    }),
    [conversationId, editingId, menuId, patch],
  );

  const needsVault = snap.vault !== 'unlocked' || snap.pendingRecovery;
  const unlocked = session.status === 'authenticated' && !needsVault;
  const activeTitle = rows.find((c) => c.id === conversationId)?.title;

  const newChat = () => {
    setConversationId(client.newConversationId());
    setChatQuery('');
  };

  /* The gates own the whole window. A rail and a conversation list around a
     sign-in form would be chrome for an app you are not yet in. */
  let gate: ReactElement | null = null;
  if (session.status === 'loading') {
    gate = <div className="mx-auto mt-24 px-5 text-on-surface-variant">Loading…</div>;
  } else if (session.status !== 'authenticated') {
    gate = <AuthGate auth={client.auth} />;
  } else if (needsVault) {
    gate = <VaultGate client={client} state={snap.vault} pendingRecovery={snap.pendingRecovery} />;
  }

  const bannerEl = banner && (
    <button
      className="shrink-0 border-b border-dr-rule bg-surface px-4 py-2 text-left font-mono text-[11px] text-on-surface-variant"
      onClick={() => setBanner(null)}
    >
      {banner} <span className="text-primary">dismiss</span>
    </button>
  );

  if (gate) {
    return (
      <div className="flex h-screen w-full flex-col bg-surface text-on-surface font-sans overflow-clip">
        {bannerEl}
        <main className="flex min-h-0 flex-1 flex-col overflow-y-auto">{gate}</main>
      </div>
    );
  }

  return (
    <ChatsContext.Provider value={chatActions}>
    {/* `overflow-clip`, not `overflow-hidden`. `hidden` makes this a scroll
        container, and focusing anything inside one makes the browser scroll it
        into view — but with no scrollbar there is no way back. `clip` clips
        identically without ever becoming scrollable. */}
    <div className="flex flex-col h-screen w-full bg-surface text-on-surface font-sans overflow-clip">
      {bannerEl}

      {/* `min-h-0` is load-bearing: a flex child defaults to min-height:auto,
          which refuses to shrink below its content, so the row would grow past
          the viewport and push the scrollable panes off the bottom instead of
          scrolling inside them. */}
      <div className="flex flex-1 min-h-0 w-full overflow-clip">

        <AppRail
          section={section}
          onSection={(s) => {
            // Chats while already in Chats toggles the list. This is the only
            // way back once it is collapsed, and it works because the rail is
            // pinned and cannot scroll out of reach.
            if (s === 'chat' && section === 'chat') setChats(!chatsOpen);
            else { setSection(s); if (s === 'chat') setChats(true); }
          }}
          connected={snap.online} synced={snap.online} />

        {section === 'chat' && (
        <ContextSidebar title="Conversations"
          open={chatsOpen} onClose={() => setChats(false)}
          actions={
            <button disabled title="Folders need a store Primnox Web does not have yet"
              aria-label="New folder"
              className="p-1.5 rounded-lg text-on-surface/50 disabled:opacity-30 disabled:cursor-not-allowed">
              <FolderPlus size={13} />
            </button>
          }>
          {/* The thing that ADDS to this list, at the top of the list it adds
              to. It was in the rail, which is for destinations. */}
          <div className="sticky top-0 z-10 bg-[var(--nav-bg)] px-3 pt-3 pb-2 space-y-2">
            <button onClick={newChat}
              className="px-interactive group/n w-full flex items-center justify-between
                         rounded-lg border border-on-surface/[0.10] px-3 py-2 text-[13px]
                         hover:border-on-surface/25 hover:bg-on-surface/[0.03]">
              New chat
              <Plus size={14} aria-hidden="true"
                className="opacity-60 transition-transform duration-200 group-hover/n:rotate-90" />
            </button>

            <label htmlFor="chat-search" className="sr-only">Search chats</label>
            <div className="flex items-center gap-2 rounded-lg border border-on-surface/[0.10]
                            px-2.5 py-1.5 focus-within:border-on-surface/30">
              <Search size={12} className="shrink-0 text-on-surface/50" aria-hidden="true" />
              <input id="chat-search" type="search" value={chatQuery}
                onChange={e => setChatQuery(e.target.value)}
                placeholder="Search chats"
                className="min-w-0 flex-1 bg-transparent text-[12px] outline-none
                           placeholder:text-on-surface/50" />
              {chatQuery && (
                <button type="button" onClick={() => setChatQuery('')}
                  aria-label="Clear search"
                  className="px-interactive shrink-0 text-on-surface/50 hover:text-on-surface">
                  <X size={12} aria-hidden="true" />
                </button>
              )}
            </div>
          </div>

          <nav className="px-2 pb-3">
            {/* While searching, one flat list of hits. Day groups are a
                browsing aid; during a search they scatter three matches across
                three headings and hide how many there are. */}
            {matches !== null ? (
              <>
                <p className="px-label mx-3 mb-1.5">
                  {matches.length} {matches.length === 1 ? 'match' : 'matches'}
                </p>
                {matches.map(c => <ChatRow key={c.id} c={c} />)}
                {matches.length === 0 && (
                  <p className="px-3 py-4 text-xs text-on-surface/50">
                    Nothing matches “{chatQuery.trim()}”.
                  </p>
                )}
              </>
            ) : snap.vault !== 'unlocked' ? (
              <ListSkeleton count={5} lines={1} />
            ) : (
              <>
                {pinned.length > 0 && (
                  <>
                    <p className="px-label mx-3 mb-1.5 flex items-center gap-1.5">
                      <Pin size={9} aria-hidden="true" /> Pinned
                    </p>
                    {pinned.map(c => <ChatRow key={c.id} c={c} />)}
                    <div className="h-3" />
                  </>
                )}
                {/* The hairline marks where pinned ends and the run of chats
                    begins. Desktop puts folders in this gap; web has none. */}
                {pinned.length > 0 && loose.length > 0 && (
                  <div className="mx-3 mt-2 mb-1 border-t border-on-surface/[0.07]" />
                )}
                {/* Grouped by day. Seventy rows of identical-looking titles is
                    a wall, not a list — the date is the only thing that
                    distinguishes one from another at a glance. */}
                {groupByDay(loose).map(([label, group]) => (
                  <div key={label}>
                    {label && <p className="px-label px-3 pt-3 pb-1.5 text-on-surface/50">{label}</p>}
                    {group.map((c: ConversationMeta) => <ChatRow key={c.id} c={c} />)}
                  </div>
                ))}
                {rows.length === 0 && (
                  <p className="px-3 py-4 text-xs text-on-surface/50">Nothing yet</p>
                )}
              </>
            )}
          </nav>
        </ContextSidebar>
        )}

        {section === 'chat' ? (
          <Chat
            client={client}
            conversationId={conversationId}
            title={activeTitle}
            chatsOpen={chatsOpen}
            connected={snap.online}
            onShowChats={() => setChats(true)}
            onOpenSettings={() => setSection('settings')}
          />
        ) : (
          <main className="relative flex-1 flex flex-col min-w-0 overflow-y-auto">
            <Settings client={client} auth={client.auth} onClose={() => setSection('chat')} />
          </main>
        )}
      </div>
    </div>
    </ChatsContext.Provider>
  );
}
