import { useState, useEffect, useRef, ChangeEvent } from 'react';
import { motion } from 'motion/react';
import { Terminal, User, Paperclip, ArrowRight, Sparkles, X, Plus, MessageSquare, Pin, Folder, ChevronDown, ChevronRight, Settings, History } from 'lucide-react';

type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

export const CommandCenter = ({ 
  aiName, 
  userName, 
  setStatus,
  liveMessages = [],
  sendMessage = () => {},
  chatSessions = [],
  chatFolders = [],
  activeChatId = 'current',
  loadChat = () => {}
}: { 
  aiName: string, 
  userName: string, 
  setStatus: (s: AiStatus) => void,
  liveMessages?: any[],
  sendMessage?: (text: string, sessionId?: string, file?: File | null) => void,
  chatSessions?: any[],
  chatFolders?: any[],
  activeChatId?: string,
  loadChat?: (id: string) => void
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
    <div className="flex-1 flex h-full bg-zinc-950 overflow-hidden">
      {/* LEFT CHAT SIDEBAR (History/Folders) */}
      <div className={`border-r border-white/5 bg-zinc-900/20 flex flex-col pt-12 text-white overflow-hidden shrink-0 transition-all duration-300 ${showLeftPane ? "w-64 lg:w-72 opacity-100" : "w-0 opacity-0 pointer-events-none"}`}>
        
        {/* Header & New Chat Button */}
        <div className="px-6 mb-6">
          <button onClick={() => loadChat('current')} className="w-full flex items-center justify-between p-3 bg-primary text-black font-bold rounded-xl hover:bg-white transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)] group active:scale-95">
            <span className="text-sm">New Chat</span>
            <Plus size={18} className="group-hover:rotate-90 transition-transform" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto custom-scrollbar px-3 pb-8 space-y-6">
          
          {/* Pinned Section */}
          <div>
            <div className="px-3 text-[10px] font-mono text-white/40 uppercase tracking-widest mb-2 flex items-center gap-2">
              <Pin size={12} /> Pinned
            </div>
            <div className="space-y-1">
              {pinnedChats.map((c: any) => (
                <button key={c.id} onClick={() => loadChat(c.id)} className={`w-full text-left p-3 rounded-lg text-sm transition-all group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-white' : 'hover:bg-white/5 text-white/70'}`}>
                  <span className="truncate font-bold">{c.title}</span>
                  <span className="text-[10px] text-white/40">{new Date(c.date).toLocaleDateString()}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Folders Section */}
          <div>
            <button onClick={() => setFoldersOpen(!foldersOpen)} className="w-full px-3 py-1 text-[10px] font-mono text-white/40 uppercase tracking-widest mb-2 flex items-center justify-between hover:text-white transition-colors">
              <div className="flex items-center gap-2"><Folder size={12} /> Folders</div>
              {foldersOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {foldersOpen && (
              <div className="space-y-1">
                {chatFolders.map((f: any) => (
                  <button key={f.id} className="w-full text-left p-3 rounded-lg text-sm hover:bg-white/5 text-white/70 transition-all flex items-center justify-between group">
                    <div className="flex items-center gap-3 truncate">
                      <Folder size={14} className="text-white/30 group-hover:text-primary transition-colors" />
                      <span className="truncate">{f.title}</span>
                    </div>
                    <span className="text-[10px] bg-white/10 px-2 py-0.5 rounded text-white/50">{f.count}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* History Section */}
          <div>
             <button onClick={() => setHistoryOpen(!historyOpen)} className="w-full px-3 py-1 text-[10px] font-mono text-white/40 uppercase tracking-widest mb-2 flex items-center justify-between hover:text-white transition-colors">
              <div className="flex items-center gap-2"><MessageSquare size={12} /> Recent</div>
              {historyOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {historyOpen && (
              <div className="space-y-1">
                {unpinnedChats.map((c: any) => (
                  <button key={c.id} onClick={() => loadChat(c.id)} className={`w-full text-left p-3 rounded-lg text-sm transition-all group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-white' : 'hover:bg-white/5 text-white/70'}`}>
                    <span className="truncate">{c.title}</span>
                    <span className="text-[10px] text-white/40">{new Date(c.date).toLocaleDateString()}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
        
        {/* Settings / Archive link bottom */}
        <div className="p-4 border-t border-white/5">
           <button className="w-full flex items-center gap-3 text-white/40 hover:text-white text-xs transition-colors p-2 rounded hover:bg-white/5">
             <Settings size={14} /> View All Archives
           </button>
        </div>
      </div>

      {/* RIGHT MAIN CHAT AREA */}
      <div className="flex-1 flex flex-col h-full relative">
        <div className="flex-1 overflow-y-auto p-8 lg:p-16 space-y-16 custom-scrollbar pb-40">
          {liveMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000 mt-20">
              <div className="w-24 h-24 rounded-full border border-white/5 flex items-center justify-center relative mb-8">
                <div className="absolute inset-0 border border-primary/20 rounded-full animate-ping [animation-duration:3s]" />
                <Sparkles size={32} className="text-primary/40" />
              </div>
              <h1 className="text-3xl font-bold text-white tracking-tighter mb-4 lowercase italic">Initialize Synapse Stream</h1>
              <p className="text-white/40 max-w-md leading-relaxed mb-12 lowercase font-light">The neural interface is online and awaiting input. Send a command or attach a file to begin.</p>
              
              <div className="flex gap-4">
                <button onClick={() => setInputValue("Analyze my current workspace")} className="bg-white/5 hover:bg-white/10 text-white/60 hover:text-white px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest transition-all">Analyze Workspace</button>
                <button onClick={() => setInputValue("Summarize system status")} className="bg-white/5 hover:bg-white/10 text-white/60 hover:text-white px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest transition-all">System Status</button>
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
                  ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'bg-primary/10 text-primary shadow-[0_0_20px_rgba(79,70,229,0.2)]' : 'bg-white/5 text-white/50 grayscale'}`}
                >
                  {msg.sender?.toUpperCase() === 'PRIMNOX' ? <Terminal size={22} /> : <User size={22} />}
                </div>
                <div className={`glass-panel p-6 rounded-3xl space-y-3 relative transition-all duration-700
                  ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'rounded-tl-none bg-zinc-900/40 shadow-[0_0_40px_rgba(79,70,229,0.15)] border border-primary/20' : 'rounded-tr-none bg-primary/5 shadow-2xl'}`}
                >
                   <div className={`flex justify-between items-center pb-3 mb-3 font-mono text-[11px] tracking-[0.2em]
                     ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'text-primary/60' : 'text-white/40'}`}
                   >
                      <span className="uppercase font-bold">{msg.sender?.toUpperCase() === 'PRIMNOX' ? `PROTOCOL // ${aiName}_v2` : `OPERATOR // ${userName}`}</span>
                      <span className="opacity-40">{msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}</span>
                   </div>
                  <p className={`text-sm leading-relaxed ${msg.sender?.toUpperCase() === 'PRIMNOX' ? 'text-white font-light italic' : 'text-white/90 font-medium'}`}>
                    {msg.text}
                  </p>
                </div>
              </motion.div>
            ))
          )}
          <div ref={messagesEndRef} className="h-1" />
        </div>

        <footer className="p-8 lg:p-12 pt-0 absolute bottom-0 left-0 right-0 z-20 pointer-events-auto">
          <div className="max-w-4xl mx-auto flex items-center justify-between w-full gap-2">
            <button onClick={() => setShowLeftPane(!showLeftPane)} className="p-3 bg-zinc-900 rounded-2xl hover:bg-zinc-800 transition-colors text-white/50 hover:text-white shrink-0" title="Toggle Chat History"><History size={20}/></button>
            <div className="flex-1 glass-panel rounded-3xl flex items-center p-4 group focus-within:shadow-[0_0_60px_rgba(79,70,229,0.2)] transition-all relative pointer-events-auto bg-zinc-900/90 backdrop-blur-3xl">
            <div className="absolute -top-10 left-8 px-4 py-1 bg-zinc-900 rounded-full font-mono text-[9px] text-white/30 uppercase tracking-[0.4em] opacity-0 group-focus-within:opacity-100 transition-all translate-y-2 group-focus-within:translate-y-0">Neural_Input_Active</div>
            
            <input type="file" ref={fileInputRef} className="hidden" onChange={handleFileChange} />
            
            <button 
              onClick={() => fileInputRef.current?.click()}
              className="p-4 text-white/20 hover:text-primary transition-all hover:bg-primary/10 rounded-2xl mr-2 group/btn"
              title="Attach_File"
            >
              <Paperclip size={22} className="group-hover/btn:rotate-12 transition-transform" />
            </button>

            <input 
              role="textbox"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSend()}
              className="flex-1 bg-transparent border-none focus:ring-0 text-white placeholder-white/10 text-sm px-6 font-light h-14" 
              placeholder="Stream thoughts or commands..."
            />
            
            {attachedFile && (
              <div className="flex items-center gap-2 bg-primary/20 text-primary px-3 py-1.5 rounded-xl mr-4 border border-primary/30">
                <span className="font-mono text-[11px] uppercase tracking-widest truncate max-w-[150px]">{attachedFile.name}</span>
                <button onClick={removeAttachedFile} className="hover:text-white transition-colors"><X size={14} /></button>
              </div>
            )}

            <button 
              onClick={handleSend}
              className="bg-primary text-black w-14 h-14 rounded-2xl flex items-center justify-center hover:bg-white transition-all shadow-2xl active:scale-90 group-hover:shadow-primary/40 disabled:opacity-50 disabled:active:scale-100"
              disabled={!inputValue.trim() && !attachedFile}
            >
              <ArrowRight size={26} strokeWidth={3} />
            </button>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};
