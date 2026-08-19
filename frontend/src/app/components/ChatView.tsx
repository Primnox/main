import { useState, useEffect, useRef, ChangeEvent } from 'react';
import { createPortal } from 'react-dom';
import { motion, AnimatePresence } from 'motion/react';
import { Paperclip, ArrowUp, Sparkles, X, Plus, MessageSquare, Pin, Folder, FolderPlus, ChevronDown, ChevronRight, Trash2, Bot, Pencil, Check, Copy, Terminal, FileText, ShieldCheck, RefreshCw, Cpu, Plug } from 'lucide-react';
import {
  BUILTIN_PROVIDERS, useProviderModels, selectedProviderKeyFor, type CustomProvider,
} from '../hooks/useProviderModels';
import { Select } from './settings/primitives';
import { StructuredBlock } from './StructuredBlock';
import { SkillActivity } from './SkillActivity';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
// Prism "light" build: only the languages we register below are bundled,
// instead of the full ~100+ language grammar set the default `Prism` export
// pulls in (hundreds of KB of unused parsers).
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism-light';
import oneDark from 'react-syntax-highlighter/dist/esm/styles/prism/one-dark';
import jsx from 'react-syntax-highlighter/dist/esm/languages/prism/jsx';
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json from 'react-syntax-highlighter/dist/esm/languages/prism/json';
import css from 'react-syntax-highlighter/dist/esm/languages/prism/css';
import markup from 'react-syntax-highlighter/dist/esm/languages/prism/markup'; // html/xml
import yaml from 'react-syntax-highlighter/dist/esm/languages/prism/yaml';
import sql from 'react-syntax-highlighter/dist/esm/languages/prism/sql';
import { API_BASE } from '../../config';

SyntaxHighlighter.registerLanguage('jsx', jsx);
SyntaxHighlighter.registerLanguage('tsx', tsx);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('ts', typescript);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('py', python);
SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('sh', bash);
SyntaxHighlighter.registerLanguage('shell', bash);
SyntaxHighlighter.registerLanguage('json', json);
SyntaxHighlighter.registerLanguage('css', css);
SyntaxHighlighter.registerLanguage('html', markup);
SyntaxHighlighter.registerLanguage('xml', markup);
SyntaxHighlighter.registerLanguage('yaml', yaml);
SyntaxHighlighter.registerLanguage('yml', yaml);
SyntaxHighlighter.registerLanguage('sql', sql);

// `prism-light` throws if asked to highlight a language that wasn't
// registered above. Fall back to plain markup highlighting (still gives
// nice quoting/braces) for anything we didn't explicitly add.
const REGISTERED_LANGS = new Set([
  'jsx', 'tsx', 'typescript', 'ts', 'javascript', 'js', 'python', 'py',
  'bash', 'sh', 'shell', 'json', 'css', 'html', 'xml', 'yaml', 'yml', 'sql',
]);

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
    <div className="my-3 rounded-xl overflow-hidden border border-on-surface/10 bg-surface/60">
      <div className="flex items-center justify-between px-4 py-2 border-b border-on-surface/5 bg-on-surface/[0.03]">
        <span className="text-[9px] font-mono text-on-surface/55 uppercase tracking-widest">{language}</span>
        <button onClick={copy}
          className="flex items-center gap-1.5 text-[9px] font-mono uppercase tracking-widest text-on-surface/55 hover:text-primary transition-colors active:scale-95">
          {copied ? <><Check size={11} /> Copied</> : <><Copy size={11} /> Copy</>}
        </button>
      </div>
      <SyntaxHighlighter
        language={REGISTERED_LANGS.has((language || '').toLowerCase()) ? language : 'markup'}
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
        <code className="bg-on-surface/10 text-primary/90 px-1.5 py-0.5 rounded-md text-[0.82em] font-mono" {...props}>
          {children}
        </code>
      );
    }
    return <CodeBlock language={lang || 'text'} value={text} />;
  },
  pre({ children }: any) { return <>{children}</>; },
  p({ children }: any) {
    return <p className="mb-3 last:mb-0 leading-7 text-on-surface/85">{children}</p>;
  },
  ul({ children }: any) {
    return <ul className="mb-3 space-y-1 pl-5 list-disc text-on-surface/85">{children}</ul>;
  },
  ol({ children }: any) {
    return <ol className="mb-3 space-y-1 pl-5 list-decimal text-on-surface/85">{children}</ol>;
  },
  li({ children }: any) {
    return <li className="leading-7">{children}</li>;
  },
  h1({ children }: any) { return <h1 className="text-xl font-bold text-on-surface mb-3 mt-4">{children}</h1>; },
  h2({ children }: any) { return <h2 className="text-base font-bold text-on-surface mb-2 mt-3">{children}</h2>; },
  h3({ children }: any) { return <h3 className="text-sm font-semibold text-on-surface/90 mb-2 mt-3">{children}</h3>; },
  strong({ children }: any) { return <strong className="font-semibold text-on-surface">{children}</strong>; },
  a({ href, children }: any) { return <a href={href} className="text-primary underline underline-offset-2 hover:text-primary/70 transition-colors">{children}</a>; },
  blockquote({ children }: any) {
    return <blockquote className="border-l-2 border-on-surface/20 pl-4 my-2 text-on-surface/50 italic">{children}</blockquote>;
  },
  table({ children }: any) {
    return (
      <div className="my-3 overflow-x-auto rounded-xl border border-on-surface/10">
        <table className="w-full text-xs">{children}</table>
      </div>
    );
  },
  th({ children }: any) { return <th className="px-4 py-2 text-left font-semibold text-on-surface/60 bg-on-surface/5 border-b border-on-surface/10">{children}</th>; },
  td({ children }: any) { return <td className="px-4 py-2 text-on-surface/75 border-b border-on-surface/5">{children}</td>; },
  hr() { return <hr className="my-4 border-on-surface/10" />; },
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

