import { useState, useEffect, useRef, ChangeEvent } from 'react';
import { NotesIconSidebar } from './NotesView';
import { motion } from 'motion/react';
import { Terminal, User, Paperclip, ArrowRight, Sparkles, X, Plus, MessageSquare, Pin, Folder, ChevronDown, ChevronRight, Settings, History, Copy, Check } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import SyntaxHighlighter from 'react-syntax-highlighter/dist/esm/prism-light';
import oneDark from 'react-syntax-highlighter/dist/esm/styles/prism/one-dark';
import tsx from 'react-syntax-highlighter/dist/esm/languages/prism/tsx';
import typescript from 'react-syntax-highlighter/dist/esm/languages/prism/typescript';
import javascript from 'react-syntax-highlighter/dist/esm/languages/prism/javascript';
import python from 'react-syntax-highlighter/dist/esm/languages/prism/python';
import bash from 'react-syntax-highlighter/dist/esm/languages/prism/bash';
import json_lang from 'react-syntax-highlighter/dist/esm/languages/prism/json';
SyntaxHighlighter.registerLanguage('tsx', tsx);
SyntaxHighlighter.registerLanguage('typescript', typescript);
SyntaxHighlighter.registerLanguage('ts', typescript);
SyntaxHighlighter.registerLanguage('javascript', javascript);
SyntaxHighlighter.registerLanguage('js', javascript);
SyntaxHighlighter.registerLanguage('python', python);
SyntaxHighlighter.registerLanguage('py', python);
SyntaxHighlighter.registerLanguage('bash', bash);
SyntaxHighlighter.registerLanguage('sh', bash);
SyntaxHighlighter.registerLanguage('json', json_lang);

type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

// ── Markdown code-block renderer ──────────────────────────────────────────────

const REGISTERED = new Set(['tsx','typescript','ts','javascript','js','python','py','bash','sh','json']);

const CCCodeBlock = ({ language, value }: { language: string; value: string }) => {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(value).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  };
  return (
    <div className="my-2 rounded-xl overflow-hidden border border-on-surface/10 bg-surface/60">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-on-surface/5 bg-on-surface/[0.03]">
        <span className="text-[9px] font-mono text-on-surface/55 uppercase tracking-widest">{language}</span>
        <button onClick={copy} className="flex items-center gap-1 text-[9px] font-mono uppercase tracking-widest text-on-surface/55 hover:text-success transition-colors">
          {copied ? <><Check size={10} /> Copied</> : <><Copy size={10} /> Copy</>}
        </button>
      </div>
      <SyntaxHighlighter
        language={REGISTERED.has((language || '').toLowerCase()) ? language : 'markup'}
        style={oneDark}
        PreTag="div"
        customStyle={{ margin: 0, background: 'transparent', fontSize: '0.75rem', padding: '0.75rem' }}
      >
        {value}
      </SyntaxHighlighter>
    </div>
  );
};

const CC_MD_COMPONENTS = {
  code({ children, className, ...props }: any) {
    const lang = /language-(\w+)/.exec(className || '')?.[1];
    const text = String(children).replace(/\n$/, '');
    if (!lang && !text.includes('\n')) {
      return <code className="bg-on-surface/10 text-success/90 px-1.5 py-0.5 rounded text-[0.8em] font-mono" {...props}>{children}</code>;
    }
    return <CCCodeBlock language={lang || 'text'} value={text} />;
  },
  pre({ children }: any) { return <>{children}</>; },
  p({ children }: any) { return <p className="text-sm leading-relaxed text-on-surface/80 mb-1 last:mb-0">{children}</p>; },
  strong({ children }: any) { return <strong className="text-on-surface font-semibold">{children}</strong>; },
  a({ href, children }: any) { return <a href={href} target="_blank" rel="noreferrer" className="text-success underline hover:text-success">{children}</a>; },
  ul({ children }: any) { return <ul className="list-disc pl-4 space-y-0.5 text-sm text-on-surface/70">{children}</ul>; },
  ol({ children }: any) { return <ol className="list-decimal pl-4 space-y-0.5 text-sm text-on-surface/70">{children}</ol>; },
  li({ children }: any) { return <li className="leading-relaxed">{children}</li>; },
};

