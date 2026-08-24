import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { AlertTriangle, ArrowUp, Check, ChevronRight, EyeOff, FileText, Folder, FolderPlus, Loader2, PanelLeftOpen, PanelRight, Paperclip, Pencil, Pin, Plus, Search, Share2, Square, Trash2, X } from 'lucide-react';
import { CrsSocket, TERMINAL, api, emptyState, reduce, turnsFromHistory, type ConversationState, type CrsEvent } from './lib/crs';
import { CanvasContext, ChatsContext, ViewerContext, type ChatActions, type OpenAsset } from './lib/contexts';
import { groupByDay } from './lib/groupByDay';
import { AppRail, type Section } from './components/AppRail';
import { TitleBar } from './components/TitleBar';
import { AssetViewer } from './components/AssetViewer';
import { Canvas } from './components/Canvas';
import { ChatRow } from './components/ChatRow';
import { ContextRail } from './components/ContextRail';
import { ContextSidebar } from './components/ContextSidebar';
import { Panel } from './components/ui';
import { GraphPanel } from './components/GraphPanel';
import { MemoryPanel } from './components/MemoryPanel';
import { SettingsPanel } from './components/SettingsPanel';
import { TrackRow } from './components/TrackRow';
import { TurnBlock } from './components/TurnBlock';

/* Primnox V2 shell — the Dead Reckoning world (direction seed f80a4f36).
 *
 * This used to say "Layout is Claude's: nav rail, conversation list,
 * transcript on a reading measure" — an honest description of the shell every
 * app in this category ships, and the reason it was replaced.
 *
 * A session is now a plotted track. Every turn is a leg on one continuous
 * reckoning rail, and the rail is the first column of the grid each leg is
 * laid out on rather than a line drawn beside a list (see TrackRow). State is
 * carried in the mark's FORM before its hue — solid for a confirmed fix,
 * hollow and dashed while reckoning forward, struck on refusal — so the track
 * survives greyscale and a colourblind reader, which WCAG 1.4.1 requires and
 * PRODUCT.md commits to.
 *
 * Type is Atkinson Hyperlegible throughout, with JetBrains Mono reserved for
 * things that are actually measurements. Colour is rationed to three signal
 * inks and never used decoratively.
 *
 * Everything the UI shows about a turn comes from that turn's own events. The
 * word "global" appears nowhere near status on purpose. */


