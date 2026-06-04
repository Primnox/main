import { useState, useEffect, useRef, ChangeEvent } from 'react';
import { createPortal } from 'react-dom';
import { motion } from 'motion/react';
import { Paperclip, ArrowRight, Sparkles, X, Plus, MessageSquare, Pin, Folder, ChevronDown, ChevronRight, Trash2, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';

type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

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
  const fileInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState("");
  const [attachedFile, setAttachedFile] = useState<File | null>(null);

  // State for Left Sidebar
  const [historyOpen, setHistoryOpen] = useState(true);
  const [foldersOpen, setFoldersOpen] = useState(true);
  const [activeFolderId, setActiveFolderId] = useState<string | null>(null);

  // Context Menu State
  const [contextMenu, setContextMenu] = useState<{ x: number, y: number, chat: any } | null>(null);

  // Close context menu on click outside
  useEffect(() => {
    const handleClick = () => setContextMenu(null);
    window.addEventListener('click', handleClick);
    return () => window.removeEventListener('click', handleClick);
  }, []);

  const handleContextMenu = (e: React.MouseEvent, chat: any) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, chat });
  };

  const handleMenuAction = async (action: string, chat: any, folderId?: string) => {
    setContextMenu(null);
    try {
      if (action === 'pin') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ isPinned: !chat.isPinned })
        });
      } else if (action === 'move') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ folderId })
        });
      } else if (action === 'auto_assign') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}/auto_assign`, { method: 'POST' });
      } else if (action === 'delete') {
        await fetch(`http://localhost:8000/api/chats/${chat.id}`, { method: 'DELETE' });
      }
      refreshChats();
    } catch (e) {
      console.error(e);
    }
  };


  const pinnedChats = chatSessions.filter(c => c.isPinned);
  const unpinnedChats = chatSessions.filter(c => !c.isPinned && ((!activeFolderId && !c.folderId) || (c.folderId === activeFolderId)));

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
      {/* Context Menu Overlay */}
      {contextMenu && createPortal(
        <div 
          className="fixed z-50 bg-zinc-900 border border-white/10 rounded-xl shadow-2xl py-1 w-48 text-sm"
          style={{ top: contextMenu.y, left: contextMenu.x }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-3 py-2 border-b border-white/5 font-bold text-white truncate text-xs">
            {contextMenu.chat.title}
          </div>
          <button onClick={() => handleMenuAction('pin', contextMenu.chat)} className="w-full text-left px-4 py-2 hover:bg-white/10 text-white/80 flex items-center gap-2">
            <Pin size={14} /> {contextMenu.chat.isPinned ? 'Unpin' : 'Pin'}
          </button>
          
          <div className="group/submenu relative">
            <button className="w-full text-left px-4 py-2 hover:bg-white/10 text-white/80 flex items-center justify-between">
              <span className="flex items-center gap-2"><Folder size={14} /> Add to Project</span>
              <ChevronRight size={14} />
            </button>
            <div className="absolute left-full top-0 hidden group-hover/submenu:block w-48 bg-zinc-900 border border-white/10 rounded-xl shadow-2xl py-1 ml-1">
              <button onClick={() => handleMenuAction('auto_assign', contextMenu.chat)} className="w-full text-left px-4 py-2 hover:bg-white/10 text-primary flex items-center gap-2">
                <Bot size={14} /> Auto-Detect
              </button>
              <div className="h-px bg-white/10 my-1" />
              {chatFolders.map((f: any) => (
                <button key={f.id} onClick={() => handleMenuAction('move', contextMenu.chat, f.id)} className="w-full text-left px-4 py-2 hover:bg-white/10 text-white/80 truncate text-xs">
                  {f.title}
                </button>
              ))}
            </div>
          </div>
          
          <div className="h-px bg-white/10 my-1" />
          <button onClick={() => handleMenuAction('delete', contextMenu.chat)} className="w-full text-left px-4 py-2 hover:bg-red-500/20 text-red-400 flex items-center gap-2">
            <Trash2 size={14} /> Delete Chat
          </button>
        </div>,
        document.body
      )}

      {/* LEFT CHAT SIDEBAR (History/Folders) */}
      <div className="w-64 lg:w-72 border-r border-white/5 bg-zinc-900/20 flex flex-col pt-12 text-white overflow-hidden shrink-0">
        
        {/* Header & New Chat Button */}
        <div className="px-6 mb-6">
          <button onClick={() => createNewChat()} className="w-full flex items-center justify-between p-3 bg-primary text-black font-bold rounded-xl hover:bg-white transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)] group active:scale-95">
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
                <button key={c.id} onClick={() => loadChat(c.id)} onContextMenu={(e) => handleContextMenu(e, c)} className={`w-full text-left p-3 rounded-lg text-sm transition-all group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-white' : 'hover:bg-white/5 text-white/70'}`}>
                  <div className="flex justify-between items-start">
                    <span className="truncate font-bold">{c.title}</span>
                    <span className="text-[9px] text-white/20 font-mono">#{c.id.substring(0,6)}</span>
                  </div>
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
                  <button key={f.id} onClick={() => { setActiveFolderId(f.id); setHistoryOpen(true); }} className={`w-full text-left p-3 rounded-lg text-sm hover:bg-white/5 transition-all flex items-center justify-between group ${activeFolderId === f.id ? 'text-primary bg-white/10' : 'text-white/70'}`}>
                    <div className="flex items-center gap-3 truncate">
                      <Folder size={14} className={`group-hover:text-primary transition-colors ${activeFolderId === f.id ? 'text-primary' : 'text-white/30'}`} />
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
             <button onClick={() => { setActiveFolderId(null); setHistoryOpen(true); }} className={`w-full px-3 py-1 text-[10px] font-mono uppercase tracking-widest mb-2 flex items-center justify-between transition-colors ${activeFolderId === null ? 'text-primary' : 'text-white/40 hover:text-white'}`}>
              <div className="flex items-center gap-2"><MessageSquare size={12} /> {activeFolderId ? "Back to Recent" : "Recent"}</div>
              {historyOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            </button>
            {historyOpen && (
              <div className="space-y-1">
                {unpinnedChats.map((c: any) => (
                  <button key={c.id} onClick={() => loadChat(c.id)} onContextMenu={(e) => handleContextMenu(e, c)} className={`w-full text-left p-3 rounded-lg text-sm transition-all group flex flex-col gap-1 ${activeChatId === c.id ? 'bg-primary/20 text-white' : 'hover:bg-white/5 text-white/70'}`}>
                    <div className="flex justify-between items-start">
                      <span className="truncate">{c.title}</span>
                      <span className="text-[9px] text-white/20 font-mono">#{c.id.substring(0,6)}</span>
                    </div>
                    <span className="text-[10px] text-white/40">{new Date(c.date).toLocaleDateString()}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* RIGHT MAIN CHAT AREA */}
      <div className="flex-1 flex flex-col h-full relative">
        <div className="flex-1 overflow-y-auto p-4 lg:p-8 flex flex-col space-y-6 custom-scrollbar relative z-10">
          {liveMessages.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000 mt-20">
              <Sparkles size={32} className="text-primary/60 mb-6" />
              <h1 className="text-2xl font-medium text-white/90 mb-10">How can I help?</h1>
              
              <div className="flex gap-4">
                <button onClick={() => setInputValue("Analyze my current workspace")} className="bg-white/5 hover:bg-white/10 text-white/60 hover:text-white px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest transition-all">Analyze Workspace</button>
                <button onClick={() => setInputValue("Summarize system status")} className="bg-white/5 hover:bg-white/10 text-white/60 hover:text-white px-6 py-3 rounded-full font-mono text-[11px] uppercase tracking-widest transition-all">System Status</button>
              </div>
            </div>
          ) : (
            liveMessages.map((msg, idx) => {
              const isAI = msg.sender?.toUpperCase() === 'PRIMNOX';
              return (
                <motion.div 
                  key={idx}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex flex-col group ${isAI ? 'items-start max-w-3xl' : 'items-end ml-auto max-w-2xl'}`}
                >
                  {isAI ? (
                    <div className="prose prose-invert prose-p:leading-relaxed prose-pre:bg-black/50 prose-pre:border prose-pre:border-white/10 prose-headings:tracking-tight prose-a:text-primary max-w-none font-sans text-sm text-white/90 font-light w-full">
                      <ReactMarkdown>{msg.text}</ReactMarkdown>
                    </div>
                  ) : (
                    <div className="bg-white/10 rounded-2xl px-4 py-3 text-white/90 text-sm font-medium leading-relaxed break-words">
                      {msg.text}
                    </div>
                  )}
                  {msg.timestamp && (
                    <div className={`text-[10px] text-white/20 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ${isAI ? 'text-left' : 'text-right'}`}>
                      {new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                  )}
                </motion.div>
              );
            })
          )}
          <div ref={messagesEndRef} className="h-1" />
        </div>

        <footer className="p-4 lg:p-8 pt-0 z-20 pointer-events-auto shrink-0">
          <div className="max-w-4xl mx-auto glass-panel rounded-3xl flex items-center p-4 group focus-within:shadow-[0_0_60px_rgba(79,70,229,0.2)] transition-all relative pointer-events-auto bg-zinc-900/90 backdrop-blur-3xl">
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
        </footer>
      </div>
    </div>
  );
};
