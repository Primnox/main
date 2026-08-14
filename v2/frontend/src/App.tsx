import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'motion/react';
import {
  ArrowUp, Square, Plus, MessageSquare, AlertTriangle, RotateCw,
  Circle, Check, Loader2, Ban, PanelRight, Cpu, Terminal, ShieldCheck,
  Paperclip, FileText, Package, Lightbulb, ShieldAlert, X, ChevronRight, Download,
  EyeOff, Eye, Pin, Folder, FolderPlus, Pencil, Trash2, Archive, MoreHorizontal,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  API, CrsSocket, api, emptyState, reduce, turnsFromHistory,
  TERMINAL, type ConversationState, type CrsEvent, type Execution,
  type PermissionRequest, type Turn, type ToolCall,
} from './lib/crs';

/* Primnox V2 shell.
 *
 * Layout is Claude's: nav rail, conversation list, transcript on a reading
 * measure, context panel on the right. Visual language is Primnox's own
 * (design-system/primnox/MASTER.md): Syne display, DM Sans body, 10px
 * uppercase JetBrains Mono labels, hairline rules and negative space rather
 * than cards and shadows, --color-* tokens only.
 *
 * Everything the UI shows about a turn comes from that turn's own events. The
 * word "global" appears nowhere near status on purpose. */

const MD: any = {
  p:  ({ children }: any) => <p className="mb-3 last:mb-0 leading-7 text-on-surface/85">{children}</p>,
  ul: ({ children }: any) => <ul className="mb-3 space-y-1 pl-5 list-disc text-on-surface/85">{children}</ul>,
  ol: ({ children }: any) => <ol className="mb-3 space-y-1 pl-5 list-decimal text-on-surface/85">{children}</ol>,
  code: ({ children, className }: any) =>
    className ? (
      <pre className="my-3 p-4 rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-x-auto">
        <code className="font-mono text-[0.78rem] leading-relaxed">{children}</code>
      </pre>
    ) : (
      <code className="bg-on-surface/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono">{children}</code>
    ),
  a: ({ href, children }: any) => <a href={href} className="text-primary underline underline-offset-2">{children}</a>,
};

// Plain words for each state. "Thinking" and "Writing" are separate on purpose:
// waiting on a slow provider and receiving a slow reply look identical under a
// single spinner, and telling them apart is most of what a status is for.
const STATUS_COPY: Record<string, string> = {
  queued: 'Queued',
  building_context: 'Gathering context',
  thinking: 'Thinking',
  streaming: 'Writing',
  tool_running: 'Running a tool',
  awaiting_input: 'Waiting for you',
};

/* Opening a file is available wherever a file is mentioned — inside an
   execution, on a turn, in the rail — and those are three different depths of
   the tree. A context beats threading a callback through every one of them. */
type OpenAsset = (asset: { id: string; name: string }) => void;
const ViewerContext = createContext<OpenAsset>(() => {});

/* ChatRow lives outside App on purpose. A component defined inside another is
   a NEW component type on every render, so React remounts it — which throws
   away the focus and caret of the rename field the moment you type. The
   handlers reach it through a context instead. */
type ChatActions = {
  activeId: string | null;
  folders: any[];
  editingId: string | null;
  menuId: string | null;
  draggingId: string | null;
  setDragging: (id: string | null) => void;
  open: (id: string) => void;
  setMenu: (id: string | null) => void;
  beginRename: (id: string) => void;
  commitRename: (id: string, title: string) => void;
  togglePin: (c: any) => void;
  move: (id: string, folderId: string | null) => void;
  archive: (id: string) => void;
  remove: (c: any) => void;
};
const ChatsContext = createContext<ChatActions | null>(null);

/* The row menu is rendered into <body>, not beside the row.
   The conversation list is `overflow-y-auto`, and an absolutely positioned
   child of a scroll container is clipped by it: measured on a row near the
   bottom, the menu overflowed the list by 124px and everything past
   "Archive" — including "Delete permanently" — was simply cut off. A portal
   escapes the clip; fixed coordinates keep it against its button. */
const MENU_WIDTH = 208;

function RowMenu({ anchor, onClose, children }: {
  anchor: DOMRect; onClose: () => void; children: any;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: anchor.bottom + 4, left: anchor.right - MENU_WIDTH });

  useEffect(() => {
    // Measured after render rather than guessed: the menu's height changes
    // with how many folders exist, so a constant would be wrong the moment
    // someone adds one.
    const height = ref.current?.offsetHeight ?? 0;
    const room = window.innerHeight - anchor.bottom - 8;
    setPos({
      top: height > room ? Math.max(8, anchor.top - height - 4) : anchor.bottom + 4,
      left: Math.max(8, Math.min(anchor.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8)),
    });
  }, [anchor]);

  useEffect(() => {
    // Fixed to the viewport, so a scroll would leave it stranded mid-air.
    const close = () => onClose();
    window.addEventListener('scroll', close, true);
    window.addEventListener('resize', close);
    return () => {
      window.removeEventListener('scroll', close, true);
      window.removeEventListener('resize', close);
    };
  }, [onClose]);

  return createPortal(
    <>
      <div className="fixed inset-0 z-[60]" onClick={onClose} />
      <div ref={ref} role="menu"
        style={{ top: pos.top, left: pos.left, width: MENU_WIDTH }}
        className="fixed z-[61] py-1 rounded-xl border border-on-surface/[0.12] bg-surface shadow-2xl">
        {children}
      </div>
    </>,
    document.body,
  );
}