export default function App() {
  const [state, setState] = useState<ConversationState>(emptyState());
  const [conversations, setConversations] = useState<any[]>([]);
  const [draft, setDraft] = useState('');
  const [health, setHealth] = useState<any>(null);
  const [attachments, setAttachments] = useState<{ id: string; name: string; status: string }[]>([]);
  const fileRef = useRef<HTMLInputElement>(null);
  // Separate from `railOpen`: below xl the rail is a drawer, and a drawer that
  // remembered "open" from a wide session would cover the transcript on load.
  const [narrowRailOpen, setNarrowRailOpen] = useState(false);
  const [railOpen, setRailOpen] = useState(() => {
    try { return localStorage.getItem('primnox2.rail') !== 'hidden'; } catch { return true; }
  });

  const [viewing, setViewing] = useState<{ id: string; name: string } | null>(null);
  const openAsset = useCallback<OpenAsset>(a => setViewing(a), []);

  /* The open document, if any. A workspace id, never the document itself: the
     canvas re-reads it so a revert or a new version shows without the shell
     having to hold a stale copy. */
  const [canvasId, setCanvasId] = useState<string | null>(() => {
    /* A document is addressable. `?doc=<id>` opens straight to it, so a
       position on the track can be handed to someone else, or to yourself
       tomorrow, and land on the same thing. */
    try { return new URLSearchParams(location.search).get('doc'); }
    catch { return null; }
  });
  const openCanvas = useCallback((id: string) => setCanvasId(id), []);

  /* The fix: the leg of each conversation the user has called a known-good
     position. Everything after it is dead reckoning, and the rail says so.

     Kept per conversation and persisted the same way the rail and the folder
     set are, because a fix that forgot itself on reload would be worse than
     no fix at all - you would re-confirm the same position every launch.

     HONEST LIMIT: this lives in localStorage, not in primnox.db. It does not
     reach the event log, does not survive a different machine, and an
     incognito conversation deliberately keeps nothing. Making it durable is a
     turns-table column and a CRS event kind, which is a backend change and
     not this one. */
  const [fixes, setFixes] = useState<Record<string, string>>(() => {
    try { return JSON.parse(localStorage.getItem('primnox2.fixes') || '{}'); }
    catch { return {}; }
  });
  const setFix = useCallback((turnId: string) => {
    setFixes(prev => {
      const cid = stateRef.current.id;
      if (!cid) return prev;
      /* Pressing the current fix again clears it, so the whole track goes
         back to unconfirmed rather than stranding you with a fix you cannot
         undo without picking a different one. */
      const next = { ...prev };
      if (next[cid] === turnId) delete next[cid];
      else next[cid] = turnId;
      try { localStorage.setItem('primnox2.fixes', JSON.stringify(next)); }
      catch { /* private mode */ }
      return next;
    });
  }, []);

  const [folders, setFolders] = useState<any[]>([]);
  // Remembered like the rail is. A folder that re-collapses on every reload
  // makes filing a conversation feel like hiding it.
  const [openFolders, setOpenFolders] = useState<Set<string>>(() => {
    try { return new Set(JSON.parse(localStorage.getItem('primnox2.folders') || '[]')); }
    catch { return new Set(); }
  });
  useEffect(() => {
    try { localStorage.setItem('primnox2.folders', JSON.stringify([...openFolders])); }
    catch { /* private mode */ }
  }, [openFolders]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [menuId, setMenuId] = useState<string | null>(null);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  const [dragOverRecent, setDragOverRecent] = useState(false);
  const [creatingFolder, setCreatingFolder] = useState(false);
  const [editingFolderId, setEditingFolderId] = useState<string | null>(null);
  const [confirmDeleteFolder, setConfirmDeleteFolder] = useState<string | null>(null);
  /* One section, not three booleans. Three independent flags could all be true
     at once — and did, stacking Settings over Memory over the graph, each with
     its own close button and no way to tell what was underneath. */
  const [section, setSection] = useState<Section>('chat');
  /* Whether the conversation list is showing, at every width — a drawer below
     `md`, an inline column above it. Remembered like the context panel's own
     `primnox2.rail`, so a collapsed sidebar stays collapsed across restarts
     instead of springing back every launch.
     Defaults to shown: someone who has never touched it should find the list. */
  const [chatsOpen, setChatsOpen] = useState(() => {
    try { return localStorage.getItem('primnox2.chats') !== 'hidden'; }
    catch { return true; }                                    // private mode
  });
  const setChats = useCallback((next: boolean) => {
    setChatsOpen(next);
    try { localStorage.setItem('primnox2.chats', next ? 'shown' : 'hidden'); }
    catch { /* private mode */ }
  }, []);
  const [chatGraph, setChatGraph] = useState<string | null>(null);

  const stateRef = useRef(state);
  stateRef.current = state;
  const wasConnectedRef = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<CrsSocket | null>(null);

  // Both of these exist because React state updates are asynchronous. A second
  // Enter arriving in the same tick still sees the pre-update `draft`, so a
  // guard written against state cannot stop a double submit — measured at five
  // identical sends within 1.4ms. Refs update synchronously, so they can.
  const sendingRef = useRef(false);
  const draftRef = useRef('');
  draftRef.current = draft;

  const apply = useCallback((e: CrsEvent) => setState(s => reduce(s, e)), []);

  const openConversation = useCallback(async (id: string) => {
    // §3.3.3 — a state read. Opening a conversation never replays events.
    const { turns, head, incognito, gone } = await api.history(id);
    setState(s => ({
      ...s, id, turns: turnsFromHistory(turns), cursor: Math.max(s.cursor, head),
      incognito: !!incognito, gone: !!gone,
    }));
    socketRef.current?.resubscribe();
  }, []);

  const refreshList = useCallback(async () => {
    const { conversations, folders } = await api.listConversations();
    setConversations(conversations);
    setFolders(folders ?? []);
    return conversations;
  }, []);

  useEffect(() => {
    const socket = new CrsSocket({
      onEvent: apply,
      onStatus: ({ connected, synced }) => {
        setState(s => ({ ...s, connected, synced }));
        // Reconnecting into an incognito conversation has to re-read it
        // (§11.2.3). Every other conversation recovers through replay, but an
        // incognito one has nothing to replay — its events never entered the
        // log — so if the backend restarted while we were away, this screen
        // is showing a transcript that no longer exists anywhere.
        const open = stateRef.current;
        if (connected && !wasConnectedRef.current && open.incognito && open.id) {
          openConversation(open.id);
        }
        wasConnectedRef.current = connected;
      },
      getCursor: () => stateRef.current.cursor,
      getConversations: () => (stateRef.current.id ? [stateRef.current.id] : []),
      onResyncRequired: () => { const id = stateRef.current.id; if (id) openConversation(id); },
    });
    socketRef.current = socket;
    socket.connect();

    api.health().then(setHealth).catch(() => setHealth(null));

    (async () => {
      const list = await refreshList();
      if (list.length) await openConversation(list[0].id);
      else { const c = await api.createConversation(); await refreshList(); await openConversation(c.id); }
    })();

    return () => socket.close();
  }, [apply, openConversation, refreshList]);

  // Follow the stream only while parked at the bottom — reading back through a
  // reply must not be yanked away by the next token flush.
  //
  // Opening a conversation is the exception: it lands on the newest message,
  // not the oldest. The "am I near the bottom" guard below is false on a fresh
  // load (scrollTop is 0 and the transcript is tall), so without the first
  // branch you opened every conversation at its very beginning and had to
  // scroll down past the whole history to see what was just said.
  const scrolledFor = useRef<string | null>(null);
  useEffect(() => {
    const end = endRef.current;
    const scroller = end?.parentElement?.parentElement;
    if (!end || !scroller) return;

    if (scrolledFor.current !== state.id) {
      if (state.turns.length === 0) return;          // wait for content to land
      scrolledFor.current = state.id;
      scroller.scrollTop = scroller.scrollHeight;    // instant — a smooth scroll
      return;                                        // through 100 turns is an
    }                                                // animation nobody asked for

    if (scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight > 120) return;
    end.scrollIntoView({ behavior: 'smooth' });
  }, [state.turns, state.id]);

  const liveTurn = useMemo(
    () => [...state.turns].reverse().find(t => !TERMINAL.includes(t.status)),
    [state.turns],
  );

  const send = async () => {
    if (sendingRef.current) return;          // a send is already in flight
    const text = draftRef.current.trim();
    if (!text || !state.id || state.gone) return;

    // Claim the send and clear the draft synchronously, before any await, so
    // the next keystroke in this same tick sees an empty composer and bails.
    sendingRef.current = true;
    draftRef.current = '';
    const ids = attachments.map(a => a.id);
    setDraft('');
    setAttachments([]);
    try {
      await api.send(state.id, text, ids);
      refreshList();
    } catch {
      setDraft(text);                        // a failed send gives the words back
      draftRef.current = text;
      setAttachments(a => a.length ? a : attachments);
    } finally {
      sendingRef.current = false;
    }
  };

  /* Upload returns as soon as the bytes are hashed; extraction runs as a job,
     so attaching a large PDF never blocks the composer (ARCH §2.5). */
  const attach = async (files: FileList | null) => {
    if (!files?.length || !state.id) return;
    for (const file of Array.from(files)) {
      try {
        const asset = await api.upload(file, state.id);
        setAttachments(a => [...a, {
          id: asset.id, name: asset.original_name ?? file.name, status: asset.status,
        }]);
      } catch {
        setAttachments(a => [...a, { id: `failed-${file.name}`, name: file.name, status: 'failed' }]);
      }
    }
    if (fileRef.current) fileRef.current.value = '';
  };

  const newChat = async (incognito = false) => {
    const c = await api.createConversation(incognito ? 'Incognito' : 'New Chat', incognito);
    await refreshList();
    setState(s => ({ ...s, id: c.id, turns: [], incognito, gone: false }));
    socketRef.current?.resubscribe();
  };

  /* Ending one is the whole point of having one, so it is a button and not a
     thing you have to know to quit the app for. */
  const closeIncognito = async () => {
    const id = state.id;
    if (!id) return;
    await api.closeConversation(id).catch(() => undefined);
    const list = await refreshList();
    const next = list.find((c: any) => c.id !== id);
    if (next) await openConversation(next.id);
    else await newChat();
  };

  /* ── Chat management ─────────────────────────────────────────────────── */
  const pinned = useMemo(() => conversations.filter(c => c.pinned_at), [conversations]);
  const unpinned = useMemo(() => conversations.filter(c => !c.pinned_at), [conversations]);
  const loose = useMemo(() => unpinned.filter(c => !c.folder_id), [unpinned]);

  /* Searching the list, client-side. The conversations are already in memory,
     so this needs no endpoint — and it is not optional at any real size: every
     row in an untitled list reads "New Chat", and folders plus day groups only
     help once you already know roughly where a chat is. */
  const [chatQuery, setChatQuery] = useState('');
  const matches = useMemo(() => {
    const q = chatQuery.trim().toLowerCase();
    if (!q) return null;                       // null = not searching
    return conversations.filter(c => (c.title ?? '').toLowerCase().includes(q));
  }, [chatQuery, conversations]);

  const toggleFolder = (id: string) => setOpenFolders(s => {
    const next = new Set(s);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const chatActions: ChatActions = {
    activeId: state.id, folders, editingId, menuId,
    draggingId, setDragging: setDraggingId,
    open: openConversation,
    setMenu: setMenuId,
    beginRename: id => { setMenuId(null); setEditingId(id); },
    commitRename: async (id, title) => {
      setEditingId(null);
      const current = conversations.find(c => c.id === id);
      if (!title.trim() || title === current?.title) return;
      await api.updateConversation(id, { title }).catch(() => undefined);
      refreshList();
    },
    togglePin: async c => {
      setMenuId(null);
      await api.updateConversation(c.id, { pinned: !c.pinned_at }).catch(() => undefined);
      refreshList();
    },
    move: async (id, folderId) => {
      setMenuId(null);
      await api.updateConversation(id, { folder_id: folderId }).catch(() => undefined);
      if (folderId) setOpenFolders(s => new Set(s).add(folderId));
      refreshList();
    },
    archive: async id => {
      setMenuId(null);
      await api.updateConversation(id, { archived: true }).catch(() => undefined);
      await afterRemoved(id);
    },
    // Permanent, so it asks — but not with window.confirm(): the same dialog
    // that silently swallowed folder deletion (see the note by
    // confirmDeleteFolder) swallows this one too. ChatRow asks inline, with a
    // second click on the menu item, before this ever runs.
    remove: async c => {
      setMenuId(null);
      await api.closeConversation(c.id).catch(() => undefined);
      await afterRemoved(c.id);
    },
  };

  /* Whatever just left the list, do not keep showing it. */
  async function afterRemoved(id: string) {
    const list = await refreshList();
    if (state.id !== id) return;
    const next = list.find((c: any) => c.id !== id);
    if (next) await openConversation(next.id);
    else await newChat();
  }

  // Folders used window.prompt() / window.confirm(). Chrome refuses both inside
  // a cross-origin iframe and several embedded webviews drop them entirely —
  // they return null with no error, so clicking "new folder" did nothing at
  // all, and there was nothing on screen to say why. Chat rename already used
  // an inline input and worked; folders now do the same.
  const createFolder = async (name: string) => {
    setCreatingFolder(false);
    if (!name.trim()) return;
    const folder = await api.createFolder(name.trim()).catch(() => null);
    if (folder) setOpenFolders(s => new Set(s).add(folder.id));
    refreshList();
  };

  const commitFolderRename = async (f: any, name: string) => {
    setEditingFolderId(null);
    if (!name.trim() || name.trim() === f.name) return;
    await api.renameFolder(f.id, name.trim()).catch(() => undefined);
    refreshList();
  };

  const removeFolder = async (f: any) => {
    setConfirmDeleteFolder(null);
    await api.deleteFolder(f.id).catch(() => undefined);
    refreshList();
  };

  const toggleRail = () => setRailOpen(o => {
    const next = !o;
    try { localStorage.setItem('primnox2.rail', next ? 'shown' : 'hidden'); } catch { /* private mode */ }
    return next;
  });

  return (
    <CanvasContext.Provider value={openCanvas}>
    <ViewerContext.Provider value={openAsset}>
    <ChatsContext.Provider value={chatActions}>
    {viewing && <AssetViewer key={viewing.id} asset={viewing}
      onClose={() => setViewing(null)} />}
    {/* Still an overlay, unlike the corpus-wide graph. This one is a transient
        look at ONE conversation from inside that conversation — leaving the
        chat to see what the chat established would lose the thing being
        looked at. */}
    {chatGraph && <GraphPanel key={chatGraph} initialScope={`conv:${chatGraph}`}
      title="This conversation" onClose={() => setChatGraph(null)} />}
    {/* `overflow-clip`, not `overflow-hidden`.
        `hidden` makes this a scroll container, and focusing anything inside a
        scroll container makes the browser scroll it into view — but with no
        scrollbar there is no way back. Measured: tabbing to the theme button at
        the foot of the rail left the shell at scrollTop 50, shifting the entire
        app up and hiding the sidebar header, permanently, for the rest of the
        session. `clip` clips identically without ever becoming scrollable. */}
    {/* A column, because the frameless Tauri window needs chrome above the
        app. `decorations: false` in tauri.conf.json removes the OS title bar
        and Tauri puts nothing back, so without this the packaged window
        cannot be moved, minimised or closed. See TitleBar. */}
    <div className="flex flex-col h-screen w-full bg-surface text-on-surface font-sans overflow-clip">
      <TitleBar />

      {/* `min-h-0` is load-bearing: a flex child defaults to min-height:auto,
          which refuses to shrink below its content, so the row would grow past
          the viewport and push the scrollable panes off the bottom instead of
          scrolling inside them. */}
      <div className="flex flex-1 min-h-0 w-full overflow-clip">

      <AppRail
        section={section}
        onSection={s => {
          // Chats while already in Chats toggles the list. This is the only way
          // back once it is collapsed, and it works because the rail is pinned
          // and cannot scroll out of reach — the failure V1 documented.
          if (s === 'chat' && section === 'chat') setChats(!chatsOpen);
          else { setSection(s); if (s === 'chat') setChats(true); }
        }}
        connected={state.connected} synced={state.synced} />

      {/* ── Conversations ─────────────────────────────────────────────── */}
      {section === 'chat' && (
      <ContextSidebar title="Conversations"
        open={chatsOpen} onClose={() => setChats(false)}
        actions={
        <button onClick={() => setCreatingFolder(true)} title="New folder"
          aria-label="New folder"
          className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface/85 hover:bg-on-surface/[0.05] transition duration-150">
          <FolderPlus size={13} />
        </button>
      }>
        {/* The two things that ADD to this list, at the top of the list they
            add to. They were in the rail, which is for destinations. */}
        <div className="sticky top-0 z-10 bg-[var(--nav-bg)] px-3 pt-3 pb-2 space-y-2">
          <div className="flex items-center gap-2">
            <button onClick={() => newChat(false)}
              className="px-interactive group/n flex-1 flex items-center justify-between
                         rounded-lg border border-on-surface/[0.10] px-3 py-2 text-[13px]
                         hover:border-on-surface/25 hover:bg-on-surface/[0.03]">
              New chat
              <Plus size={14} aria-hidden="true"
                className="opacity-60 transition-transform duration-200 group-hover/n:rotate-90" />
            </button>
            <button onClick={() => newChat(true)}
              aria-label="New incognito chat"
              title="Nothing is written to disk. It ends when Primnox closes."
              className="px-interactive shrink-0 rounded-lg border border-dashed
                         border-on-surface/[0.16] p-2 text-on-surface/60
                         hover:border-on-surface/30 hover:text-on-surface">
              <EyeOff size={14} aria-hidden="true" />
            </button>
          </div>

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
          {/* While searching, one flat list of hits. Folders and day groups are
              navigation aids for browsing; during a search they scatter three
              matches across three headings and hide how many there are. */}
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

          {creatingFolder && (
            <input autoFocus placeholder="Folder name"
              aria-label="New folder name"
              onKeyDown={e => {
                if (e.key === 'Enter') createFolder((e.target as HTMLInputElement).value);
                if (e.key === 'Escape') setCreatingFolder(false);
              }}
              onBlur={e => createFolder(e.target.value)}
              className="w-full mb-1 px-3 py-2 rounded-lg bg-on-surface/[0.07] border border-primary/40
                         text-[12px] placeholder-on-surface/30 outline-none" />
          )}

          {folders.map(f => {
            const inside = unpinned.filter(c => c.folder_id === f.id);
            const open = openFolders.has(f.id);

            if (editingFolderId === f.id) {
              return (
                <input key={f.id} autoFocus defaultValue={f.name}
                  aria-label={`Rename folder ${f.name}`}
                  onKeyDown={e => {
                    if (e.key === 'Enter') commitFolderRename(f, (e.target as HTMLInputElement).value);
                    if (e.key === 'Escape') setEditingFolderId(null);
                  }}
                  onBlur={e => commitFolderRename(f, e.target.value)}
                  className="w-full mb-1 px-3 py-2 rounded-lg bg-on-surface/[0.07] border border-primary/40
                             text-[12px] outline-none" />
              );
            }

            return (
              <div key={f.id} className="mb-1">
                <div
                  className={`group/f flex items-center gap-1 pr-1 rounded-lg transition-colors duration-150
                    ${dragOverFolder === f.id ? 'bg-primary/[0.12] ring-1 ring-primary/40' : ''}`}
                  onDragOver={e => {
                    if (!draggingId) return;
                    e.preventDefault();                       // without this the
                    e.dataTransfer.dropEffect = 'move';       // drop never fires
                    setDragOverFolder(f.id);
                  }}
                  onDragLeave={e => {
                    // Only clear when the pointer actually leaves the row, not
                    // when it crosses onto a child element inside it.
                    if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOverFolder(null);
                  }}
                  onDrop={e => {
                    e.preventDefault();
                    const id = e.dataTransfer.getData('text/plain') || draggingId;
                    setDragOverFolder(null);
                    setDraggingId(null);
                    if (!id) return;
                    setOpenFolders(s => new Set(s).add(f.id));  // show where it landed
                    chatActions.move(id, f.id);
                  }}>
                  <button onClick={() => toggleFolder(f.id)}
                    aria-expanded={open}
                    className="flex-1 min-w-0 text-left px-3 py-1.5 rounded-lg flex items-center gap-2 text-[12px] text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03] transition duration-150">
                    <ChevronRight size={11}
                      className={`shrink-0 opacity-60 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
                    <Folder size={12} className="shrink-0 opacity-60" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="font-mono text-[9px] text-on-surface/50 tabular-nums">{inside.length}</span>
                  </button>

                  {/* Two-step delete, in place. `window.confirm` is blocked in
                      the same contexts `window.prompt` is, so a confirm dialog
                      nobody can see means either an unconfirmed delete or a
                      dead button. */}
                  {confirmDeleteFolder === f.id ? (
                    <>
                      <span className="px-label text-error/80 whitespace-nowrap">Delete?</span>
                      <button onClick={() => removeFolder(f)} aria-label={`Confirm delete folder ${f.name}`}
                        className="p-1 rounded text-error hover:bg-error/10 transition-colors">
                        <Check size={12} />
                      </button>
                      <button onClick={() => setConfirmDeleteFolder(null)} aria-label="Cancel delete"
                        className="p-1 rounded text-on-surface/50 hover:bg-on-surface/10 transition-colors">
                        <X size={12} />
                      </button>
                    </>
                  ) : (
                    <>
                      <button onClick={() => setEditingFolderId(f.id)} aria-label={`Rename folder ${f.name}`}
                        className="opacity-0 group-hover/f:opacity-60 hover:!opacity-100 p-1 rounded transition-opacity">
                        <Pencil size={11} />
                      </button>
                      <button onClick={() => setConfirmDeleteFolder(f.id)} aria-label={`Delete folder ${f.name}`}
                        className="opacity-0 group-hover/f:opacity-60 hover:!opacity-100 p-1 rounded transition-opacity">
                        <Trash2 size={11} />
                      </button>
                    </>
                  )}
                </div>
                {open && (
                  <div className="pl-3">
                    {inside.map(c => <ChatRow key={c.id} c={c} />)}
                    {inside.length === 0 && (
                      <p className="px-3 py-2 text-[11px] text-on-surface/50">Empty</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Dropping here takes a conversation back out of its folder —
              otherwise a chat could be filed but never unfiled by dragging. */}
          {/* `justify-between` here was holding a "New folder" button on the
              right. That button now lives in the sidebar header, so the flex
              was left distributing a single child across the full width and
              the label no longer aligned with the rows beneath it. */}
          <div
            className={`rounded-lg transition-colors duration-150
              ${dragOverRecent ? 'bg-primary/[0.12] ring-1 ring-primary/40' : ''}`}
            onDragOver={e => {
              if (!draggingId) return;
              e.preventDefault();
              e.dataTransfer.dropEffect = 'move';
              setDragOverRecent(true);
            }}
            onDragLeave={e => {
              if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragOverRecent(false);
            }}
            onDrop={e => {
              e.preventDefault();
              const id = e.dataTransfer.getData('text/plain') || draggingId;
              setDragOverRecent(false);
              setDraggingId(null);
              if (id) chatActions.move(id, null);
            }}>
            {/* No "Recent" label. It sat above TODAY and YESTERDAY saying the
                same thing a third time — three stacked headings for one list.
                The div stays because it is the drop target that takes a chat
                back OUT of a folder; only the redundant caption is gone, and
                the hairline still marks where folders end and chats begin. */}
            <div className="mx-3 mt-2 mb-1 border-t border-on-surface/[0.07]" />
          </div>
          {/* Grouped by day. Seventy rows of identical-looking titles is a
              wall, not a list — the date is the only thing that distinguishes
              "battery pptx" from "battery pdf" at a glance. */}
          {groupByDay(loose).map(([label, rows]) => (
            <div key={label}>
              {label && <p className="px-label px-3 pt-3 pb-1.5 text-on-surface/50">{label}</p>}
              {rows.map(c => <ChatRow key={c.id} c={c} />)}
            </div>
          ))}
          {conversations.length === 0 && <p className="px-3 py-4 text-xs text-on-surface/50">Nothing yet</p>}
          </>
          )}
        </nav>
      </ContextSidebar>
      )}

      {/* ── The section ───────────────────────────────────────────────────
          Knowledge, Memory and Settings render HERE rather than as
          `fixed inset-0` overlays. As overlays they blanked the rail that
          opened them, so the only way out of any of them was a close button —
          and moving between two of them meant closing one first. */}
      {section === 'knowledge' && <GraphPanel embedded />}
      {section === 'memory' && <MemoryPanel embedded />}
      {section === 'settings' && <SettingsPanel embedded />}

      {/* ── Transcript ────────────────────────────────────────────────── */}
      {section === 'chat' && (
      <main className="relative flex-1 flex flex-col min-w-0">
        {/* The ground the glass sits on.
            These three were defined in tailwind.css and used by nothing, which
            is why the composer's backdrop-filter had no visible effect: on
            `tactical` the panel is rgba(10,10,10,0.94) over a #0A0A0A body, so
            blurring it diffused one black into an identical black. Glass only
            reads as glass when there is something behind it worth seeing
            through to.
            Coloured from --primary / --accent / --green, so they follow the
            palette rather than pinning the app to one accent. */}
        <div className="orb orb-1" aria-hidden="true" />
        <div className="orb orb-2" aria-hidden="true" />
        <div className="orb orb-3" aria-hidden="true" />
        <header className="relative z-10 h-14 shrink-0 flex items-center justify-between gap-3 px-8 border-b border-on-surface/[0.07]">
          {/* The way back, where a way back belongs: at the edge the panel
              retracted into, in the header of the thing that took its space.
              The rail's Chats button also restores it, but nothing about an
              icon for the section you are already in says "this reveals the
              list" — that was reachable, not discoverable, which is not the
              same thing. Mirrors the context panel's own show-control on the
              opposite edge, so both sides of the app behave alike. */}
          {!chatsOpen && (
            <button onClick={() => setChats(true)}
              aria-label="Show conversations" aria-expanded={false}
              title="Show conversations"
              className="px-interactive -ml-3 shrink-0 p-1.5 rounded-lg text-on-surface/50
                         hover:text-on-surface hover:bg-on-surface/[0.05]">
              <PanelLeftOpen size={16} aria-hidden="true" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <span className="px-eyebrow block">
              {state.incognito ? 'Incognito · nothing written to disk' : 'Conversation'}
            </span>
            {/* Display type is for hero moments — the empty state, the site.
                A chat title is a label for the thing you are already looking
                at, and setting it at 30px made it the largest element on
                screen, louder than the conversation it names. */}
            <h1 className="font-display font-bold text-[14px] uppercase tracking-[0.02em]
                           text-on-surface/85 truncate flex items-center gap-2 leading-tight">
              {state.incognito && <EyeOff size={13} className="shrink-0 opacity-70" />}
              {conversations.find(c => c.id === state.id)?.title || 'New Chat'}
            </h1>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            {state.incognito && (
              <button onClick={closeIncognito}
                className="px-3 py-1.5 rounded-lg border border-on-surface/[0.12] hover:border-on-surface/25 hover:bg-on-surface/[0.04] transition duration-150 px-label">
                End chat
              </button>
            )}
            {/* This conversation's OWN graph — what it has established, not
                what the codebase contains. Lives in the chat header because it
                is a property of this chat; the sidebar button opens the
                corpus-wide one. Hidden for incognito, whose graph is memory
                only and deliberately has nothing to show from disk. */}
            {state.id && !state.incognito && (
              <button onClick={() => setChatGraph(state.id)}
                aria-label="Graph for this conversation" title="What this conversation has established"
                className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface/85 hover:bg-on-surface/[0.05] transition duration-150">
                <Share2 size={15} />
              </button>
            )}
            <button onClick={() => setNarrowRailOpen(true)} aria-label="Show context panel"
              className="xl:hidden p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface/85 hover:bg-on-surface/[0.05] transition duration-150">
              <PanelRight size={15} />
            </button>
          </div>
        </header>

        {/* z-10 so the orbs stay behind the reading column. They are positioned
            with z-index 0, which paints them ABOVE non-positioned siblings —
            without this the ambient glow washes over the transcript instead of
            sitting under it. The composer still blurs them: backdrop-filter
            captures whatever is painted behind, regardless of z-index. */}
        <div className="relative z-10 flex-1 overflow-y-auto custom-scrollbar
                        [scroll-padding-bottom:12rem]">
          {/* pb-48 clears the composer, which now overlays the foot of this
              scroller rather than sitting below it. Without the padding the
              last reply would end up permanently hidden behind the input, and
              the matching scroll-padding keeps a keyboard-focused element from
              coming to rest under it (WCAG 2.2 Focus Not Obscured). */}
          <div className="mx-auto w-full max-w-[72rem] px-6 pt-8 pb-48">
            {/* §11.2.3 — the loss is stated. An incognito conversation the
                runtime has forgotten would otherwise render as one you simply
                had not spoken in yet, which reads as your words going
                missing rather than as the mode working. */}
            {state.gone && (
              <div className="pt-24 text-center">
                <EyeOff size={20} className="mx-auto mb-4 opacity-40" />
                <h2 className="px-display px-display-sm mb-3">This incognito chat has ended</h2>
                <p className="px-body text-sm">
                  It lived in memory only, so restarting Primnox ended it. Nothing
                  was written down — that was the point.
                </p>
              </div>
            )}

            {!state.gone && state.turns.length === 0 && (
              <div className="pt-24 text-center">
                {state.incognito ? (
                  <>
                    <EyeOff size={20} className="mx-auto mb-4 opacity-40" />
                    <h2 className="px-display px-display-sm mb-3">Off the record</h2>
                    <p className="px-body text-sm">
                      Nothing here is written to disk — no history, no attachments,
                      no running code. It ends when you close it, or when Primnox
                      restarts.
                    </p>
                  </>
                ) : (
                  <>
                    <h2 className="px-display px-display-sm mb-3">Right, what are we doing?</h2>
                    <p className="px-body text-sm">Everything here stays local until you say otherwise.</p>
                  </>
                )}
              </div>
            )}

            {/* The track. Every turn is a leg on one continuous rail, and the
                rail is the grid's first column rather than decoration beside
                it — see TrackRow. This replaces the centred transcript the
                whole category ships. */}
            {(() => {
              /* Resolved once per render rather than per row: the drift of a
                 leg is its distance from the fix, so every row needs to know
                 where the fix IS, not just whether it is the fix. */
              const fixId = state.id ? fixes[state.id] : undefined;
              const fixIndex = fixId ? state.turns.findIndex(t => t.id === fixId) : -1;
              return state.turns.map((turn, i) => (
                <TrackRow key={turn.id} turn={turn} index={i}
                  isFix={i === fixIndex}
                  drift={fixIndex === -1 ? i + 1 : Math.max(0, i - fixIndex)}
                  onFix={setFix}>
                  <TurnBlock turn={turn} />
                </TrackRow>
              ));
            })()}
            <div ref={endRef} />
          </div>
        </div>

        {/* Composer.
            Overlays the foot of the transcript rather than sitting beneath it,
            so the conversation passes under the glass and the blur has
            something to diffuse. In normal flow it had only the page behind it,
            which is a tinted rectangle, not glass. */}
        <div className="absolute inset-x-0 bottom-0 z-10 px-8 pb-6 pt-2
                        pointer-events-none [&_*]:pointer-events-auto">
          {/* The scrim.

              Glass diffuses what is behind it; it does not END it. Below the
              panel there was no glass at all — just the raw transcript running
              under the "Enter to send" hint and out the bottom of the window,
              so a reply's last line and the composer's own label overlapped at
              full contrast. Two unrelated sentences crossing each other reads
              as a rendering fault, not as depth.

              So the ground rises behind the composer instead: transparent well
              above it, opaque from the panel's lower edge down. The glass still
              has something to diffuse (the fade is only partial across the
              panel itself), and nothing under it competes with the composer.

              Stops are in px from the bottom rather than percentages. The
              textarea grows to 160px, and percentage stops would drag the
              opaque band up across the panel as it grew — the fade has to stay
              pinned to the panel's lower edge. That edge measures 49px up —
              pb-6 (24) + the hint line (~15) + its mt-2.5 (10) — so the opaque
              plateau runs to 54px rather than exactly 49: the hint's height is
              font-metric dependent and varies between the ten themes, and a
              1px margin here would show as a bright seam in whichever theme
              rounded the other way. */}
          <div aria-hidden="true"
               className="!pointer-events-none absolute inset-x-0 -top-14 bottom-0"
               style={{
                 background:
                   'linear-gradient(to top,'
                   + ' var(--bg) 0px,'
                   + ' var(--bg) 54px,'
                   + ' color-mix(in srgb, var(--bg) 70%, transparent) 90px,'
                   + ' color-mix(in srgb, var(--bg) 22%, transparent) 135px,'
                   + ' transparent 190px)',
               }} />
          {/* `relative` so the panel paints over the scrim. The scrim is
              absolutely positioned and later stacking steps win, so a static
              wrapper here would put the gradient on top of the composer. */}
          <div className="relative mx-auto w-full max-w-[46rem]">
            {/* Glass: the composer sits at the foot of the transcript and the
                conversation scrolls behind it, so diffusing what is behind
                rather than blanking it keeps the two connected. */}
            <Panel variant="glass"
              className="focus-within:border-on-surface/25 px-interactive">
              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-3.5 pt-3">
                  {attachments.map(a => (
                    <span key={a.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/[0.12] text-[11px] text-on-surface/65">
                      <FileText size={11} className="opacity-60" />
                      {a.name}
                      {a.status === 'ingesting' && <Loader2 size={9} className="px-spin opacity-60" />}
                      {a.status === 'failed' && <AlertTriangle size={9} className="text-error" />}
                      <button onClick={() => setAttachments(list => list.filter(x => x.id !== a.id))}
                        aria-label={`Remove ${a.name}`}
                        className="opacity-40 hover:opacity-100 transition-opacity">
                        <X size={10} />
                      </button>
                    </span>
                  ))}
                </div>
              )}
              {/* The composer names itself only in a placeholder that vanishes
                  on the first keystroke, so the label carries the name for
                  everyone who is not reading grey hint text. */}
              <label htmlFor="composer" className="sr-only">Message Primnox</label>
              <textarea
                id="composer"
                value={draft}
                disabled={state.gone}
                onChange={e => {
                  setDraft(e.target.value);
                  e.target.style.height = 'auto';
                  e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px';
                }}
                onKeyDown={e => {
                  // isComposing: while composing Japanese, Chinese or Korean
                  // text Enter confirms the candidate word, and without this
                  // guard it would also fire a half-written message.
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    send();
                  }
                }}
                rows={1}
                placeholder={state.gone
                  ? 'This conversation has ended — start a new one'
                  : 'Message Primnox…'}
                className="w-full bg-transparent text-on-surface/90 placeholder-on-surface/25 text-sm resize-none leading-6 min-h-[24px] max-h-[160px] px-4 pt-3.5 pb-1 outline-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
              />
              <div className="flex items-center gap-1.5 px-2.5 pb-2.5">
                <input ref={fileRef} type="file" multiple className="hidden"
                  onChange={e => attach(e.target.files)} />
                {/* Disabled rather than hidden, and it says why. A control
                    that quietly vanishes reads as a bug; the server refuses
                    these uploads either way (§11.2.4). */}
                <button onClick={() => fileRef.current?.click()}
                  aria-label="Attach a file"
                  disabled={state.incognito}
                  title={state.incognito
                    ? 'Attachments are stored on disk, so they are unavailable in an incognito chat'
                    : undefined}
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.06] transition duration-150 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-on-surface/50 disabled:cursor-not-allowed">
                  <Paperclip size={15} />
                </button>
                <span className="px-label px-1">
                  {state.incognito
                    ? 'incognito · no history, no files, no code'
                    : health?.model
                      ? `${health.model.model} · ${health.model.local ? 'local' : 'cloud'}`
                      : 'connecting…'}
                </span>
                <div className="flex-1" />
                {/* Stop and Send coexist. Turns are independent objects, so a
                    new message while one is still running is legitimate — and
                    Enter already did exactly that. Replacing Send with Stop
                    told the user they could not send while the keyboard
                    happily sent anyway; showing both makes the UI honest about
                    what the runtime actually supports. */}
                {liveTurn && (
                  <button onClick={() => api.cancel(liveTurn.id)}
                    aria-label="Stop generating"
                    className="w-8 h-8 rounded-lg flex items-center justify-center bg-on-surface/[0.09] hover:bg-on-surface/[0.14] transition duration-150">
                    <Square size={13} className="fill-current" />
                  </button>
                )}
                <button onClick={send} disabled={!draft.trim() || state.gone}
                  aria-label="Send message"
                  className="w-8 h-8 rounded-lg flex items-center justify-center transition duration-150
                    disabled:bg-on-surface/5 disabled:text-on-surface/50 disabled:cursor-not-allowed
                    enabled:bg-primary enabled:text-surface enabled:hover:opacity-80 enabled:active:scale-95">
                  <ArrowUp size={16} strokeWidth={2.5} />
                </button>
              </div>
            </Panel>
            <p className="px-label mt-2.5 text-center normal-case tracking-[0.1em]">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </main>
      )}

      {/* ── Context rail ──────────────────────────────────────────────────
          Inline above 1280px, an overlay drawer below it. Previously the rail
          and its toggle were both `hidden xl:*`, so on a 1000px window the
          panel did not exist and there was no control to summon it — the file
          list, the sandbox status and the stream cursor were simply
          unreachable at the width most people actually run this at. */}
      {/* The canvas. Beside the track, never over it: the leg that produced a
          document stays readable while you read the document, which is the
          whole premise of a track you can retrace. It takes the panel slot
          rather than opening a second one, because two stacked side panels at
          this width would leave the plate below its reading measure. */}
      <AnimatePresence initial={false}>
        {/* The track gives up its space immediately; the panel slides into the
            space that opened. Animating the container's WIDTH instead made
            every frame a layout+paint+composite on the widest element on
            screen, which is what the performance rule exists to stop. The
            inner panel carries a transform, which the compositor owns. */}
        {canvasId && section === 'chat' && (
          <motion.div key="canvas"
            initial={{ width: 0 }}
            animate={{ width: 420, transition: { duration: 0 } }}
            /* The width snaps, but only AFTER the panel has slid out.
               AnimatePresence keeps a child mounted until the child it
               TRACKS finishes exiting, and that is this wrapper - so a
               zero-length exit here unmounted the subtree instantly and
               the inner slide never rendered. Delaying the collapse by
               the slide's own duration makes the wrapper outlive it. */
            exit={{ width: 0, transition: { delay: 0.25, duration: 0 } }}
            className="hidden shrink-0 overflow-hidden lg:block">
            <motion.div
              initial={{ opacity: 0, transform: 'translate3d(100%,0,0)' }}
              animate={{ opacity: 1, transform: 'translate3d(0,0,0)' }}
              exit={{ opacity: 0, transform: 'translate3d(100%,0,0)' }}
              transition={{ duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
              className="h-full w-[420px]">
              <Canvas key={canvasId} id={canvasId} onClose={() => setCanvasId(null)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence initial={false}>
        {railOpen && section === 'chat' && !canvasId && (
          <motion.div key="rail"
            initial={{ width: 0 }}
            animate={{ width: 288, transition: { duration: 0 } }}
            /* The width snaps, but only AFTER the panel has slid out.
               AnimatePresence keeps a child mounted until the child it
               TRACKS finishes exiting, and that is this wrapper - so a
               zero-length exit here unmounted the subtree instantly and
               the inner slide never rendered. Delaying the collapse by
               the slide's own duration makes the wrapper outlive it. */
            exit={{ width: 0, transition: { delay: 0.25, duration: 0 } }}
            className="shrink-0 overflow-hidden hidden xl:block">
            <motion.div
              initial={{ opacity: 0, transform: 'translate3d(100%,0,0)' }}
              animate={{ opacity: 1, transform: 'translate3d(0,0,0)' }}
              exit={{ opacity: 0, transform: 'translate3d(100%,0,0)' }}
              transition={{ duration: 0.25, ease: [0.32, 0.72, 0, 1] }}
              className="h-full w-[288px]">
              <ContextRail state={state} liveTurn={liveTurn} health={health} onClose={toggleRail} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      {!railOpen && section === 'chat' && (
        <button onClick={toggleRail} aria-label="Show context panel"
          className="shrink-0 w-10 border-l border-on-surface/[0.07] bg-[var(--nav-bg)] hidden xl:flex items-start justify-center pt-4 text-on-surface/50 hover:text-on-surface transition duration-150">
          <PanelRight size={15} />
        </button>
      )}

      <AnimatePresence>
        {narrowRailOpen && section === 'chat' && (
          <motion.div key="rail-overlay" className="xl:hidden fixed inset-0 z-40 flex justify-end"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}>
            <div className="absolute inset-0 bg-black/50" onClick={() => setNarrowRailOpen(false)} />
            <motion.div className="relative z-10 h-full"
              initial={{ transform: 'translate3d(300px,0,0)' }}
              animate={{ transform: 'translate3d(0,0,0)' }}
              exit={{ transform: 'translate3d(300px,0,0)' }}
              transition={{ duration: 0.25, ease: [0.32, 0.72, 0, 1] }}>
              <ContextRail state={state} liveTurn={liveTurn} health={health}
                onClose={() => setNarrowRailOpen(false)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
      </div>
    </div>
    </ChatsContext.Provider>
    </ViewerContext.Provider>
    </CanvasContext.Provider>
  );
}

/* The model's plan, shown as reasoning rather than scraped out of prose. */