// ─────────────────────────────────────────────────────────────────────────────

export const CommandCenter = ({
  aiName,
  userName,
  setStatus,
  liveMessages = [],
  sendMessage = () => {},
  chatSessions = [],
  chatFolders = [],
  activeChatId = 'current',
  loadChat = () => {},
  notes = [],
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
  notes?: any[],
}) => {

  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState("");
  const [attachedFile, setAttachedFile] = useState<File | null>(null);

  // State for Left Sidebar
  const [foldersOpen, setFoldersOpen] = useState(true);
  const [historyOpen, setHistoryOpen] = useState(true);
  const [showLeftPane, setShowLeftPane] = useState(true);

  const pinnedChats = chatSessions.filter(c => c.isPinned);
  const unpinnedChats = chatSessions.filter(c => !c.isPinned);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [liveMessages]);

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setAttachedFile(e.target.files[0]);
      setStatus('copy');
    }
  };

  const removeAttachedFile = () => {
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
  };

  const handleSend = () => {
    if (!inputValue.trim() && !attachedFile) return;
    sendMessage(inputValue, activeChatId, attachedFile); // Send text with active session and file
    setInputValue("");
    setAttachedFile(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
    setStatus('idle');
  };

  return (
    <div className="flex-1 flex h-full bg-surface overflow-hidden">
      {/* LEFT CHAT SIDEBAR (History/Folders) */}
      <div className={`border-r border-on-surface/5 bg-[var(--surface)] flex flex-col pt-12 text-on-surface overflow-hidden shrink-0 transition-all duration-300 ${showLeftPane ? "w-64 lg:w-72 opacity-100" : "w-0 opacity-0 pointer-events-none"}`}>
        
        {/* Header & New Chat Button */}
        <div className="px-6 mb-6">
          <button onClick={() => loadChat('current')} className="w-full flex items-center justify-between p-3 bg-primary text-surface font-bold rounded-xl hover:bg-on-surface active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50 shadow-[0_0_20px_rgba(79,70,229,0.3)] group">
            <span className="text-sm">New Chat</span>
            <Plus size={18} className="group-hover:rotate-90 transition-transform" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-3 pb-8 space-y-6">
          
          {/* Pinned Section */}
          <div>
            <div className="px-3 text-[10px] font-mono text-on-surface/60 uppercase tracking-widest mb-2 flex items-center gap-2">
              <Pin size={12} /> Pinned
            </div>
            <div className="space-y-1">
              {pinnedChats.map((c: any) => (
                <button key={c.id} onClick={() => loadChat(c.id)} className={`w-full text-left p-3 rounded-lg text-sm active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50 group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-on-surface' : 'hover:bg-on-surface/5 text-on-surface/70'}`}>
                  <span className="truncate font-bold">{c.title}</span>
                  <span className="text-[10px] text-on-surface/60">{new Date(c.date).toLocaleDateString()}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Folders Section */}
          <div>
            <button onClick={() => setFoldersOpen(!foldersOpen)} className="w-full px-3 py-1 text-[10px] font-mono text-on-surface/60 uppercase tracking-widest mb-2 flex items-center justify-between hover:text-on-surface active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50">
              <div className="flex items-center gap-2"><Folder size={12} /> Folders</div>
              {foldersOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {foldersOpen && (
              <div className="space-y-1">
                {chatFolders.map((f: any) => (
                  <button key={f.id} className="w-full text-left p-3 rounded-lg text-sm hover:bg-on-surface/5 text-on-surface/70 active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50 flex items-center justify-between group">
                    <div className="flex items-center gap-3 truncate">
                      <Folder size={14} className="text-on-surface/55 group-hover:text-primary transition-colors" />
                      <span className="truncate">{f.title}</span>
                    </div>
                    <span className="text-[10px] bg-on-surface/10 px-2 py-0.5 rounded text-on-surface/50">{f.count}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* History Section */}
          <div>
             <button onClick={() => setHistoryOpen(!historyOpen)} className="w-full px-3 py-1 text-[10px] font-mono text-on-surface/60 uppercase tracking-widest mb-2 flex items-center justify-between hover:text-on-surface active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50">
              <div className="flex items-center gap-2"><MessageSquare size={12} /> Recent</div>
              {historyOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {historyOpen && (
              <div className="space-y-1">
                {unpinnedChats.map((c: any) => (
                  <button key={c.id} onClick={() => loadChat(c.id)} className={`w-full text-left p-3 rounded-lg text-sm active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50 group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-on-surface' : 'hover:bg-on-surface/5 text-on-surface/70'}`}>
                    <span className="truncate">{c.title}</span>
                    <span className="text-[10px] text-on-surface/60">{new Date(c.date).toLocaleDateString()}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Settings / Archive link bottom */}
        <div className="p-4 border-t border-on-surface/5">
           <button className="w-full flex items-center gap-3 text-on-surface/60 hover:text-on-surface text-xs p-2 rounded hover:bg-on-surface/5 active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50">
             <Settings size={14} /> View All Archives
           </button>
        </div>
      </div>

      {/* RIGHT MAIN CHAT AREA */}
      <div className="flex-1 flex flex-col h-full relative">
        <div 
          className="flex-1 overflow-y-auto p-8 lg:p-16 space-y-16 custom-scrollbar"
          style={{ maskImage: 'linear-gradient(to bottom, black 80%, transparent 100%)', WebkitMaskImage: 'linear-gradient(to bottom, black 80%, transparent 100%)' }}
        >
          {liveMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000 mt-20">
              <div className="w-24 h-24 rounded-full border border-on-surface/5 flex items-center justify-center relative mb-8">
                <div className="absolute inset-0 border border-primary/20 rounded-full animate-ping [animation-duration:3s]" />
                <Sparkles size={32} className="text-primary/60" />
              </div>
              <h1 className="text-3xl font-bold text-on-surface tracking-tighter mb-4 lowercase italic">Initialize Synapse Stream</h1>
              <p className="text-on-surface/60 max-w-md leading-relaxed mb-12 lowercase font-light">The neural interface is online and awaiting input. Send a command or attach a file to begin.</p>
              
              <div className="flex gap-4">
                <button onClick={() => setInputValue("Analyze my current workspace")} className="bg-on-surface/5 hover:bg-on-surface/10 text-on-surface/60 hover:text-on-surface px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50">Analyze Workspace</button>
                <button onClick={() => setInputValue("Summarize system status")} className="bg-on-surface/5 hover:bg-on-surface/10 text-on-surface/60 hover:text-on-surface px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50">System Status</button>
              </div>
            </div>
          ) : (
            liveMessages.map((msg, idx) => (
              <motion.div 
                key={idx}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex gap-8 max-w-4xl ${msg.sender?.toUpperCase() === 'PRIMNOX' ? '' : 'ml-auto flex-row-reverse'}`}
              >
                <div className={`w-12 h-12 flex items-center justify-center shrink-0 rounded-xl
                  ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'bg-primary/10 text-primary shadow-[0_0_20px_rgba(79,70,229,0.2)]' : 'bg-on-surface/5 text-on-surface/50 grayscale'}`}
                >
                  {msg.sender?.toUpperCase() === 'PRIMNOX' ? <Terminal size={22} /> : <User size={22} />}
                </div>
                <div className={`glass-panel p-6 rounded-3xl space-y-3 relative transition-all duration-700
                  ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'rounded-tl-none bg-[var(--surface)] shadow-[0_0_40px_rgba(79,70,229,0.15)] border border-primary/20' : 'rounded-tr-none bg-primary/5 shadow-2xl'}`}
                >
                   <div className={`flex justify-between items-center pb-3 mb-3 font-mono text-[11px] tracking-[0.2em]
                     ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'text-primary/60' : 'text-on-surface/60'}`}
                   >
                      <span className="uppercase font-bold">{msg.sender?.toUpperCase() === 'PRIMNOX' ? `PROTOCOL // ${aiName}_v2` : `OPERATOR // ${userName}`}</span>
                      <span className="opacity-40">{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}</span>
                   </div>
                   <ReactMarkdown components={CC_MD_COMPONENTS}>{msg.text}</ReactMarkdown>
                </div>
              </motion.div>
            ))
          )}
          <div ref={messagesEndRef} className="h-1" />
        </div>

        <footer className="p-8 lg:p-12 pt-0 z-20 pointer-events-auto shrink-0">
          <div className="max-w-4xl mx-auto flex items-center justify-between w-full gap-2">
            <button onClick={() => setShowLeftPane(!showLeftPane)} className="p-3 bg-surface-container rounded-2xl hover:bg-surface-container-high text-on-surface/50 hover:text-on-surface shrink-0 active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50" title="Toggle Chat History"><History size={20}/></button>
            <div className="flex-1 glass-panel rounded-3xl flex items-center p-4 group focus-within:shadow-[0_0_60px_rgba(79,70,229,0.2)] transition-all relative pointer-events-auto bg-[var(--nav-bg)] backdrop-blur-3xl">
            <div className="absolute -top-10 left-8 px-4 py-1 bg-surface-container rounded-full font-mono text-[9px] text-on-surface/55 uppercase tracking-[0.4em] opacity-0 group-focus-within:opacity-100 transition-all translate-y-2 group-focus-within:translate-y-0">Neural_Input_Active</div>
            
            <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileChange} />
            
            <button 
              onClick={() => fileInputRef.current?.click()}
              className="p-4 text-on-surface/48 hover:text-primary hover:bg-primary/10 rounded-2xl mr-2 group/btn active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50"
              title="Attach_File"
            >
              <Paperclip size={22} className="group-hover/btn:rotate-12 transition-transform" />
            </button>

            <input 
              role="textbox"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              className="flex-1 bg-transparent border-none focus:ring-0 text-on-surface placeholder-on-surface/10 text-sm px-6 font-light h-14" 
              placeholder="Stream thoughts or commands..."
            />
            
            {attachedFile && (
              <div className="flex items-center gap-2 bg-primary/20 text-primary px-3 py-1.5 rounded-xl mr-4 border border-primary/30">
                <span className="font-mono text-[11px] uppercase tracking-widest truncate max-w-[150px]">{attachedFile.name}</span>
                <button onClick={removeAttachedFile} className="hover:text-on-surface active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50"><X size={14} /></button>
              </div>
            )}

            <button 
              onClick={handleSend}
              className="bg-primary text-surface w-14 h-14 rounded-2xl flex items-center justify-center hover:bg-on-surface shadow-2xl group-hover:shadow-primary/40 disabled:opacity-50 disabled:active:scale-100 active:scale-95 transition-all duration-300 ease-out focus-visible:ring-1 focus-visible:ring-success/50"
              disabled={!inputValue.trim() && !attachedFile}
            >
              <ArrowRight size={26} strokeWidth={3} />
            </button>
            </div>
          </div>
        </footer>
      </div>

      {/* RIGHT WORKSPACE PANE */}
      <div className="w-80 lg:w-96 border-l border-on-surface/5 bg-surface flex flex-col h-full relative z-10 shrink-0">
        <NotesIconSidebar notes={notes} onExport={() => {}} />
      </div>
    </div>

  );
};
