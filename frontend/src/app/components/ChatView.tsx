import { useState, useEffect, useRef, ChangeEvent } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Paperclip, ArrowUp, Sparkles, X, Plus, MessageSquare, Pin, Folder, FolderPlus, ChevronDown, ChevronRight, Trash2, Bot, Pencil, Check, Copy, Terminal } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

// ── Code block: syntax highlighting + copy button ─────────────────────────────
const CodeBlock = ({ language, value }: { language: string; value: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value)
      .then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); })
      .catch(() => {});
  };
  return (
    <div className="my-3 rounded-xl overflow-hidden border border-white/10 bg-black/60">
      <div className="flex items-center justify-between px-4 py-2 border-b border-white/5 bg-white/[0.03]">
        <span className="text-[9px] font-mono text-white/30 uppercase tracking-widest">{language}</span>
        <button onClick={copy}
          className="flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-widest text-white/30 hover:text-primary transition-colors active:scale-95">
          {copied ? <><Check size={11} /> Copied</> : <><Copy size={11} /> Copy</>}
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        PreTag="div"
        customStyle={{ margin: 0, background: 'transparent', padding: '1rem', fontSize: '0.78rem', lineHeight: 1.65 }}
        codeTagProps={{ style: { fontFamily: 'inherit' } }}
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
};

