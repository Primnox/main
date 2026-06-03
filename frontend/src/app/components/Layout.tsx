import { useState, ReactNode, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Terminal, MessageSquare, FileText, Database, History, Settings, ChevronRight, Network, LayoutDashboard } from 'lucide-react';
import { DynamicIsland } from './DynamicIsland';
import { TitleBar } from './TitleBar';

type SidebarState = 'expanded' | 'icon' | 'hidden';
type AppMode = 'chat' | 'notes' | 'research';
type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

type ScreenId = 
  | 'summaries_expanded'
  | 'notes_icon_sidebar'
  | 'summaries_sidebar_hidden'
  | 'summaries_empty_state'
  | 'island_settings'
  | 'summaries_icon_sidebar'
  | 'chat_expanded_sidebar'
  | 'settings_neural'
  | 'logs'
  | 'archive'
  | 'knowledge'
  | 'graph_view';

const IconButton = ({ icon: Icon, active, onClick, label }: { icon: any, active?: boolean, onClick?: () => void, label?: string }) => (
  <button 
    onClick={onClick}
    className={`flex flex-col items-center gap-1 group transition-all duration-300 ${active ? 'text-primary' : 'text-on-surface-variant hover:text-on-surface'}`}
  >
    <div className={`p-2 rounded ${active ? 'bg-primary/10' : 'hover:bg-white/5'}`}>
      <Icon size={18} />
    </div>
    {label && <span className="text-[8px] font-mono uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-opacity">{label}</span>}
  </button>
);