function ChatRow({ c }: { c: any }) {
  const a = useContext(ChatsContext)!;
  const active = c.id === a.activeId;
  const editing = a.editingId === c.id;
  const menuBtn = useRef<HTMLButtonElement>(null);
  const [anchor, setAnchor] = useState<DOMRect | null>(null);

  if (editing) {
    return (
      <input autoFocus defaultValue={c.title}
        aria-label={`Rename ${c.title}`}
        onKeyDown={e => {
          if (e.key === 'Enter') a.commitRename(c.id, (e.target as HTMLInputElement).value);
          if (e.key === 'Escape') a.commitRename(c.id, c.title);
        }}
        onBlur={e => a.commitRename(c.id, e.target.value)}
        className="w-full px-3 py-2 rounded-lg bg-on-surface/[0.07] border border-primary/40 text-[13px] outline-none" />
    );
  }

  const openMenuAt = (x: number, y: number) => {
    // A zero-size rect at the cursor. RowMenu positions against a rect, so the
    // pointer becomes the anchor and the menu opens where the click happened
    // rather than beside a button the user never touched.
    setAnchor(new DOMRect(x, y, 0, 0));
    a.setMenu(c.id);
  };

  return (
    <div
      className={`relative group/c flex items-center rounded-lg transition-opacity duration-150
                  ${a.draggingId === c.id ? 'opacity-40' : ''}`}
      // Incognito conversations are never written to disk, so they have no
      // folder to be moved into — dragging one would promise a placement that
      // cannot survive the session.
      draggable={!c.incognito}
      onDragStart={e => {
        e.dataTransfer.effectAllowed = 'move';
        e.dataTransfer.setData('text/plain', c.id);
        a.setDragging(c.id);
      }}
      onDragEnd={() => a.setDragging(null)}
      onContextMenu={e => { e.preventDefault(); openMenuAt(e.clientX, e.clientY); }}>
      <button onClick={() => a.open(c.id)}
        aria-current={active ? 'page' : undefined}
        className={`flex-1 min-w-0 text-left px-3 py-2.5 rounded-lg flex items-center gap-2.5 transition-all duration-200 text-[13px]
          ${active ? 'bg-on-surface/[0.07] text-on-surface' : 'text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03]'}`}>
        {c.incognito
          ? <EyeOff size={13} className="shrink-0 opacity-60" />
          : c.pinned_at
            ? <Pin size={12} className="shrink-0 opacity-60" />
            : <MessageSquare size={13} className="shrink-0 opacity-60" />}
        <span className="truncate flex-1">{c.title}</span>
        {c.turn_count > 0 && (
          <span className="font-mono text-[9px] text-on-surface/35 tabular-nums">{c.turn_count}</span>
        )}
      </button>

      <button ref={menuBtn}
        onClick={() => {
          const open = a.menuId === c.id;
          if (open) { setAnchor(null); a.setMenu(null); return; }
          const r = menuBtn.current!.getBoundingClientRect();
          openMenuAt(r.right, r.bottom);
        }}
        aria-label={`Actions for ${c.title}`} aria-expanded={a.menuId === c.id}
        className="absolute right-1 opacity-0 group-hover/c:opacity-60 hover:!opacity-100 focus-visible:opacity-100 p-1 rounded transition-opacity bg-[var(--nav-bg)]">
        <MoreHorizontal size={13} />
      </button>

      {a.menuId === c.id && anchor && (
        <RowMenu anchor={anchor} onClose={() => { setAnchor(null); a.setMenu(null); }}>
            <MenuItem icon={<Pencil size={12} />} onClick={() => a.beginRename(c.id)}>Rename</MenuItem>
            {!c.incognito && (
              <MenuItem icon={<Pin size={12} />} onClick={() => a.togglePin(c)}>
                {c.pinned_at ? 'Unpin' : 'Pin'}
              </MenuItem>
            )}
            {!c.incognito && a.folders.length > 0 && (
              <>
                <p className="px-label px-3 pt-2 pb-1">Move to</p>
                {a.folders.map(f => (
                  <MenuItem key={f.id} icon={<Folder size={12} />}
                    onClick={() => a.move(c.id, c.folder_id === f.id ? null : f.id)}>
                    {f.name}{c.folder_id === f.id ? ' ·  remove' : ''}
                  </MenuItem>
                ))}
              </>
            )}
            <div className="my-1 h-px bg-on-surface/[0.08]" />
            {!c.incognito && (
              <MenuItem icon={<Archive size={12} />} onClick={() => a.archive(c.id)}>
                Archive
              </MenuItem>
            )}
            <MenuItem icon={<Trash2 size={12} />} danger onClick={() => a.remove(c)}>
              Delete permanently
            </MenuItem>
        </RowMenu>
      )}
    </div>
  );
}