// ── Markdown component overrides ──────────────────────────────────────────────
const MD_COMPONENTS: any = {
  code({ children, className, ...props }: any) {
    // react-markdown v8 removed the `inline` prop; detect by language class or newlines.
    const lang = /language-(\w+)/.exec(className || '')?.[1];
    const text = String(children).replace(/\n$/, '');
    if (!lang && !text.includes('\n')) {
      return (
        <code className="bg-white/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock language={lang || 'text'} value={text} />;
  },
  pre({ children }: any) { return <>{children}</>; },
  p({ children }: any) {
    return <p className="mb-3 last:mb-0 leading-7 text-white/85">{children}</p>;
  },
  ul({ children }: any) {
    return <ul className="mb-3 space-y-1 pl-5 list-disc text-white/85">{children}</ul>;
  },
  ol({ children }: any) {
    return <ol className="mb-3 space-y-1 pl-5 list-decimal text-white/85">{children}</ol>;
  },
  li({ children }: any) {
    return <li className="leading-7">{children}</li>;
  },
  h1({ children }: any) { return <h1 className="text-xl font-bold text-white mb-3 mt-4">{children}</h1>; },
  h2({ children }: any) { return <h2 className="text-base font-bold text-white mb-2 mt-3">{children}</h2>; },
  h3({ children }: any) { return <h3 className="text-sm font-semibold text-white/90 mb-2 mt-3">{children}</h3>; },
  strong({ children }: any) { return <strong className="font-semibold text-white">{children}</strong>; },
  a({ href, children }: any) { return <a href={href} className="text-primary underline underline-offset-2 hover:text-primary/70 transition-colors">{children}</a>; },
  blockquote({ children }: any) {
    return <blockquote className="border-l-2 border-white/20 pl-4 my-2 text-white/50 italic">{children}</blockquote>;
  },
  table({ children }: any) {
    return (
      <div className="my-3 overflow-x-auto rounded-xl border border-white/10">
        <table className="w-full text-xs">{children}</table>
      </div>
    );
  },
  th({ children }: any) { return <th className="px-4 py-2 text-left font-semibold text-white/60 bg-white/5 border-b border-white/10">{children}</th>; },
  td({ children }: any) { return <td className="px-4 py-2 text-white/75 border-b border-white/5">{children}</td>; },
  hr() { return <hr className="my-4 border-white/10" />; },
};

// ── Relative time formatter ────────────────────────────────────────────────────
function relativeTime(ts: number): string {
  const diff = (Date.now() - ts) / 1000;
  if (diff < 60)  return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return new Date(ts).toLocaleDateString([], { month: 'short', day: 'numeric' });
}

// ── Sidebar date label ────────────────────────────────────────────────────────
function sidebarDate(dateStr: string): string {
  if (!dateStr) return '';
  const d = new Date(dateStr);
  const now = new Date();
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000);
  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7)  return d.toLocaleDateString([], { weekday: 'long' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

// ── Typing dots ───────────────────────────────────────────────────────────────
const TypingDots = () => (
  <div className="flex items-center gap-1.5 py-1">
    {[0, 1, 2].map(i => (
      <motion.div
        key={i}
        className="w-1.5 h-1.5 rounded-full bg-white/30"
        animate={{ opacity: [0.25, 1, 0.25], y: [0, -3, 0] }}
        transition={{ repeat: Infinity, duration: 1, delay: i * 0.18, ease: 'easeInOut' }}
      />
    ))}
  </div>
);

// ── Quick action cards ────────────────────────────────────────────────────────
const QUICK_ACTIONS = [
  { label: "Analyze workspace",   prompt: "Analyze my current workspace and give me a summary" },
  { label: "System status",       prompt: "Summarize my current system status" },
  { label: "Pending tasks",       prompt: "What tasks do I have pending?" },
  { label: "Search notes",        prompt: "Search my notes for " },
  { label: "Set a reminder",      prompt: "Remind me to " },
  { label: "Research something",  prompt: "Search the web for " },
];

// ── Main component ─────────────────────────────────────────────────────────────
export const ChatExpandedSidebar = ({
  aiName: _aiName,
  userName: _userName,
  setStatus,
  liveMessages = [],
  sendMessage = () => {},
  chatSessions = [],
  chatFolders = [],
  activeChatId = 'current',
  loadChat = () => {},
  createNewChat = () => {},
  refreshChats = () => {}
}: {
  aiName: string,
  userName: string,
  setStatus: (s: AiStatus) => void,
  liveMessages?: any[],
  sendMessage?: (text: string, sessionId?: string, file?: File | null) => void,
  chatSessions?: any[],
  chatFolders?: any[],
  activeChatId?: string,
  loadChat?: (id: string) => void,
  createNewChat?: () => void,
  refreshChats?: () => void
}) => {
  const fileInputRef   = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue]   = useState('');
  const [attachedFile, setAttachedFile] = useState<File | null>(null);

  // Sidebar
  const [historyOpen, setHistoryOpen]   = useState(true);
  const [foldersOpen, setFoldersOpen]   = useState(true);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);

  // Context menu / rename / folder creation
  const [contextMenu, setContextMenu]   = useState<{ x: number; y: number; chat: any } | null>(null);
  const [renameState, setRenameState]   = useState<{ chatId: string; value: string } | null>(null);
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [newFolderName, setNewFolderName]   = useState('');
  const [creatingFolder, setCreatingFolder] = useState(false);

  useEffect(() => {
    const close = () => setContextMenu(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, []);

  useEffect(() => {
    if (renameState) setTimeout(() => renameInputRef.current?.select(), 50);
  }, [renameState]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [liveMessages]);

  // ── Handlers ─────────────────────────────────────────────────────────────
  const handleContextMenu = (e: React.MouseEvent, chat: any) => {
    e.preventDefault(); e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, chat });
  };

  const handleMenuAction = async (action: string, chat: any, folderId?: string) => {
    setContextMenu(null);
    try {
      if (action === 'pin') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ isPinned: !chat.isPinned })
        });
      } else if (action === 'rename') {
        setRenameState({ chatId: chat.id, value: chat.title }); return;
      } else if (action === 'move') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folderId })
        });
      } else if (action === 'auto_assign') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}/auto_assign`, { method: 'POST' });
      } else if (action === 'delete') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, { method: 'DELETE' });
      }
      refreshChats();
    } catch (e) { console.error(e); }
  };

  const submitRename = async () => {
    if (!renameState || !renameState.value.trim()) { setRenameState(null); return; }
    try {
      const res = await fetch(`http://localhost:8000/api/chats/${renameState.chatId}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: renameState.value.trim() })
      });
      if (!res.ok) throw new Error(`${res.status}`);
      refreshChats();
    } catch (e) { console.error(e); }
    finally { setRenameState(null); }
  };

  const createFolder = async () => {
    const name = newFolderName.trim(); if (!name) return;
    try {
      await fetch('http://localhost:8000/api/folders', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: name }),
      });
      setNewFolderName(''); setCreatingFolder(false); refreshChats();
    } catch (e) { console.error(e); }
  };

  const deleteFolder = async (folderId: string) => {
    try {
      await fetch(`http://localhost:8000/api/folders/${folderId}`, { method: 'DELETE' });
      if (activeFolderId === folderId) setActiveFolderId(null);
      refreshChats();
    } catch (e) { console.error(e); }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) { setAttachedFile(e.target.files[0]); setStatus('copy'); }
  };

  const removeAttachedFile = () => {
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
  };

  const handleSend = async () => {
    if (!inputValue.trim() && !attachedFile) return;
    // Capture values before clearing — clear immediately for responsive feel
    const text = inputValue;
    const file = attachedFile;
    setInputValue('');
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
    try {
      await sendMessage(text, activeChatId, file);
    } catch (e) {
      // Restore message text so the user doesn't lose it
      setInputValue(text);
      console.error('sendMessage failed', e);
    }
  };

  const pinnedChats   = chatSessions.filter(c => c.isPinned);
  const unpinnedChats = chatSessions.filter(c =>
    !c.isPinned && ((!activeFolderId && !c.folderId) || c.folderId === activeFolderId)
  );

  // ── Sidebar chat item ─────────────────────────────────────────────────────
  const ChatItem = ({ c }: { c: any }) => {
    const isActive = activeChatId === c.id;
    return (
      <button
        onClick={() => loadChat(c.id)}
        onContextMenu={e => handleContextMenu(e, c)}
        className={`w-full text-left px-3 py-2.5 rounded-xl transition-all group flex items-start gap-2.5
          ${isActive
            ? 'bg-primary/15 text-white'
            : 'hover:bg-white/5 text-white/55 hover:text-white/85'}`}
      >
        <MessageSquare size={13} className={`mt-0.5 shrink-0 ${isActive ? 'text-primary/70' : 'text-white/20 group-hover:text-white/40'}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm truncate font-medium leading-snug">{c.title}</p>
          <p className="text-[10px] mt-0.5 text-white/25">{sidebarDate(c.date)}</p>
        </div>
        {c.isPinned && <Pin size={10} className="shrink-0 mt-1 text-primary/40" />}
      </button>
    );
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full bg-black overflow-hidden">

      {/* ── Context Menu ────────────────────────────────────────────────── */}
      {contextMenu && createPortal(
        <div
          className="fixed z-50 bg-zinc-900/95 border border-white/10 rounded-2xl shadow-2xl backdrop-blur-2xl py-1.5 w-52 text-sm overflow-hidden"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={e => e.stopPropagation()}
        >
          <p className="px-4 py-2 border-b border-white/5 font-semibold text-white/80 truncate text-xs">{contextMenu.chat.title}</p>
          {[
            { action: 'pin', icon: Pin, label: contextMenu.chat.isPinned ? 'Unpin' : 'Pin to top' },
            { action: 'rename', icon: Pencil, label: 'Rename' },
          ].map(({ action, icon: Icon, label }) => (
            <button key={action} onClick={() => handleMenuAction(action, contextMenu.chat)}
              className="w-full text-left px-4 py-2.5 hover:bg-white/8 text-white/70 hover:text-white flex items-center gap-3 transition-colors">
              <Icon size={13} /> {label}
            </button>
          ))}
          <div className="group/sub relative">
            <button className="w-full text-left px-4 py-2.5 hover:bg-white/8 text-white/70 hover:text-white flex items-center justify-between transition-colors">
              <span className="flex items-center gap-3"><Folder size={13} /> Move to folder</span>
              <ChevronRight size={13} />
            </button>
            <div className="absolute left-full top-0 hidden group-hover/sub:block w-52 bg-zinc-900/95 border border-white/10 rounded-2xl shadow-2xl backdrop-blur-2xl py-1.5 ml-1">
              <button onClick={() => handleMenuAction('auto_assign', contextMenu.chat)}
                className="w-full text-left px-4 py-2.5 hover:bg-white/8 text-primary flex items-center gap-3 transition-colors">
                <Bot size={13} /> Auto-detect
              </button>
              <div className="h-px bg-white/10 my-1" />
              {chatFolders.map((f: any) => (
                <button key={f.id} onClick={() => handleMenuAction('move', contextMenu.chat, f.id)}
                  className="w-full text-left px-4 py-2.5 hover:bg-white/8 text-white/70 hover:text-white truncate text-xs transition-colors">
                  {f.title}
                </button>
              ))}
            </div>
          </div>
          <div className="h-px bg-white/8 my-1" />
          <button onClick={() => handleMenuAction('delete', contextMenu.chat)}
            className="w-full text-left px-4 py-2.5 hover:bg-red-500/15 text-red-400/80 hover:text-red-400 flex items-center gap-3 transition-colors">
            <Trash2 size={13} /> Delete
          </button>
        </div>,
        document.body
      )}

      {/* ── Rename Modal ─────────────────────────────────────────────────── */}
      {renameState && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setRenameState(null)}>
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            className="bg-zinc-900 border border-white/10 rounded-2xl shadow-2xl p-6 w-96"
            onClick={e => e.stopPropagation()}>
            <p className="text-xs font-semibold text-white/50 uppercase tracking-widest mb-4">Rename Chat</p>
            <input ref={renameInputRef} value={renameState.value}
              onChange={e => setRenameState({ ...renameState, value: e.target.value })}
              onKeyDown={e => { if (e.key === 'Enter') submitRename(); if (e.key === 'Escape') setRenameState(null); }}
              className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-sm focus:outline-none focus:border-primary/50 transition-colors"
            />
            <div className="flex gap-2 mt-4">
              <button onClick={submitRename}
                className="flex-1 flex items-center justify-center gap-2 bg-primary text-black font-bold px-4 py-2.5 rounded-xl text-sm hover:bg-white transition-all">
                <Check size={14} /> Save
              </button>
              <button onClick={() => setRenameState(null)}
                className="px-4 py-2.5 rounded-xl text-sm text-white/40 hover:text-white hover:bg-white/8 transition-all">
                Cancel
              </button>
            </div>
          </motion.div>
        </div>,
        document.body
      )}

      {/* ── Left Sidebar ─────────────────────────────────────────────────── */}
      <div className="w-64 border-r border-white/5 bg-zinc-950/60 flex flex-col shrink-0 overflow-hidden">
        {/* New Chat */}
        <div className="p-4 pt-10 border-b border-white/5">
          <button onClick={createNewChat}
            className="w-full flex items-center justify-between px-4 py-2.5 bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 hover:border-primary/40 rounded-xl transition-all group font-medium text-sm">
            New chat
            <Plus size={16} className="group-hover:rotate-90 transition-transform duration-200" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto py-4 px-3 space-y-5 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">

          {/* Pinned */}
          {pinnedChats.length > 0 && (
            <div>
              <p className="px-3 text-[10px] font-mono text-white/25 uppercase tracking-widest mb-2 flex items-center gap-2">
                <Pin size={10} /> Pinned
              </p>
              <div className="space-y-0.5">
                {pinnedChats.map(c => <ChatItem key={c.id} c={c} />)}
              </div>
            </div>
          )}

          {/* Folders */}
          <div>
            <div className="px-3 mb-2 flex items-center justify-between">
              <button onClick={() => setFoldersOpen(!foldersOpen)}
                className="flex items-center gap-2 text-[10px] font-mono text-white/25 uppercase tracking-widest hover:text-white/60 transition-colors">
                <Folder size={10} /> Folders
                {foldersOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
              </button>
              <button onClick={() => { setCreatingFolder(true); setFoldersOpen(true); }}
                className="text-white/20 hover:text-primary/70 transition-colors" title="New folder">
                <FolderPlus size={13} />
              </button>
            </div>
            {foldersOpen && (
              <div className="space-y-0.5">
                {creatingFolder && (
                  <div className="flex items-center gap-1 px-2 pb-1">
                    <input autoFocus value={newFolderName} onChange={e => setNewFolderName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') createFolder(); if (e.key === 'Escape') { setCreatingFolder(false); setNewFolderName(''); } }}
                      placeholder="Folder name…"
                      className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-white placeholder-white/20 outline-none focus:border-primary/50"
                    />
                    <button onClick={createFolder} className="text-primary hover:text-white transition-colors p-1"><Check size={12} /></button>
                    <button onClick={() => { setCreatingFolder(false); setNewFolderName(''); }} className="text-white/25 hover:text-white/60 transition-colors p-1"><X size={12} /></button>
                  </div>
                )}
                {chatFolders.map((f: any) => (
                  <div key={f.id} className={`flex items-center group rounded-xl transition-all ${activeFolderId === f.id ? 'bg-white/8' : 'hover:bg-white/5'}`}>
                    <button onClick={() => { setActiveFolderId(f.id); setHistoryOpen(true); }}
                      className={`flex-1 text-left px-3 py-2.5 text-sm flex items-center gap-2.5 ${activeFolderId === f.id ? 'text-primary' : 'text-white/55 group-hover:text-white/85'}`}>
                      <Folder size={13} className={activeFolderId === f.id ? 'text-primary/70' : 'text-white/20'} />
                      <span className="truncate flex-1">{f.title}</span>
                      <span className="text-[10px] text-white/25 shrink-0">{f.count}</span>
                    </button>
                    <button onClick={() => deleteFolder(f.id)}
                      className="pr-2.5 opacity-0 group-hover:opacity-100 text-white/20 hover:text-red-400/80 transition-all">
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent */}
          <div>
            <button onClick={() => { setActiveFolderId(null); setHistoryOpen(h => !h); }}
              className={`w-full px-3 mb-2 flex items-center justify-between text-[10px] font-mono uppercase tracking-widest transition-colors
                ${activeFolderId === null ? 'text-white/50' : 'text-white/25 hover:text-white/50'}`}>
              <span className="flex items-center gap-2">
                <MessageSquare size={10} /> {activeFolderId ? 'Back to recent' : 'Recent'}
              </span>
              {historyOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            </button>
            {historyOpen && (
              <div className="space-y-0.5">
                {unpinnedChats.map(c => <ChatItem key={c.id} c={c} />)}
                {unpinnedChats.length === 0 && (
                  <p className="px-3 py-4 text-xs text-white/20 text-center">No chats yet</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Main Chat Area ───────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col h-full min-w-0">

        {/* Messages */}
        <div className="flex-1 overflow-y-auto [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.08)_transparent]">
          {liveMessages.length === 0 ? (
            /* ── Empty state ──── */
            <div className="h-full flex flex-col items-center justify-center px-8 text-center">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-5">
                <Sparkles size={22} className="text-primary/70" />
              </div>
              <h2 className="text-xl font-semibold text-white/80 mb-1">How can I help?</h2>
              <p className="text-sm text-white/30 mb-8">Ask anything or pick a quick action below.</p>
              <div className="grid grid-cols-2 gap-2 w-full max-w-md">
                {QUICK_ACTIONS.map(({ label, prompt }) => (
                  <button key={label} onClick={() => setInputValue(prompt)}
                    className="text-left px-4 py-3 rounded-xl bg-white/[0.04] hover:bg-white/[0.07] border border-white/[0.06] hover:border-white/10 text-white/55 hover:text-white/80 text-sm transition-all">
                    {label}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="px-5 py-5 flex flex-col">
              <AnimatePresence initial={false}>
                {liveMessages.map((msg, idx) => {
                  const isAI     = msg.sender?.toUpperCase() === 'PRIMNOX';
                  const prevIsAI = liveMessages[idx - 1]?.sender?.toUpperCase() === 'PRIMNOX';
                  const isFirst  = idx === 0 || prevIsAI !== isAI; // first in a run

                  return (
                    <motion.div
                      key={idx}
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ duration: 0.2, ease: 'easeOut' }}
                      className={isFirst ? 'mt-5 first:mt-0' : 'mt-0.5'}
                    >
                      {isAI ? (
                        /* ── AI message ── */
                        <div className="flex gap-2.5 items-start group">
                          {/* Avatar — only on the first message in a run */}
                          <div className="w-6 shrink-0 mt-0.5">
                            {isFirst && (
                              <div className="w-6 h-6 rounded-full bg-primary/15 border border-primary/25 flex items-center justify-center">
                                <Terminal size={11} className="text-primary/70" />
                              </div>
                            )}
                          </div>

                          <div className="flex-1 min-w-0">
                            {isFirst && (
                              <p className="text-[10px] font-mono text-primary/40 uppercase tracking-widest mb-1 select-none">Primnox</p>
                            )}
                            {msg.isTyping && !msg.text ? (
                              <TypingDots />
                            ) : (
                              <div className="text-sm leading-6 text-white/80 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{msg.text || ''}</ReactMarkdown>
                              </div>
                            )}
                            {msg.timestamp && (
                              <p className="text-[10px] text-white/15 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                {relativeTime(msg.timestamp)}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        /* ── User message ── */
                        <div className="flex justify-end group">
                          <div className="max-w-[65%]">
                            <div className="bg-white/[0.07] border border-white/[0.08] rounded-2xl rounded-br-sm px-4 py-2.5">
                              <p className="text-sm text-white/90 leading-6 break-words whitespace-pre-wrap">{msg.text}</p>
                            </div>
                            {msg.timestamp && (
                              <p className="text-[10px] text-white/15 mt-1 text-right opacity-0 group-hover:opacity-100 transition-opacity">
                                {relativeTime(msg.timestamp)}
                              </p>
                            )}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  );
                })}
              </AnimatePresence>
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>

        {/* ── Input Bar ───────────────────────────────────────────────────── */}
        <div className="shrink-0 px-5 py-4 border-t border-white/[0.05]">
          <div>
            {/* Attached file pill */}
            <AnimatePresence>
              {attachedFile && (
                <motion.div initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                  animate={{ opacity: 1, height: 'auto', marginBottom: 8 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  className="flex items-center gap-2 w-fit">
                  <div className="flex items-center gap-2 bg-primary/10 text-primary border border-primary/20 px-3 py-1.5 rounded-full text-xs font-medium">
                    <Paperclip size={11} />
                    <span className="max-w-[200px] truncate">{attachedFile.name}</span>
                    <button onClick={removeAttachedFile} className="hover:text-white transition-colors ml-0.5">
                      <X size={11} />
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input row */}
            <div className="flex items-end gap-3 bg-white/[0.04] border border-white/[0.08] rounded-2xl px-4 py-3 focus-within:border-white/15 transition-colors">
              <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileChange} />

              <button onClick={() => fileInputRef.current?.click()}
                className="p-1.5 text-white/20 hover:text-white/60 transition-colors shrink-0 self-end mb-0.5"
                title="Attach file">
                <Paperclip size={17} />
              </button>

              <textarea
                value={inputValue}
                onChange={e => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'; }}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); } }}
                rows={1}
                className="flex-1 bg-transparent border-none focus:ring-0 text-white/90 placeholder-white/20 text-sm resize-none overflow-y-auto leading-6 min-h-[24px] max-h-[160px] py-0 outline-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                placeholder="Message Primnox…"
              />

              <button onClick={handleSend}
                disabled={!inputValue.trim() && !attachedFile}
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0 self-end
                  disabled:bg-white/5 disabled:text-white/15 disabled:cursor-not-allowed
                  enabled:bg-primary enabled:text-black enabled:hover:bg-white enabled:active:scale-90">
                <ArrowUp size={16} strokeWidth={2.5} />
              </button>
            </div>
            <p className="text-[10px] text-white/15 text-center mt-2.5">Enter to send · Shift+Enter for new line</p>
          </div>
        </div>
      </div>
    </div>
  );
};