const SidebarLink = ({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) => (
  <div 
    onClick={onClick}
    className={`flex items-center gap-4 px-6 py-3 font-mono text-[10px] uppercase tracking-widest transition-all cursor-pointer group
      ${active 
        ? 'bg-primary/10 text-white border-l-2 border-primary' 
        : 'text-on-surface-variant hover:text-on-surface hover:bg-white/5'}`}
  >
    <Icon size={18} className={active ? 'fill-current' : ''} />
    <span>{label}</span>
  </div>
);

export const Layout = ({ 
  children, 
  sidebarState, 
  onNavigate,
  activeLink, 
  title = "",
  subtitle = "",
  actions = null,
  aiName = "Primnox",
  appMode,
  setAppMode,
  status,
  setStatus,
  onLogoClick,
  isIslandVisible = true,
  toasts = [],
  vadLevel = 0,
  transcript = "",
  attachedFile = null,
  micMuted = false,
  onMicClick,
  isZenMode = false
}: { 
  children: ReactNode, 
  sidebarState: SidebarState, 
  onNavigate: (id: ScreenId) => void, 
  activeLink: string,
  title?: string,
  subtitle?: string,
  actions?: ReactNode,
  aiName?: string,
  appMode: AppMode,
  setAppMode: (m: AppMode) => void,
  status: AiStatus,
  setStatus: (s: AiStatus) => void,
  onLogoClick?: () => void,
  isIslandVisible?: boolean,
  toasts?: any[],
  vadLevel?: number,
  transcript?: string,
  attachedFile?: any,
  micMuted?: boolean,
  onMicClick?: () => void,
  isZenMode?: boolean
}) => {
  const [localSidebar, setLocalSidebar] = useState<SidebarState>(sidebarState);

  useEffect(() => {
    setLocalSidebar(sidebarState);
  }, [sidebarState]);

  return (
    <div className={`flex flex-col w-full h-screen bg-black text-white font-sans overflow-hidden`}>
      <TitleBar />
      <AnimatePresence mode="wait">
          {isIslandVisible && (
          <DynamicIsland 
            mode={appMode} 
            setMode={setAppMode} 
            status={status} 
            setStatus={setStatus}
            onProfileClick={() => onNavigate('island_settings')}
            vadLevel={vadLevel}
            transcript={transcript}
            attachedFile={attachedFile}
            micMuted={micMuted}
            onMicClick={onMicClick}
          />
        )}
      </AnimatePresence>

      <>
          {/* Toasts */}
          <div className="fixed bottom-8 right-8 z-[200] flex flex-col gap-3">
            <AnimatePresence>
              {toasts.map((toast: any) => (
                <motion.div
                  key={toast.id}
                  initial={{ opacity: 0, x: 20, scale: 0.9 }}
                  animate={{ opacity: 1, x: 0, scale: 1 }}
                  exit={{ opacity: 0, x: 20, scale: 0.9 }}
                  className={`px-6 py-4 rounded-xl border backdrop-blur-xl shadow-2xl font-mono text-[10px] uppercase tracking-widest font-bold
                    ${toast.type === 'success' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-500' : 
                      toast.type === 'error' ? 'bg-red-500/10 border-red-500/20 text-red-500' : 
                      'bg-primary/10 border-primary/20 text-primary'}`}
                >
                  {toast.message}
                </motion.div>
              ))}
            </AnimatePresence>
          </div>

          {/* Main Layout Container */}
          <div className="flex-1 flex overflow-hidden">
            {!isZenMode && (
              <aside 
                className={`flex flex-col bg-zinc-950/50 backdrop-blur-xl border-r border-white/5 transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] relative z-20 shrink-0
                  ${localSidebar === 'expanded' ? 'w-[260px]' : localSidebar === 'icon' ? 'w-20' : 'w-0 border-r-0 opacity-0'}`}
              >
                {/* Logo Area */}
                <div 
                  className={`h-20 flex items-center border-b border-white/5 transition-all
                    ${localSidebar === 'icon' ? 'justify-center px-0' : 'px-8 justify-between'}`}
                >
                  <div className="flex items-center gap-3 cursor-pointer group" onClick={onLogoClick}>
                    <div className="w-8 h-8 rounded-full border border-primary/30 flex items-center justify-center bg-primary/10 text-primary group-hover:scale-105 group-hover:bg-primary/20 transition-all shadow-[0_0_15px_rgba(79,70,229,0.2)]">
                      <Terminal size={14} />
                    </div>
                    {localSidebar === 'expanded' && (
                      <div className="flex flex-col">
                        <span className="font-bold text-white tracking-tighter uppercase">{aiName}</span>
                      </div>
                    )}
                  </div>
                </div>

                <nav className="flex-1 flex flex-col gap-1.5 px-4 mt-6">
                  {localSidebar === 'expanded' ? (
                    <>
                      <SidebarLink icon={MessageSquare} label="Synapse_Stream" active={activeLink === 'transcripts'} onClick={() => { onNavigate('chat_expanded_sidebar'); setAppMode('chat'); }} />
                      <SidebarLink icon={FileText} label="Neural_Nodes" active={activeLink === 'notes'} onClick={() => { onNavigate('notes_icon_sidebar'); setAppMode('notes'); }} />
                      <SidebarLink icon={LayoutDashboard} label="Dashboard" active={activeLink === 'summaries'} onClick={() => onNavigate('summaries_expanded')} />
                      <SidebarLink icon={Network} label="Knowledge_Graph" active={activeLink === 'graph'} onClick={() => onNavigate('graph_view')} />
                      <SidebarLink icon={Database} label="Data_Vault" active={activeLink === 'archive'} onClick={() => onNavigate('archive')} />
                      <SidebarLink icon={History} label="System_Logs" active={activeLink === 'logs'} onClick={() => onNavigate('logs')} />
                      <SidebarLink icon={Settings} label="Configure" active={activeLink === 'settings'} onClick={() => onNavigate('island_settings')} />
                    </>
                  ) : (
                    <div className="flex flex-col gap-8 items-center flex-1 py-6">
                      <IconButton icon={MessageSquare} active={activeLink === 'transcripts'} onClick={() => { onNavigate('chat_expanded_sidebar'); setAppMode('chat'); }} label="Synapse" />
                      <IconButton icon={FileText} active={activeLink === 'notes'} onClick={() => { onNavigate('notes_icon_sidebar'); setAppMode('notes'); }} label="Nodes" />
                      <IconButton icon={LayoutDashboard} active={activeLink === 'summaries'} onClick={() => onNavigate('summaries_expanded')} label="Dash" />
                      <IconButton icon={Network} active={activeLink === 'graph'} onClick={() => onNavigate('graph_view')} label="Graph" />
                      <IconButton icon={Database} active={activeLink === 'archive'} onClick={() => onNavigate('archive')} label="Vault" />
                      <IconButton icon={History} active={activeLink === 'logs'} onClick={() => onNavigate('logs')} label="Logs" />
                      <IconButton icon={Settings} active={activeLink === 'settings'} onClick={() => onNavigate('island_settings')} label="Config" />
                    </div>
                  )}
                </nav>

                <div className="p-6 mt-auto">
                  <button 
                    onClick={() => setLocalSidebar(localSidebar === 'expanded' ? 'icon' : 'expanded')}
                    className={`w-full p-3 rounded flex items-center gap-3 text-white/20 hover:text-white transition-all overflow-hidden whitespace-nowrap
                      ${localSidebar === 'icon' ? 'justify-center' : ''}`}
                  >
                    <ChevronRight size={18} className={`transition-transform duration-500 ${localSidebar === 'expanded' ? 'rotate-180' : ''}`} />
                    {localSidebar === 'expanded' && <span className="font-mono text-[10px] uppercase tracking-widest text-white/40">Collapse_UI</span>}
                  </button>
                </div>
              </aside>
            )}

            <main className="flex-1 flex flex-col relative overflow-hidden bg-black">
              {!isZenMode && (
                <header className="h-20 border-b border-white/5 flex items-center px-12 justify-between bg-zinc-950/50 backdrop-blur-xl relative z-30">
                  <div className="flex flex-col text-left">
                    <h2 className="text-white font-bold tracking-tighter text-lg italic lowercase">{title}</h2>
                    <p className="text-white/20 font-mono text-[9px] uppercase tracking-[0.4em] font-bold">{subtitle}</p>
                  </div>
                  <div className="flex items-center gap-6">
                    {actions && (
                      <div className="flex items-center gap-4">
                        {actions}
                      </div>
                    )}
                  </div>
                </header>
              )}
              <div className="flex-1 relative overflow-hidden">
                <AnimatePresence mode="wait">
                  <motion.div
                    key={appMode}
                    initial={{ opacity: 0, y: 10, filter: 'blur(4px)' }}
                    animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
                    exit={{ opacity: 0, y: -10, filter: 'blur(4px)' }}
                    transition={{ duration: 0.3, ease: 'easeOut' }}
                    className="absolute inset-0"
                  >
                    {children}
                  </motion.div>
                </AnimatePresence>
              </div>
            </main>
          </div>
      </>
    </div>
  );
};