// ── Privacy Mirror reveal ─────────────────────────────────────────────────────
// Shows exactly what was pseudonymized before this turn left the device. The map
// lives only on this machine — it's the user's own data shown back to them. Starts
// collapsed as a lock chip; expands to the redaction diff.
interface ScrubItem { original: string; placeholder: string; label: string; }
const PrivacyMirrorBlock = ({ data }: { data: { mapping?: ScrubItem[]; model?: string } }) => {
  const [open, setOpen] = useState(false);
  const items = data?.mapping ?? [];
  if (!items.length) return null;
  return (
    <div className="mb-2 rounded-xl border border-success/15 bg-success/25/[0.04] overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-success/25/[0.06] transition-colors"
      >
        <ShieldCheck size={13} className="text-success/70 shrink-0" />
        <span className="text-[10px] font-mono uppercase tracking-widest text-success/60">
          Privacy Mirror · {items.length} scrubbed
        </span>
        {data?.model && (
          <span className="text-[9px] font-mono text-on-surface/48 truncate">→ {data.model}</span>
        )}
        <ChevronDown
          size={12}
          className={`ml-auto text-success/60 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>
      {open && (
        <div className="px-3 pb-2.5 pt-1 space-y-1 border-t border-success/10">
          <p className="text-[10px] text-on-surface/55 leading-5 pt-1">
            Replaced before leaving your device — restored in the reply below.
          </p>
          {items.map((it, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px] font-mono">
              <span className="text-error/70 line-through truncate max-w-[45%]">{it.original}</span>
              <span className="text-on-surface/48">→</span>
              <span className="text-success/80 truncate">{it.placeholder}</span>
              <span className="ml-auto text-[9px] uppercase tracking-wider text-on-surface/48 shrink-0">{it.label}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

// ── Typing dots ───────────────────────────────────────────────────────────────
/** What an answered Allow/Deny card turns into. The buttons are removed once
 *  answered, so without this the card would just lose its controls and leave
 *  no record of what the user actually chose. */
const PermissionOutcome = ({ state }: { state: 'allowed' | 'denied' | 'failed' }) => {
  const { Icon, label, tone } = state === 'allowed'
    ? { Icon: ShieldCheck, label: 'Allowed', tone: 'text-primary' }
    : state === 'denied'
      ? { Icon: X, label: 'Denied', tone: 'text-on-surface/50' }
      : { Icon: X, label: "Couldn't send your answer", tone: 'text-red-400' };
  return (
    <div className={`flex items-center gap-1.5 mt-1.5 text-[11px] font-medium ${tone}`}>
      <Icon size={13} />
      <span>{label}</span>
    </div>
  );
};

const TypingDots = () => (
  <div className="flex items-center gap-1.5 py-1">
    {[0, 1, 2].map(i => (
      <motion.div
        key={i}
        className="w-1.5 h-1.5 rounded-full bg-on-surface/30"
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

// ── User message: renders file attachment chips ────────────────────────────────
const FILE_CHIP_RE = /\[📎\s*(.+?)\]/g;

const UserMessage = ({ text }: { text: string }) => {
  const chips: string[] = [];
  let clean = text;
  let match;
  while ((match = FILE_CHIP_RE.exec(text)) !== null) {
    chips.push(match[1]);
  }
  if (chips.length > 0) {
    clean = text.replace(FILE_CHIP_RE, '').trim();
  }
  return (
    <>
      {clean && <p className="text-sm text-on-surface/90 leading-6 break-words whitespace-pre-wrap">{clean}</p>}
      {chips.length > 0 && (
        <div className={`flex flex-wrap gap-1.5 ${clean ? 'mt-2' : ''}`}>
          {chips.map((name, i) => (
            <span key={i} className="inline-flex items-center gap-1.5 bg-on-surface/[0.06] border border-on-surface/[0.08] text-on-surface/60 px-2.5 py-1 rounded-lg text-xs font-medium">
              <FileText size={12} className="text-on-surface/55 shrink-0" />
              <span className="max-w-[180px] truncate">{name}</span>
            </span>
          ))}
        </div>
      )}
    </>
  );
};

// ── Main component ─────────────────────────────────────────────────────────────
export const ChatExpandedSidebar = ({
  aiName: _aiName,
  userName: _userName,
  setStatus,
  liveMessages = [],
  sendMessage = () => {},
  respondToPermission = () => {},
  chatSessions = [],
  chatFolders = [],
  activeChatId = 'current',
  loadChat = () => {},
  createNewChat = () => {},
  refreshChats = () => {},
  privacyScrub = null,
  activeModel = 'Groq_Llama_3',
  activeCustomProviderId = '',
  quickSetProviderAndModel = () => {},
  apiKey = '', openaiApiKey = '', anthropicApiKey = '', geminiApiKey = '',
  groqModel = '', openaiModel = '', anthropicModel = '', geminiModel = '',
  customProviders = [],
}: {
  aiName: string,
  userName: string,
  setStatus: (s: AiStatus) => void,
  liveMessages?: any[],
  sendMessage?: (text: string, sessionId?: string, files?: File[] | null) => void,
  respondToPermission?: (token: string, allow: boolean) => void,
  chatSessions?: any[],
  chatFolders?: any[],
  activeChatId?: string,
  loadChat?: (id: string) => void,
  createNewChat?: () => void,
  refreshChats?: () => void,
  privacyScrub?: { mapping: { original: string; placeholder: string; label: string }[]; model: string } | null,
  activeModel?: string,
  activeCustomProviderId?: string,
  quickSetProviderAndModel?: (providerKey: string, modelValue?: string) => void,
  apiKey?: string, openaiApiKey?: string, anthropicApiKey?: string, geminiApiKey?: string,
  groqModel?: string, openaiModel?: string, anthropicModel?: string, geminiModel?: string,
  customProviders?: CustomProvider[],
}) => {
  const fileInputRef   = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue]   = useState('');
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  // ── In-chat model switcher ────────────────────────────────────────────
  const [modelPickerOpen, setModelPickerOpen] = useState(false);
  const selectedProviderKey = selectedProviderKeyFor(activeModel, activeCustomProviderId);
  const [pickerProviderKey, setPickerProviderKey] = useState(selectedProviderKey);
  useEffect(() => { if (modelPickerOpen) setPickerProviderKey(selectedProviderKey); }, [modelPickerOpen, selectedProviderKey]);

  const { providerModelsCache, detectingProvider, detectModelsFor } = useProviderModels({
    apiKeys: { groq: apiKey, openai: openaiApiKey, anthropic: anthropicApiKey, gemini: geminiApiKey },
    customProviders,
  });
  useEffect(() => {
    if (!modelPickerOpen || !pickerProviderKey) return;
    if (providerModelsCache[pickerProviderKey]) return;
    detectModelsFor(pickerProviderKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelPickerOpen, pickerProviderKey]);

  const currentModelLabel = (): string => {
    if (activeModel === 'Custom') {
      const p = customProviders.find(p => p.id === activeCustomProviderId);
      return p ? `${p.name} · ${p.model || '—'}` : 'Custom';
    }
    const builtin = BUILTIN_PROVIDERS.find(p => p.activeModel === activeModel);
    const model = selectedProviderKey === 'groq' ? groqModel : selectedProviderKey === 'openai' ? openaiModel
      : selectedProviderKey === 'anthropic' ? anthropicModel : selectedProviderKey === 'gemini' ? geminiModel : '';
    return builtin ? `${builtin.label}${model ? ` · ${model}` : ''}` : activeModel.replace(/_/g, ' ');
  };
  const pickerCurrentModel = (): string => {
    if (pickerProviderKey === 'groq') return groqModel;
    if (pickerProviderKey === 'openai') return openaiModel;
    if (pickerProviderKey === 'anthropic') return anthropicModel;
    if (pickerProviderKey === 'gemini') return geminiModel;
    return customProviders.find(p => p.id === pickerProviderKey)?.model || '';
  };

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
    const end = messagesEndRef.current;
    if (!end) return;
    // liveMessages changes on every token flush (~10x/second while streaming),
    // and this used to scroll unconditionally each time — so scrolling up to
    // re-read anything mid-reply was impossible, the view snapped back within
    // 100ms, and the competing smooth-scrolls fought each other. Follow the
    // stream only while the user is already parked at the bottom; the moment
    // they read up, leave their scroll position alone.
    let scroller = end.parentElement;
    while (scroller && scroller.scrollHeight <= scroller.clientHeight + 1) {
      scroller = scroller.parentElement;
    }
    if (scroller) {
      const distanceFromBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
      if (distanceFromBottom > 120) return;
    }
    end.scrollIntoView({ behavior: 'smooth' });
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
        await fetch(`${API_BASE}/api/chats/${chat.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ isPinned: !chat.isPinned })
        });
      } else if (action === 'rename') {
        setRenameState({ chatId: chat.id, value: chat.title }); return;
      } else if (action === 'move') {
        await fetch(`${API_BASE}/api/chats/${chat.id}`, {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folderId })
        });
      } else if (action === 'auto_assign') {
        await fetch(`${API_BASE}/api/chats/${chat.id}/auto_assign`, { method: 'POST' });
      } else if (action === 'delete') {
        await fetch(`${API_BASE}/api/chats/${chat.id}`, { method: 'DELETE' });
      }
      refreshChats();
    } catch (e) { console.error(e); }
  };

  const submitRename = async () => {
    if (!renameState || !renameState.value.trim()) { setRenameState(null); return; }
    try {
      const res = await fetch(`${API_BASE}/api/chats/${renameState.chatId}`, {
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
      await fetch(`${API_BASE}/api/folders`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: name }),
      });
      setNewFolderName(''); setCreatingFolder(false); refreshChats();
    } catch (e) { console.error(e); }
  };

  const deleteFolder = async (folderId: string) => {
    try {
      await fetch(`${API_BASE}/api/folders/${folderId}`, { method: 'DELETE' });
      if (activeFolderId === folderId) setActiveFolderId(null);
      refreshChats();
    } catch (e) { console.error(e); }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setAttachedFiles(prev => [...prev, ...Array.from(e.target.files!)]);
      setStatus('copy');
    }
  };

  const removeAttachedFile = (index: number) => {
    setAttachedFiles(prev => prev.filter((_, i) => i !== index));
    if (attachedFiles.length <= 1) {
      if (fileInputRef.current) fileInputRef.current.value = '';
      setStatus('idle');
    }
  };

  const clearAttachedFiles = () => {
    setAttachedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
  };

  const handleSend = async () => {
    if (!inputValue.trim() && attachedFiles.length === 0) return;
    // Capture values before clearing — clear immediately for responsive feel
    const text = inputValue;
    const files = attachedFiles.length > 0 ? [...attachedFiles] : null;
    setInputValue('');
    setAttachedFiles([]);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
    try {
      await sendMessage(text, activeChatId, files);
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
            ? 'bg-primary/15 text-on-surface'
            : 'hover:bg-on-surface/5 text-on-surface/55 hover:text-on-surface/85'}`}
      >
        <MessageSquare size={13} className={`mt-0.5 shrink-0 ${isActive ? 'text-primary/70' : 'text-on-surface/48 group-hover:text-on-surface/60'}`} />
        <div className="flex-1 min-w-0">
          <p className="text-sm truncate font-medium leading-snug">{c.title}</p>
          <p className="text-[10px] mt-0.5 text-on-surface/52">{sidebarDate(c.date)}</p>
        </div>
        {c.isPinned && <Pin size={10} className="shrink-0 mt-1 text-primary/60" />}
      </button>
    );
  };

  // ── Drag & Drop ──────────────────────────────────────────────────────────
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounter.current += 1;
    if (e.dataTransfer.types.includes('Files')) setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) { setIsDragging(false); dragCounter.current = 0; }
  };
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
  };
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation();
    setIsDragging(false);
    dragCounter.current = 0;
    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length > 0) {
      setAttachedFiles(prev => [...prev, ...droppedFiles]);
      setStatus('copy');
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex h-full bg-surface overflow-hidden">

      {/* ── Context Menu ────────────────────────────────────────────────── */}
      {contextMenu && createPortal(
        <div
          className="fixed z-50 bg-[var(--nav-bg)] border border-on-surface/10 rounded-2xl shadow-2xl backdrop-blur-2xl py-1.5 w-52 text-sm overflow-hidden"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={e => e.stopPropagation()}
        >
          <p className="px-4 py-2 border-b border-on-surface/5 font-semibold text-on-surface/80 truncate text-xs">{contextMenu.chat.title}</p>
          {[
            { action: 'pin', icon: Pin, label: contextMenu.chat.isPinned ? 'Unpin' : 'Pin to top' },
            { action: 'rename', icon: Pencil, label: 'Rename' },
          ].map(({ action, icon: Icon, label }) => (
            <button key={action} onClick={() => handleMenuAction(action, contextMenu.chat)}
              className="w-full text-left px-4 py-2.5 hover:bg-on-surface/8 text-on-surface/70 hover:text-on-surface flex items-center gap-3 transition-colors">
              <Icon size={13} /> {label}
            </button>
          ))}
          <div className="group/sub relative">
            <button className="w-full text-left px-4 py-2.5 hover:bg-on-surface/8 text-on-surface/70 hover:text-on-surface flex items-center justify-between transition-colors">
              <span className="flex items-center gap-3"><Folder size={13} /> Move to folder</span>
              <ChevronRight size={13} />
            </button>
            <div className="absolute left-full top-0 hidden group-hover/sub:block w-52 bg-[var(--nav-bg)] border border-on-surface/10 rounded-2xl shadow-2xl backdrop-blur-2xl py-1.5 ml-1">
              <button onClick={() => handleMenuAction('auto_assign', contextMenu.chat)}
                className="w-full text-left px-4 py-2.5 hover:bg-on-surface/8 text-primary flex items-center gap-3 transition-colors">
                <Bot size={13} /> Auto-detect
              </button>
              <div className="h-px bg-on-surface/10 my-1" />
              {chatFolders.map((f: any) => (
                <button key={f.id} onClick={() => handleMenuAction('move', contextMenu.chat, f.id)}
                  className="w-full text-left px-4 py-2.5 hover:bg-on-surface/8 text-on-surface/70 hover:text-on-surface truncate text-xs transition-colors">
                  {f.title}
                </button>
              ))}
            </div>
          </div>
          <div className="h-px bg-on-surface/8 my-1" />
          <button onClick={() => handleMenuAction('delete', contextMenu.chat)}
            className="w-full text-left px-4 py-2.5 hover:bg-error/15 text-error/80 hover:text-error flex items-center gap-3 transition-colors">
            <Trash2 size={13} /> Delete
          </button>
        </div>,
        document.body
      )}

      {/* ── Rename Modal ─────────────────────────────────────────────────── */}
      {renameState && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-surface/70 backdrop-blur-sm"
          onClick={() => setRenameState(null)}>
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }}
            className="bg-surface-container border border-on-surface/10 rounded-2xl shadow-2xl p-6 w-96"
            onClick={e => e.stopPropagation()}>
            <p className="text-xs font-semibold text-on-surface/50 uppercase tracking-widest mb-4">Rename Chat</p>
            <input ref={renameInputRef} value={renameState.value}
              onChange={e => setRenameState({ ...renameState, value: e.target.value })}
              onKeyDown={e => { if (e.key === 'Enter') submitRename(); if (e.key === 'Escape') setRenameState(null); }}
              className="w-full bg-on-surface/5 border border-on-surface/10 rounded-xl px-4 py-3 text-on-surface text-sm focus:outline-none focus:border-primary/50 transition-colors"
            />
            <div className="flex gap-2 mt-4">
              <button onClick={submitRename}
                className="flex-1 flex items-center justify-center gap-2 bg-primary text-surface font-bold px-4 py-2.5 rounded-xl text-sm hover:bg-on-surface transition-all">
                <Check size={14} /> Save
              </button>
              <button onClick={() => setRenameState(null)}
                className="px-4 py-2.5 rounded-xl text-sm text-on-surface/60 hover:text-on-surface hover:bg-on-surface/8 transition-all">
                Cancel
              </button>
            </div>
          </motion.div>
        </div>,
        document.body
      )}

      {/* ── Left Sidebar ─────────────────────────────────────────────────── */}
      <div className="w-64 border-r border-on-surface/5 bg-[var(--nav-bg)] flex flex-col shrink-0 overflow-hidden">
        {/* New Chat */}
        <div className="p-4 pt-10 border-b border-on-surface/5">
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
              <p className="px-3 text-[10px] font-mono text-on-surface/52 uppercase tracking-widest mb-2 flex items-center gap-2">
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
                className="flex items-center gap-2 text-[10px] font-mono text-on-surface/52 uppercase tracking-widest hover:text-on-surface/60 transition-colors">
                <Folder size={10} /> Folders
                {foldersOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
              </button>
              <button onClick={() => { setCreatingFolder(true); setFoldersOpen(true); }}
                className="text-on-surface/48 hover:text-primary/70 transition-colors" title="New folder">
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
                      className="flex-1 bg-on-surface/5 border border-on-surface/10 rounded-lg px-3 py-1.5 text-xs text-on-surface placeholder-on-surface/20 outline-none focus:border-primary/50"
                    />
                    <button onClick={createFolder} className="text-primary hover:text-on-surface transition-colors p-1"><Check size={12} /></button>
                    <button onClick={() => { setCreatingFolder(false); setNewFolderName(''); }} className="text-on-surface/52 hover:text-on-surface/60 transition-colors p-1"><X size={12} /></button>
                  </div>
                )}
                {chatFolders.map((f: any) => (
                  <div key={f.id} className={`flex items-center group rounded-xl transition-all ${activeFolderId === f.id ? 'bg-on-surface/8' : 'hover:bg-on-surface/5'}`}>
                    <button onClick={() => { setActiveFolderId(f.id); setHistoryOpen(true); }}
                      className={`flex-1 text-left px-3 py-2.5 text-sm flex items-center gap-2.5 ${activeFolderId === f.id ? 'text-primary' : 'text-on-surface/55 group-hover:text-on-surface/85'}`}>
                      <Folder size={13} className={activeFolderId === f.id ? 'text-primary/70' : 'text-on-surface/48'} />
                      <span className="truncate flex-1">{f.title}</span>
                      <span className="text-[10px] text-on-surface/52 shrink-0">{f.count}</span>
                    </button>
                    <button onClick={() => deleteFolder(f.id)}
                      aria-label={`Delete folder ${f.title}`}
                      className="pr-2.5 opacity-0 group-hover:opacity-100 text-on-surface/48 hover:text-error/80 transition-all">
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
                ${activeFolderId === null ? 'text-on-surface/50' : 'text-on-surface/52 hover:text-on-surface/50'}`}>
              <span className="flex items-center gap-2">
                <MessageSquare size={10} /> {activeFolderId ? 'Back to recent' : 'Recent'}
              </span>
              {historyOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
            </button>
            {historyOpen && (
              <div className="space-y-0.5">
                {unpinnedChats.map(c => <ChatItem key={c.id} c={c} />)}
                {unpinnedChats.length === 0 && (
                  <p className="px-3 py-4 text-xs text-on-surface/48 text-center">Nothing here yet</p>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Main Chat Area ───────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col h-full min-w-0 relative"
        onDragEnter={handleDragEnter}
        onDragLeave={handleDragLeave}
        onDragOver={handleDragOver}
        onDrop={handleDrop}
      >

        {/* Drop overlay */}
        <AnimatePresence>
          {isDragging && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="absolute inset-0 z-40 bg-surface/70 backdrop-blur-sm border-2 border-dashed border-primary/50 rounded-2xl flex flex-col items-center justify-center gap-3 pointer-events-none"
            >
              <motion.div
                animate={{ scale: [1, 1.1, 1] }}
                transition={{ repeat: Infinity, duration: 1.5, ease: 'easeInOut' }}
                className="w-14 h-14 rounded-2xl bg-primary/15 border border-primary/30 flex items-center justify-center"
              >
                <Paperclip size={24} className="text-primary" />
              </motion.div>
              <p className="text-sm font-medium text-on-surface/70">Drop files here</p>
              <p className="text-[11px] text-on-surface/55">PDF, images, code, text — anything</p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto [scrollbar-width:thin] [scrollbar-color:var(--scroll)_transparent]">
          {liveMessages.length === 0 ? (
            /* ── Empty state ──── */
            <div className="h-full flex flex-col items-center justify-center px-8 text-center">
              <div className="w-12 h-12 rounded-2xl bg-primary/10 border border-primary/20 flex items-center justify-center mb-5">
                <Sparkles size={22} className="text-primary/70" />
              </div>
              <h2 className="text-xl font-semibold text-on-surface/80 mb-1">Right, what are we doing?</h2>
              <p className="text-sm text-on-surface/55 mb-8">Everything here stays local until you say otherwise.</p>
              <div className="grid grid-cols-2 gap-2 w-full max-w-md">
                {QUICK_ACTIONS.map(({ label, prompt }) => (
                  <button key={label} onClick={() => setInputValue(prompt)}
                    className="text-left px-4 py-3 rounded-xl bg-on-surface/[0.04] hover:bg-on-surface/[0.07] border border-on-surface/[0.06] hover:border-on-surface/10 text-on-surface/55 hover:text-on-surface/80 text-sm transition-all">
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
                              <p className="text-[10px] font-mono text-primary/60 uppercase tracking-widest mb-1 select-none">Primnox</p>
                            )}
                            {msg.privacyScrub && <PrivacyMirrorBlock data={msg.privacyScrub} />}
                            {!!msg.activity?.length && <SkillActivity phases={msg.activity} />}
                            {msg.isTyping && !msg.text ? (
                              <TypingDots />
                            ) : (
                              <div className="text-sm leading-6 text-on-surface/80 [&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
                                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{msg.text || ''}</ReactMarkdown>
                              </div>
                            )}
                            {!!msg.blocks?.length && (
                              <StructuredBlock
                                blocks={msg.blocks}
                                onAction={(action) => {
                                  const permMatch = /^permission:(.+):(allow|deny)$/.exec(action);
                                  if (permMatch) {
                                    respondToPermission(permMatch[1], permMatch[2] === 'allow');
                                  } else {
                                    sendMessage(action, activeChatId);
                                  }
                                }}
                              />
                            )}
                            {msg.permissionState && msg.permissionState !== 'pending' && (
                              <PermissionOutcome state={msg.permissionState} />
                            )}
                            {msg.timestamp && (
                              <p className="text-[10px] text-on-surface/42 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                {relativeTime(msg.timestamp)}
                              </p>
                            )}
                          </div>
                        </div>
                      ) : (
                        /* ── User message ── */
                        <div className="flex justify-end group">
                          <div className="max-w-[65%]">
                            <div className="bg-on-surface/[0.07] border border-on-surface/[0.08] rounded-2xl rounded-br-sm px-4 py-2.5">
                              <UserMessage text={msg.text || ''} />
                            </div>
                            {msg.timestamp && (
                              <p className="text-[10px] text-on-surface/42 mt-1 text-right opacity-0 group-hover:opacity-100 transition-opacity">
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
        <div className="shrink-0 px-5 py-4 border-t border-on-surface/[0.05]">
          <div>
            {/* Attached file pills */}
            <AnimatePresence>
              {attachedFiles.length > 0 && (
                <motion.div initial={{ opacity: 0, height: 0, marginBottom: 0 }}
                  animate={{ opacity: 1, height: 'auto', marginBottom: 8 }}
                  exit={{ opacity: 0, height: 0, marginBottom: 0 }}
                  className="flex flex-wrap items-center gap-2 w-full">
                  {attachedFiles.map((file, i) => (
                    <div key={`${file.name}-${i}`} className="flex items-center gap-2 bg-primary/10 text-primary border border-primary/20 px-3 py-1.5 rounded-full text-xs font-medium">
                      <Paperclip size={11} />
                      <span className="max-w-[200px] truncate">{file.name}</span>
                      <button onClick={() => removeAttachedFile(i)} className="hover:text-on-surface transition-colors ml-0.5">
                        <X size={11} />
                      </button>
                    </div>
                  ))}
                  {attachedFiles.length > 1 && (
                    <button onClick={clearAttachedFiles} className="text-[10px] text-on-surface/55 hover:text-error transition-colors">
                      Clear all
                    </button>
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* Input row */}
            <div className="flex items-end gap-3 bg-on-surface/[0.04] border border-on-surface/[0.08] rounded-2xl px-4 py-3 focus-within:border-on-surface/15 transition-colors">
              <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileChange} multiple />

              <button onClick={() => fileInputRef.current?.click()}
                className="p-1.5 text-on-surface/48 hover:text-on-surface/60 transition-colors shrink-0 self-end mb-0.5"
                title="Attach file">
                <Paperclip size={17} />
              </button>

              <textarea
                value={inputValue}
                onChange={e => { setInputValue(e.target.value); e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'; }}
                // isComposing guards IME input: while composing Japanese, Chinese
                // or Korean text, Enter confirms the candidate word. Without this
                // check that Enter also sent the message, so those users could
                // not finish a word without firing a half-written message.
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                rows={1}
                className="flex-1 bg-transparent border-none focus:ring-0 text-on-surface/90 placeholder-on-surface/20 text-sm resize-none overflow-y-auto leading-6 min-h-[24px] max-h-[160px] py-0 outline-none [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
                placeholder="Message Primnox…"
              />

              <button onClick={handleSend}
                disabled={!inputValue.trim() && attachedFiles.length === 0}
                aria-label="Send message"
                className="w-8 h-8 rounded-xl flex items-center justify-center transition-all shrink-0 self-end
                  disabled:bg-on-surface/5 disabled:text-on-surface/42 disabled:cursor-not-allowed
                  enabled:bg-primary enabled:text-surface enabled:hover:bg-on-surface enabled:active:scale-90">
                <ArrowUp size={16} strokeWidth={2.5} />
              </button>
            </div>
            <div className="flex items-center justify-center gap-2 mt-2.5">
              <p className="text-[10px] text-on-surface/42 text-center">Enter to send · Shift+Enter for new line</p>
              <div className="relative">
                <button
                  onClick={() => setModelPickerOpen(v => !v)}
                  className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-on-surface/[0.06] hover:bg-on-surface/[0.1] border border-on-surface/[0.08] text-on-surface/55 hover:text-on-surface/75 transition-colors text-[10px] font-mono max-w-[160px]"
                  title="Switch model"
                >
                  <Cpu size={10} className="shrink-0" />
                  <span className="truncate">{currentModelLabel()}</span>
                  <ChevronDown size={9} className="shrink-0" />
                </button>
                <AnimatePresence>
                  {modelPickerOpen && (
                    <>
                      <div className="fixed inset-0 z-40" onClick={() => setModelPickerOpen(false)} />
                      <motion.div
                        initial={{ opacity: 0, y: 6, scale: 0.97 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 6, scale: 0.97 }}
                        className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-64 rounded-xl border border-on-surface/10 bg-[var(--surface)] shadow-2xl p-3 z-50 space-y-3"
                      >
                        <div className="space-y-1">
                          {BUILTIN_PROVIDERS.map(p => (
                            <button
                              key={p.key}
                              onClick={() => setPickerProviderKey(p.key)}
                              className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-[11px] font-mono transition-colors ${
                                pickerProviderKey === p.key ? 'bg-primary/10 text-primary' : 'text-on-surface/65 hover:bg-on-surface/5'
                              }`}
                            >
                              {p.label}
                              {pickerProviderKey === p.key && <Check size={11} />}
                            </button>
                          ))}
                          {customProviders.map(p => (
                            <button
                              key={p.id}
                              onClick={() => setPickerProviderKey(p.id)}
                              className={`w-full flex items-center gap-1.5 justify-between px-2.5 py-1.5 rounded-lg text-[11px] font-mono transition-colors ${
                                pickerProviderKey === p.id ? 'bg-primary/10 text-primary' : 'text-on-surface/65 hover:bg-on-surface/5'
                              }`}
                            >
                              <span className="flex items-center gap-1.5 truncate"><Plug size={10} className="shrink-0" />{p.name}</span>
                              {pickerProviderKey === p.id && <Check size={11} className="shrink-0" />}
                            </button>
                          ))}
                        </div>

                        <div className="flex items-center gap-1.5 pt-2 border-t border-on-surface/10">
                          <div className="flex-1 min-w-0">
                            <Select
                              label="Model"
                              value={pickerCurrentModel()}
                              onChange={(v) => quickSetProviderAndModel(pickerProviderKey, v)}
                              options={(providerModelsCache[pickerProviderKey]?.models || []).map(m => ({ value: m, label: m }))}
                            />
                          </div>
                          <button
                            onClick={() => detectModelsFor(pickerProviderKey)}
                            className="p-1.5 text-on-surface/50 hover:text-on-surface transition-colors shrink-0"
                            title="Refresh model list"
                          >
                            <RefreshCw size={12} className={detectingProvider === pickerProviderKey ? 'animate-spin' : ''} />
                          </button>
                        </div>

                        {pickerProviderKey !== selectedProviderKey && (
                          <button
                            onClick={() => { quickSetProviderAndModel(pickerProviderKey); setModelPickerOpen(false); }}
                            className="w-full text-center py-1.5 rounded-lg bg-primary/10 text-primary text-[10px] font-mono uppercase tracking-wider hover:bg-primary/20 transition-colors"
                          >
                            Switch to this provider
                          </button>
                        )}
                      </motion.div>
                    </>
                  )}
                </AnimatePresence>
              </div>
              {privacyScrub && privacyScrub.mapping.length > 0 && (
                <PrivacyScrubIndicator scrub={privacyScrub} />
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

// Live proof of the privacy claim, not just a settings-page diagram: what
// actually got pseudonymized before this exchange left the device. The
// backend has computed this on every cloud send all along
// (ScrubSession.mapping in privacy_mirror.py, broadcast as `privacy_scrub`
// in core.py) — nothing on the frontend was rendering it.
const PrivacyScrubIndicator = ({ scrub }: { scrub: { mapping: { original: string; placeholder: string; label: string }[]; model: string } }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-success/10 border border-success/20 text-success/80 hover:text-success hover:border-success/40 transition-colors text-[10px] font-mono"
        title="What was scrubbed before this left your device"
      >
        <ShieldCheck size={10} />
        {scrub.mapping.length} scrubbed
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.97 }}
            className="absolute bottom-full right-0 mb-2 w-72 max-h-64 overflow-y-auto rounded-xl border border-on-surface/10 bg-[var(--surface)] shadow-2xl p-3 z-50"
          >
            <p className="text-[10px] font-mono uppercase tracking-widest text-on-surface/48 mb-2">
              Stayed on this device · {scrub.model || 'cloud model'} saw placeholders only
            </p>
            <div className="space-y-1.5">
              {scrub.mapping.map((m, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-xs">
                  <span className="text-on-surface/85 truncate">{m.original}</span>
                  <span className="shrink-0 flex items-center gap-1.5">
                    <span className="text-on-surface/30">→</span>
                    <span className="font-mono text-[10px] text-primary/80 bg-primary/10 border border-primary/20 rounded px-1.5 py-0.5">
                      {m.placeholder}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