function MenuItem({ icon, children, onClick, danger }: {
  icon: any; children: any; onClick: () => void; danger?: boolean;
}) {
  return (
    <button role="menuitem" onClick={onClick}
      className={`w-full text-left px-3 py-1.5 flex items-center gap-2 text-[12px] transition-colors duration-150
        ${danger ? 'text-error hover:bg-error/[0.10]' : 'text-on-surface/75 hover:bg-on-surface/[0.06]'}`}>
      {icon}{children}
    </button>
  );
}

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
    remove: async c => {
      setMenuId(null);
      // Permanent, so it asks. Archive is the reversible one and does not.
      if (!window.confirm(
        `Delete "${c.title}" permanently?\n\nIts messages go with it. Files it produced are kept.`)) return;
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
    <ViewerContext.Provider value={openAsset}>
    <ChatsContext.Provider value={chatActions}>
    {viewing && <AssetViewer key={viewing.id} asset={viewing}
      onClose={() => setViewing(null)} />}
    <div className="flex h-screen w-full bg-surface text-on-surface font-sans overflow-hidden">

      {/* ── Conversations ─────────────────────────────────────────────── */}
      <aside className="w-[248px] shrink-0 flex flex-col border-r border-on-surface/[0.07] bg-[var(--nav-bg)]">
        <div className="h-14 flex items-center gap-2.5 px-5 border-b border-on-surface/[0.07]">
          <span className="w-[7px] h-[7px] rounded-full bg-on-surface shrink-0" />
          <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">Primnox</span>
          <span className="px-label ml-auto">v2</span>
        </div>

        <div className="p-3 space-y-2">
          <button onClick={() => newChat(false)}
            className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border border-on-surface/[0.09] hover:border-on-surface/20 hover:bg-on-surface/[0.03] transition-all duration-200 text-sm group">
            New chat
            <Plus size={15} className="group-hover:rotate-90 transition-transform duration-200" />
          </button>
          <button onClick={() => newChat(true)}
            title="Nothing is written to disk. It ends when Primnox closes."
            className="w-full flex items-center justify-between px-3.5 py-2 rounded-xl border border-dashed border-on-surface/[0.14] hover:border-on-surface/25 hover:bg-on-surface/[0.03] transition-all duration-200 text-[13px] text-on-surface/60 hover:text-on-surface/85">
            Incognito chat
            <EyeOff size={14} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-2 pb-3">
          {pinned.length > 0 && (
            <>
              <p className="px-label px-3 pb-2 flex items-center gap-1.5">
                <Pin size={9} /> Pinned
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
                    className="flex-1 min-w-0 text-left px-3 py-1.5 rounded-lg flex items-center gap-2 text-[12px] text-on-surface/55 hover:text-on-surface/85 hover:bg-on-surface/[0.03] transition-all duration-200">
                    <ChevronRight size={11}
                      className={`shrink-0 opacity-60 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
                    <Folder size={12} className="shrink-0 opacity-60" />
                    <span className="truncate flex-1">{f.name}</span>
                    <span className="font-mono text-[9px] text-on-surface/35 tabular-nums">{inside.length}</span>
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
                      <p className="px-3 py-2 text-[11px] text-on-surface/30">Empty</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}

          {/* Dropping here takes a conversation back out of its folder —
              otherwise a chat could be filed but never unfiled by dragging. */}
          <div
            className={`flex items-center justify-between pr-1 rounded-lg transition-colors duration-150
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
            <p className="px-label px-3 pb-2 pt-2">Recent</p>
            {/* Next to the list it acts on, and above it — at the bottom it sat
                below every conversation, which on a list of seventy is not
                somewhere anyone finds it. */}
            <button onClick={() => setCreatingFolder(true)} title="New folder"
              aria-label="New folder"
              className="p-1.5 rounded-lg text-on-surface/40 hover:text-on-surface/85 hover:bg-on-surface/[0.05] transition-all duration-200">
              <FolderPlus size={13} />
            </button>
          </div>
          {/* Grouped by day. Seventy rows of identical-looking titles is a
              wall, not a list — the date is the only thing that distinguishes
              "battery pptx" from "battery pdf" at a glance. */}
          {groupByDay(loose).map(([label, rows]) => (
            <div key={label}>
              {label && <p className="px-label px-3 pt-3 pb-1.5 text-on-surface/30">{label}</p>}
              {rows.map(c => <ChatRow key={c.id} c={c} />)}
            </div>
          ))}
          {conversations.length === 0 && <p className="px-3 py-4 text-xs text-on-surface/35">Nothing yet</p>}
        </nav>

        <div className="h-9 shrink-0 flex items-center gap-2 px-5 border-t border-on-surface/[0.07]">
          <Circle size={6} className={state.connected ? 'text-primary fill-current' : 'text-error fill-current'} />
          <span className="px-label">{state.connected ? (state.synced ? 'Live' : 'Syncing') : 'Offline'}</span>
        </div>
      </aside>

      {/* ── Transcript ────────────────────────────────────────────────── */}
      <main className="flex-1 flex flex-col min-w-0">
        <header className="h-14 shrink-0 flex items-center justify-between px-8 border-b border-on-surface/[0.07]">
          <div className="min-w-0">
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
                className="px-3 py-1.5 rounded-lg border border-on-surface/[0.12] hover:border-on-surface/25 hover:bg-on-surface/[0.04] transition-all duration-200 px-label">
                End chat
              </button>
            )}
            {/* The only way to reach files, sandbox status and the stream
                cursor on a window narrower than 1280px. */}
            <button onClick={() => setNarrowRailOpen(true)} aria-label="Show context panel"
              className="xl:hidden p-1.5 rounded-lg text-on-surface/40 hover:text-on-surface/85 hover:bg-on-surface/[0.05] transition-all duration-200">
              <PanelRight size={15} />
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="mx-auto w-full max-w-[46rem] px-8 py-8">
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

            {state.turns.map(turn => <TurnBlock key={turn.id} turn={turn} />)}
            <div ref={endRef} />
          </div>
        </div>

        {/* Composer */}
        <div className="shrink-0 px-8 pb-6 pt-2">
          <div className="mx-auto w-full max-w-[46rem]">
            <div className="bg-on-surface/[0.035] border border-on-surface/[0.09] rounded-2xl focus-within:border-on-surface/20 transition-colors duration-200">
              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-1.5 px-3.5 pt-3">
                  {attachments.map(a => (
                    <span key={a.id}
                      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/[0.12] text-[11px] text-on-surface/65">
                      <FileText size={11} className="opacity-60" />
                      {a.name}
                      {a.status === 'ingesting' && <Loader2 size={9} className="animate-spin opacity-60" />}
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
              <textarea
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
                  className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface/45 hover:text-on-surface hover:bg-on-surface/[0.06] transition-all duration-200 disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-on-surface/45 disabled:cursor-not-allowed">
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
                    className="w-8 h-8 rounded-lg flex items-center justify-center bg-on-surface/[0.09] hover:bg-on-surface/[0.14] transition-all duration-200">
                    <Square size={13} className="fill-current" />
                  </button>
                )}
                <button onClick={send} disabled={!draft.trim() || state.gone}
                  aria-label="Send message"
                  className="w-8 h-8 rounded-lg flex items-center justify-center transition-all duration-200
                    disabled:bg-on-surface/5 disabled:text-on-surface/40 disabled:cursor-not-allowed
                    enabled:bg-primary enabled:text-surface enabled:hover:opacity-80 enabled:active:scale-95">
                  <ArrowUp size={16} strokeWidth={2.5} />
                </button>
              </div>
            </div>
            <p className="px-label mt-2.5 text-center normal-case tracking-[0.1em]">
              Enter to send · Shift+Enter for new line
            </p>
          </div>
        </div>
      </main>

      {/* ── Context rail ──────────────────────────────────────────────────
          Inline above 1280px, an overlay drawer below it. Previously the rail
          and its toggle were both `hidden xl:*`, so on a 1000px window the
          panel did not exist and there was no control to summon it — the file
          list, the sandbox status and the stream cursor were simply
          unreachable at the width most people actually run this at. */}
      <AnimatePresence initial={false}>
        {railOpen && (
          <motion.div key="rail"
            initial={{ width: 0, opacity: 0 }} animate={{ width: 288, opacity: 1 }} exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
            className="shrink-0 overflow-hidden hidden xl:block">
            <ContextRail state={state} liveTurn={liveTurn} health={health} onClose={toggleRail} />
          </motion.div>
        )}
      </AnimatePresence>
      {!railOpen && (
        <button onClick={toggleRail} aria-label="Show context panel"
          className="shrink-0 w-10 border-l border-on-surface/[0.07] bg-[var(--nav-bg)] hidden xl:flex items-start justify-center pt-4 text-on-surface/40 hover:text-on-surface transition-all duration-200">
          <PanelRight size={15} />
        </button>
      )}

      <AnimatePresence>
        {narrowRailOpen && (
          <motion.div key="rail-overlay" className="xl:hidden fixed inset-0 z-40 flex justify-end"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}>
            <div className="absolute inset-0 bg-black/50" onClick={() => setNarrowRailOpen(false)} />
            <motion.div className="relative z-10 h-full"
              initial={{ x: 300 }} animate={{ x: 0 }} exit={{ x: 300 }}
              transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}>
              <ContextRail state={state} liveTurn={liveTurn} health={health}
                onClose={() => setNarrowRailOpen(false)} />
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
    </ChatsContext.Provider>
    </ViewerContext.Provider>
  );
}

/* The model's plan, shown as reasoning rather than scraped out of prose. */
function PlanBlock({ plan }: { plan: string }) {
  return (
    <div className="mb-3 flex gap-2.5 rounded-xl border border-on-surface/[0.09] bg-on-surface/[0.02] px-3.5 py-3">
      <Lightbulb size={13} className="shrink-0 mt-0.5 text-on-surface/40" />
      <div className="min-w-0">
        <p className="px-label mb-1">Plan</p>
        <p className="text-[12px] leading-5 text-on-surface/65 whitespace-pre-wrap">{plan}</p>
      </div>
    </div>
  );
}

/* One sandbox run: what it was allowed to do, what it printed, what it changed. */
function ExecutionBlock({ execution }: { execution: Execution }) {
  const [open, setOpen] = useState(false);
  const openAsset = useContext(ViewerContext);
  const changed = execution.changes;
  const changeCount = changed
    ? changed.created.length + changed.modified.length + changed.deleted.length
    : 0;

  return (
    <div className="mb-3 rounded-xl border border-on-surface/[0.09] overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-on-surface/[0.03] transition-colors duration-200">
        <Terminal size={12} className="shrink-0 text-on-surface/45" />
        <span className="px-label">{execution.runtime}</span>
        <span className="text-[11px] text-on-surface/45 truncate flex-1">
          {execution.status === 'running' ? 'running…' : execution.summary}
        </span>
        {execution.status === 'running'
          ? <Loader2 size={11} className="animate-spin text-on-surface/45 shrink-0" />
          : execution.status === 'failed'
            ? <AlertTriangle size={11} className="text-error shrink-0" />
            : <Check size={11} className="text-primary shrink-0" />}
        <ChevronRight size={12}
          className={`shrink-0 text-on-surface/35 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
      </button>

      {/* Outside the collapse on purpose: a generated file the user cannot
          find is the same as one that was never produced. */}
      {execution.artifacts.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3.5 pb-3 pt-0.5">
          {execution.artifacts.map(a => (
            <button key={a.asset_id}
              onClick={() => openAsset({ id: a.asset_id, name: a.name })}
              aria-label={`Open ${a.name}`}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-primary/30 bg-primary/[0.06] text-[11px] text-on-surface/80 hover:bg-primary/[0.12] transition-colors duration-200">
              <Eye size={11} className="text-primary/80" />
              <span className="font-mono">{a.name}</span>
              <span className="text-on-surface/40">{(a.bytes / 1024).toFixed(1)} KB</span>
            </button>
          ))}
        </div>
      )}

      {open && (
        <div className="border-t border-on-surface/[0.07]">
          {execution.output.length > 0 && (
            <pre className="max-h-64 overflow-auto px-3.5 py-3 font-mono text-[11px] leading-relaxed text-on-surface/70 bg-on-surface/[0.02]">
              {execution.output.join('\n')}
            </pre>
          )}
          {changeCount > 0 && changed && (
            <div className="px-3.5 py-2.5 border-t border-on-surface/[0.07]">
              <p className="px-label mb-1.5">Files</p>
              <ul className="space-y-0.5 font-mono text-[11px]">
                {changed.created.map(p => <li key={p} className="text-primary/80">+ {p}</li>)}
                {changed.modified.map(p => <li key={p} className="text-on-surface/60">~ {p}</li>)}
                {changed.deleted.map(p => <li key={p} className="text-error/80">− {p}</li>)}
              </ul>
            </div>
          )}
          {execution.output.length === 0 && changeCount === 0 && (
            <p className="px-3.5 py-3 text-[11px] text-on-surface/35">No output, no file changes.</p>
          )}
        </div>
      )}
    </div>
  );
}

function ToolRow({ call }: { call: ToolCall }) {
  return (
    <div className="mb-2 flex items-center gap-2.5 text-[11px]">
      {call.status === 'running'
        ? <Loader2 size={11} className="animate-spin text-on-surface/45 shrink-0" />
        : call.status === 'error'
          ? <AlertTriangle size={11} className="text-error shrink-0" />
          : <Check size={11} className="text-primary shrink-0" />}
      <span className="font-mono text-on-surface/70">{call.name}</span>
      {call.summary && <span className="text-on-surface/40 truncate">{call.summary}</span>}
    </div>
  );
}

/* ── Built-in viewers ──────────────────────────────────────────────────────
   Everything Primnox can produce, readable without leaving the app and
   without downloading it first.

   Read-only by construction, not by discipline: this renders text nodes and
   nothing else. There is no input, no contenteditable, and no endpoint behind
   it that writes — the server's preview layer only reads. PDFs and images go
   straight to the browser, which already knows them; Word, Excel, PowerPoint
   and SQLite are parsed server-side by the same libraries that wrote them,
   which is why this file needs no new dependency to read any of them. */
function AssetViewer({ asset, onClose }: {
  asset: { id: string; name: string }; onClose: () => void;
}) {
  const [preview, setPreview] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState(0);

  useEffect(() => {
    let live = true;
    setPreview(null); setError(null); setSheet(0);
    api.preview(asset.id)
      .then(p => { if (live) setPreview(p); })
      .catch(e => { if (live) setError(String(e)); });
    return () => { live = false; };
  }, [asset.id]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const src = `${API}/assets/${asset.id}/download?inline=1`;

  /* Deliberately not a `motion` element, unlike the rest of this file.
     Wrapped in AnimatePresence as a custom component, the backdrop mounted
     with its `initial` styles — opacity 0, translateY(8px) — and no animation
     ever started, so the viewer was present in the DOM, readable to a script,
     and completely invisible to a person. A modal that silently fails to
     appear is a worse defect than a modal without a fade, so the entry
     animation is plain CSS with nothing to go wrong. */
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--scrim)] p-6"
      onClick={onClose}>
      <div
        role="dialog" aria-modal="true" aria-label={`Preview of ${asset.name}`}
        onClick={e => e.stopPropagation()}
        className="w-full max-w-5xl h-[85vh] flex flex-col rounded-2xl border border-on-surface/[0.12] bg-surface overflow-hidden shadow-2xl">

        <header className="h-12 shrink-0 flex items-center gap-3 px-4 border-b border-on-surface/[0.09]">
          <FileText size={14} className="opacity-60 shrink-0" />
          <span className="font-mono text-[12px] truncate">{asset.name}</span>
          <span className="px-label shrink-0 opacity-50">read-only</span>
          <div className="flex-1" />
          <a href={`${API}/assets/${asset.id}/download`} download={asset.name}
            className="px-2.5 py-1 rounded-lg border border-on-surface/[0.12] hover:bg-on-surface/[0.06] transition-colors duration-200 px-label inline-flex items-center gap-1.5">
            <Download size={11} /> Download
          </a>
          <button onClick={onClose} aria-label="Close preview"
            className="w-7 h-7 rounded-lg flex items-center justify-center hover:bg-on-surface/[0.08] transition-colors duration-200">
            <X size={14} />
          </button>
        </header>

        <div className="flex-1 min-h-0 overflow-auto custom-scrollbar bg-on-surface/[0.02]">
          {error && <p className="p-6 text-sm text-error">Could not load a preview: {error}</p>}
          {!preview && !error && (
            <p className="p-6 px-label flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> Reading…
            </p>
          )}

          {/* The PDF frame stays white in every theme, and correctly so: a PDF
              page is paper. Tinting it would misrepresent the document. */}
          {preview?.kind === 'pdf' && (
            <iframe src={src} title={asset.name} className="w-full h-full border-0 bg-white" />
          )}

          {preview?.kind === 'image' && (
            <div className="h-full flex items-center justify-center p-6">
              <img src={src} alt={asset.name} className="max-w-full max-h-full object-contain" />
            </div>
          )}

          {preview?.kind === 'text' && (
            <pre className="p-5 font-mono text-[12px] leading-relaxed whitespace-pre-wrap break-words text-on-surface/80">
              {preview.text}
              {preview.truncated && <span className="text-on-surface/40">{'\n\n… truncated'}</span>}
            </pre>
          )}

          {preview?.kind === 'sheets' && preview.sheets?.length > 0 && (
            <div className="h-full flex flex-col">
              {preview.sheets.length > 1 && (
                <div className="flex gap-1 px-3 pt-3 shrink-0 flex-wrap">
                  {preview.sheets.map((s: any, i: number) => (
                    <button key={s.name + i} onClick={() => setSheet(i)}
                      className={`px-2.5 py-1 rounded-lg px-label transition-colors duration-200
                        ${i === sheet ? 'bg-on-surface/[0.10] text-on-surface'
                                      : 'text-on-surface/50 hover:bg-on-surface/[0.05]'}`}>
                      {s.name}
                    </button>
                  ))}
                </div>
              )}
              <SheetTable sheet={preview.sheets[Math.min(sheet, preview.sheets.length - 1)]} />
            </div>
          )}

          {preview?.kind === 'document' && (
            <article className="mx-auto max-w-2xl p-8 space-y-3">
              {preview.blocks.map((b: any, i: number) =>
                b.type === 'heading'
                  ? <h2 key={i} className={b.level <= 1 ? 'px-display px-display-sm' : 'text-[15px] font-semibold'}>{b.text}</h2>
                  : b.type === 'bullet'
                    ? <p key={i} className="text-sm leading-6 pl-5 relative before:content-['•'] before:absolute before:left-1 before:opacity-40">{b.text}</p>
                    : b.type === 'table'
                      ? <SheetTable key={i} sheet={{ name: '', header: b.rows[0] ?? [], rows: b.rows.slice(1), total_rows: b.rows.length - 1, truncated: false }} />
                      : <p key={i} className="text-sm leading-6 text-on-surface/80">{b.text}</p>)}
              {preview.blocks.length === 0 && <p className="px-label">This document has no text in it.</p>}
            </article>
          )}

          {preview?.kind === 'slides' && (
            <div className="p-6 space-y-4">
              {preview.slides.map((s: any) => (
                <div key={s.index} className="rounded-xl border border-on-surface/[0.10] bg-surface p-5 aspect-[16/9] flex flex-col">
                  <p className="px-label mb-2">Slide {s.index}</p>
                  <h3 className="text-[17px] font-semibold mb-3">{s.title || <span className="opacity-40">Untitled</span>}</h3>
                  <ul className="space-y-1.5 overflow-auto">
                    {s.lines.map((l: string, i: number) => (
                      <li key={i} className="text-sm leading-6 text-on-surface/75 pl-4 relative before:content-['–'] before:absolute before:left-0 before:opacity-40">{l}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

          {(preview?.kind === 'unsupported' || preview?.kind === 'unreadable'
            || preview?.kind === 'missing') && (
            <div className="p-8 text-center">
              <p className="px-body text-sm mb-1">
                {preview.kind === 'missing' ? 'The stored file is gone.'
                  : preview.kind === 'unreadable' ? 'This file could not be read.'
                    : 'No built-in viewer for this format.'}
              </p>
              {preview.error && <p className="px-label mb-3">{preview.error}</p>}
              <p className="px-label">Download it to open it elsewhere.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* One table, used for spreadsheets, CSVs, database tables and the tables
   inside a Word document — they are all the same shape once parsed. */
function SheetTable({ sheet }: { sheet: any }) {
  return (
    <div className="flex-1 min-h-0 overflow-auto custom-scrollbar p-3">
      <table className="w-full text-[12px] border-collapse">
        {sheet.header?.length > 0 && (
          <thead className="sticky top-0">
            <tr>
              {sheet.header.map((h: string, i: number) => (
                <th key={i} className="text-left font-semibold px-2.5 py-1.5 bg-surface border-b border-on-surface/[0.14] whitespace-nowrap">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {sheet.rows.map((row: string[], r: number) => (
            <tr key={r} className="hover:bg-on-surface/[0.03]">
              {row.map((cell, c) => (
                <td key={c} className="px-2.5 py-1 border-b border-on-surface/[0.05] text-on-surface/75 whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {sheet.truncated && (
        <p className="px-label pt-3">
          Showing {sheet.rows.length} of {sheet.total_rows} rows.
        </p>
      )}
    </div>
  );
}

/* What a settled question says afterwards. An approval you gave by hand must
   not read back as one the machine gave itself — that is the difference
   between a record and a reassurance. */
const RESOLUTION_COPY: Record<string, string> = {
  allow_auto: 'approved automatically',
  allow_once: 'you allowed this once',
  allow_turn: 'you allowed this for the turn',
  deny: 'you declined',
};

/* A permission question. Auto-approved ones are still shown — the user should
   be able to see afterwards what ran without having been interrupted. */
function PermissionBlock({ p }: { p: PermissionRequest }) {
  if (p.auto || p.resolved) {
    return (
      <div className="mb-3 flex items-center gap-2 text-[11px] text-on-surface/40">
        {p.resolved === 'deny'
          ? <ShieldAlert size={11} className="shrink-0" />
          : <ShieldCheck size={11} className="shrink-0" />}
        <span className="font-mono">{p.action}</span>
        <span>
          {p.resolved
            ? RESOLUTION_COPY[p.resolved] ?? p.resolved
            : 'approved automatically'}
        </span>
      </div>
    );
  }
  return (
    <div className="mb-3 rounded-xl border border-primary/25 bg-primary/[0.05] px-3.5 py-3">
      <div className="flex items-start gap-2.5">
        <ShieldAlert size={14} className="shrink-0 mt-0.5 text-primary/80" />
        <div className="min-w-0 flex-1">
          <p className="px-label mb-1">Permission needed</p>
          <p className="text-[12px] leading-5 text-on-surface/75 whitespace-pre-wrap">{p.detail}</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {p.options.map(o => (
              <button key={o.id} onClick={() => api.resolvePermission(p.id, o.id)}
                className="px-2.5 py-1 rounded-lg border border-on-surface/15 hover:bg-on-surface/[0.06] transition-all duration-200 px-label">
                {o.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* One turn: the user's message, the reply, and — critically — its own status.
   There is no global "thinking" indicator anywhere in this file (CRS §5.3). */
function TurnBlock({ turn }: { turn: Turn }) {
  const live = !TERMINAL.includes(turn.status);
  const openAsset = useContext(ViewerContext);
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }} className="mb-8">

      <div className="flex justify-end mb-4">
        <div className="max-w-[80%] bg-on-surface/[0.07] border border-on-surface/[0.08] rounded-2xl rounded-br-sm px-4 py-2.5">
          <p className="text-sm leading-6 whitespace-pre-wrap">{turn.userText}</p>
        </div>
      </div>

      <div className="flex gap-3">
        <div className="w-6 shrink-0 mt-0.5">
          <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center">
            <Terminal size={11} className="text-primary/70" />
          </div>
        </div>

        <div className="flex-1 min-w-0">
          {live && (
            <p className="px-label mb-2 flex items-center gap-1.5">
              <Loader2 size={10} className="animate-spin" />
              {STATUS_COPY[turn.status] ?? turn.status}
            </p>
          )}

          {turn.plan && <PlanBlock plan={turn.plan} />}
          {turn.permissions.map(p => <PermissionBlock key={p.id} p={p} />)}
          {turn.toolCalls.map((c, i) => <ToolRow key={`${c.name}-${i}`} call={c} />)}
          {turn.executions.map(x => <ExecutionBlock key={x.id} execution={x} />)}

          {turn.assets.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {turn.assets.map(a => (
                <button key={a.id} onClick={() => openAsset({ id: a.id, name: a.name })}
                  aria-label={`Open ${a.name}`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/[0.09] text-[11px] text-on-surface/60 hover:text-on-surface/90 hover:bg-on-surface/[0.05] transition-colors duration-200">
                  <FileText size={11} className="opacity-60" />{a.name}
                </button>
              ))}
            </div>
          )}

          {turn.workspaces.length > 0 && (
            <div className="mb-3 flex flex-wrap gap-1.5">
              {turn.workspaces.map(w => (
                <span key={w.id}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-primary/25 bg-primary/[0.05] text-[11px] text-on-surface/70">
                  <Package size={11} className="text-primary/70" />
                  {w.title}
                  <span className="font-mono text-[9px] text-on-surface/40">v{w.version}</span>
                </span>
              ))}
            </div>
          )}

          {turn.assistantText && (
            <div className="text-sm leading-6">
              <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{turn.assistantText}</ReactMarkdown>
            </div>
          )}

          {turn.status === 'cancelled' && (
            <p className="px-label mt-2 flex items-center gap-1.5">
              <Ban size={10} /> Stopped{turn.assistantText ? ' — partial reply kept' : ''}
            </p>
          )}

          {/* A failure renders as a failure, with an honest retry affordance —
              never as an assistant message pretending to be a reply. */}
          {turn.error && (
            <div className="mt-2 flex items-start gap-2.5 rounded-xl border border-error/25 bg-error/[0.06] px-3.5 py-3">
              <AlertTriangle size={14} className="text-error shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="text-[13px] text-on-surface/85">{turn.error.message}</p>
                <p className="px-label mt-1">{turn.error.code}</p>
              </div>
              {turn.error.retryable && (
                <button onClick={() => api.retry(turn.id)}
                  aria-label="Retry this message"
                  className="ml-auto shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-on-surface/15 hover:bg-on-surface/[0.06] transition-all duration-200 px-label">
                  <RotateCw size={10} /> Retry
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

/** Bucket conversations by day, newest bucket first, preserving list order. */
function groupByDay(rows: any[]): [string, any[]][] {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const day = 86_400_000;

  const bucket = (ts: number): string => {
    if (!ts) return 'Earlier';
    if (ts >= startOfToday) return 'Today';
    if (ts >= startOfToday - day) return 'Yesterday';
    if (ts >= startOfToday - 7 * day) return 'Previous 7 days';
    if (ts >= startOfToday - 30 * day) return 'Previous 30 days';
    return 'Earlier';
  };

  const order = ['Today', 'Yesterday', 'Previous 7 days', 'Previous 30 days', 'Earlier'];
  const groups = new Map<string, any[]>();
  for (const c of rows) {
    const key = bucket(c.updated_at ?? c.created_at ?? 0);
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(c);
  }
  return order.filter(k => groups.has(k)).map(k => [k, groups.get(k)!] as [string, any[]]);
}

function ContextRail({ state, liveTurn, health, onClose }:
  { state: ConversationState; liveTurn: Turn | undefined; health: any; onClose: () => void }) {
  // One step per state the turn actually passes through, so Progress reflects
  // the runtime rather than a hardcoded three-stage guess.
  const ORDER = ['queued', 'building_context', 'thinking', 'streaming'];
  const steps = liveTurn
    ? ORDER.map((s, i) => ({
        label: STATUS_COPY[s],
        done: TERMINAL.includes(liveTurn.status) || ORDER.indexOf(liveTurn.status) > i,
      }))
    : [];

  // Everything this conversation produced, newest first. The rail used to be
  // six lines of diagnostics above 500px of black, while the generated file —
  // the entire point of the app — was a chip you could miss next to the
  // avatar. Files belong at the top of the panel that has the room for them.
  const files = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; name: string; bytes?: number }[] = [];
    for (const t of state.turns) {
      for (const x of t.executions) {
        for (const a of x.artifacts ?? []) {
          if (!seen.has(a.asset_id)) {
            seen.add(a.asset_id);
            out.push({ id: a.asset_id, name: a.name, bytes: a.bytes });
          }
        }
      }
      for (const a of t.assets) {
        if (!seen.has(a.id)) {
          seen.add(a.id);
          out.push({ id: a.id, name: a.name });
        }
      }
    }
    return out.reverse();
  }, [state.turns]);

  const workspaces = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; title: string; version: number }[] = [];
    for (const t of state.turns) {
      for (const w of t.workspaces) {
        if (!seen.has(w.id)) { seen.add(w.id); out.push(w); }
      }
    }
    return out.reverse();
  }, [state.turns]);

  return (
    <aside aria-label="Context" className="w-[288px] h-full flex flex-col border-l border-on-surface/[0.07] bg-[var(--nav-bg)]">
      <header className="h-14 shrink-0 flex items-center justify-between px-5 border-b border-on-surface/[0.07]">
        <span className="px-label">Context</span>
        <button onClick={onClose} aria-label="Hide context panel"
          className="p-1 -mr-1 rounded text-on-surface/40 hover:text-on-surface transition-all duration-200">
          <PanelRight size={14} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* Progress only exists while something is running. A permanent
            "Steps appear here as a turn runs" is a heading explaining its own
            emptiness — it occupied the top of the panel to say nothing. */}
        {steps.length > 0 && (
          <section className="px-5 py-4 border-b border-on-surface/[0.07]">
            <p className="px-label mb-3">Progress</p>
            <ol className="space-y-2.5">
              {steps.map(s => (
                <li key={s.label} className="flex items-center gap-2.5">
                  {s.done ? <Check size={12} className="text-primary shrink-0" />
                          : <Loader2 size={12} className="text-on-surface/45 animate-spin shrink-0" />}
                  <span className={`text-[11px] ${s.done ? 'text-on-surface/55' : 'text-on-surface/80'}`}>{s.label}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {(files.length > 0 || workspaces.length > 0) && (
          <section className="px-5 py-4 border-b border-on-surface/[0.07]">
            <p className="px-label mb-3">Files</p>
            <ul className="space-y-1">
              {files.map(f => (
                <li key={f.id}>
                  <a href={`${API}/assets/${f.id}/download`} download={f.name}
                    className="group flex items-center gap-2.5 -mx-2 px-2 py-1.5 rounded-lg
                               hover:bg-on-surface/[0.05] transition-colors duration-200">
                    <FileText size={13} className="shrink-0 text-on-surface/40" />
                    <span className="text-[11px] text-on-surface/75 truncate flex-1">{f.name}</span>
                    {f.bytes != null && (
                      <span className="font-mono text-[9px] text-on-surface/30 tabular-nums shrink-0">
                        {f.bytes < 1024 ? `${f.bytes}B` : `${(f.bytes / 1024).toFixed(0)}K`}
                      </span>
                    )}
                    <Download size={11} className="shrink-0 text-on-surface/0 group-hover:text-on-surface/50 transition-colors duration-200" />
                  </a>
                </li>
              ))}
              {workspaces.map(w => (
                <li key={w.id} className="flex items-center gap-2.5 -mx-2 px-2 py-1.5">
                  <Package size={13} className="shrink-0 text-primary/60" />
                  <span className="text-[11px] text-on-surface/75 truncate flex-1">{w.title}</span>
                  <span className="font-mono text-[9px] text-on-surface/30 shrink-0">v{w.version}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="px-5 py-4 border-b border-on-surface/[0.07]">
          <p className="px-label mb-3">Context</p>
          <ul className="space-y-2.5">
            <li className="flex items-center gap-2.5"><Cpu size={13} className="text-on-surface/40 shrink-0" />
              <span className="text-[11px] text-on-surface/70">
                {health?.model ? `${health.model.provider} · ${health.model.model}` : 'resolving provider…'}
              </span></li>
            <li className="flex items-center gap-2.5"><Terminal size={13} className="text-on-surface/40 shrink-0" />
              <span className="text-[11px] text-on-surface/70">{state.turns.length} turns in context</span></li>
            {/* Says which backend is actually isolating execution — or that
                none is, rather than implying a sandbox that isn't there. */}
            <li className="flex items-start gap-2.5">
              {health?.sandbox
                ? <ShieldCheck size={13} className="text-on-surface/40 shrink-0 mt-0.5" />
                : <ShieldAlert size={13} className="text-error/70 shrink-0 mt-0.5" />}
              <span className={`text-[11px] ${health?.sandbox ? 'text-on-surface/45' : 'text-error/80'}`}>
                {health?.sandbox === 'appcontainer' ? 'Sandbox: AppContainer isolation'
                  : health?.sandbox === 'unsandboxed' ? 'Sandbox: NONE — code runs unisolated'
                  : health ? 'Sandbox: unavailable — execution refused'
                  : 'Checking sandbox…'}
              </span>
            </li>
            {health?.model && !health.model.local && (
              <li className="flex items-start gap-2.5"><ShieldAlert size={13} className="text-on-surface/40 shrink-0 mt-0.5" />
                <span className="text-[11px] text-on-surface/45">Cloud provider — prompts leave this device</span></li>
            )}
          </ul>
        </section>

        {/* The cursor, on screen. Reconnect correctness is the whole reason the
            sequence is global and gapless, so it is worth being able to see. */}
        <section className="px-5 py-4">
          <p className="px-label mb-3">Stream</p>
          <ul className="space-y-2.5 font-mono text-[10px] text-on-surface/50">
            <li className="flex justify-between"><span>cursor</span><span className="tabular-nums text-on-surface/75">{state.cursor}</span></li>
            <li className="flex justify-between"><span>socket</span><span className="text-on-surface/75">{state.connected ? 'open' : 'closed'}</span></li>
            <li className="flex justify-between"><span>synced</span><span className="text-on-surface/75">{state.synced ? 'yes' : 'no'}</span></li>
          </ul>
        </section>
      </div>

      <footer className="h-10 shrink-0 flex items-center gap-2 px-5 border-t border-on-surface/[0.07]">
        <Circle size={7} className={liveTurn ? 'text-primary fill-current animate-pulse' : 'text-on-surface/25 fill-current'} />
        <span className="px-label">{liveTurn ? STATUS_COPY[liveTurn.status] ?? 'Working' : 'Idle'}</span>
      </footer>
    </aside>
  );
}
