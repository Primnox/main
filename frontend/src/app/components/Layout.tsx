import { useState, ReactNode, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { MessageSquare, FileText, Database, History, Settings, ChevronRight, Network, LayoutDashboard, Globe, BookOpen, Calendar, Mic } from 'lucide-react';
import { DynamicIsland } from './DynamicIsland';
import { TitleBar } from './TitleBar';

type SidebarState = 'expanded' | 'icon' | 'hidden';
type AppMode = 'chat' | 'notes' | 'research';
type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy' | 'error';

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
  | 'graph_view'
  | 'research_workspace'
  | 'calendar'
  | 'meetings';

const IconButton = ({ icon: Icon, active, onClick, label }: { icon: any, active?: boolean, onClick?: () => void, label?: string }) => (
  <button 
    onClick={onClick}
    className={`flex flex-col items-center gap-1 group transition-all duration-300 ${active ? 'text-primary' : 'text-on-surface-variant hover:text-on-surface'}`}
  >
    <div className={`p-2 rounded ${active ? 'bg-primary/10' : 'hover:bg-on-surface/5'}`}>
      <Icon size={18} />
    </div>
    {label && <span className="text-[10px] font-mono uppercase tracking-widest opacity-0 group-hover:opacity-100 transition-all duration-300">{label}</span>}
  </button>
);

const SidebarLink = ({ icon: Icon, label, active, onClick }: { icon: any, label: string, active?: boolean, onClick?: () => void }) => (
  <div 
    onClick={onClick}
    className={`flex items-center gap-4 px-6 py-3 font-mono text-[10px] uppercase tracking-widest transition-all duration-300 cursor-pointer group
      ${active 
        ? 'bg-primary/10 text-on-surface border-l-2 border-primary' 
        : 'text-on-surface-variant hover:text-on-surface hover:bg-on-surface/5'}`}
  >
    <Icon size={18} className={active ? 'fill-current' : ''} />
    <span>{label}</span>
  </div>
);

export const Layout = ({
  children,
  sidebarState,
  onSidebarStateChange,
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
  transcript = "",
  attachedFile = null,
  errorPayload = null,
  onClearError,
  flowState = null,
  errorStreak = null,
  nowPlaying = null,
  islandSkills = {},
  productivityScore = 100,
  parallelTasks = [],
  onSmartPaste,
  onMediaControl,
  proactiveAlert = null,
  onDismissProactive,
  onSuggestionClick,
  isZenMode = false,
  isIslandMode = false,
  onRestoreWindow,
}: {
  children: ReactNode,
  sidebarState: SidebarState,
  onSidebarStateChange?: (s: SidebarState) => void,
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
  transcript?: string,
  attachedFile?: any,
  errorPayload?: { summary: string; fix: string; hover_text: string } | null,
  onClearError?: () => void,
  flowState?: { duration_minutes: number; started_at: number; app: string } | null,
  errorStreak?: { error: string; duration_minutes: number } | null,
  nowPlaying?: { title: string; artist: string; album?: string; source: string; is_playing?: boolean; position_ms?: number; duration_ms?: number; sampled_at?: number } | null,
  islandSkills?: Record<string, any>,
  productivityScore?: number,
  parallelTasks?: { id: string; label: string; color: string }[],
  onSmartPaste?: () => void,
  onMediaControl?: (action: 'play_pause' | 'next' | 'prev' | 'stop') => void,
  proactiveAlert?: { message: string; suggestions: string[] } | null,
  onDismissProactive?: () => void,
  onSuggestionClick?: (s: string) => void,
  isZenMode?: boolean,
  isIslandMode?: boolean,
  onRestoreWindow?: () => void,
}) => {
  // The sidebar width is the user's preference and belongs to one owner (App,
  // which persists it). This used to keep a private copy that stopped following
  // the prop after the first manual toggle, so the same click produced different
  // results depending on whether the toggle had ever been touched.
  const [localSidebar, setLocalSidebar] = useState<SidebarState>(sidebarState);

  useEffect(() => { setLocalSidebar(sidebarState); }, [sidebarState]);

  const handleSidebarToggle = () => {
    const next: SidebarState = localSidebar === 'expanded' ? 'icon' : 'expanded';
    setLocalSidebar(next);
    onSidebarStateChange?.(next);
  };

  // ── Island-pill mode: render ONLY the Dynamic Island ──────────────────────
  // The Electron main process has already shrunk the window to 900×200 and
  // positioned it at the top-centre of the screen. We just need to clear
  // everything except the pill so nothing leaks around it.
  if (isIslandMode) {
    return (
      <div className="w-full h-screen bg-transparent overflow-hidden pointer-events-none">
        <DynamicIsland
          mode={appMode}
          setMode={setAppMode}
          status={status}
          setStatus={setStatus}
          onProfileClick={onRestoreWindow || (() => {})}
          transcript={transcript}
          attachedFile={attachedFile}
          errorPayload={errorPayload}
          onClearError={onClearError}
          flowState={flowState}
          errorStreak={errorStreak}
          nowPlaying={nowPlaying}
          islandSkills={islandSkills}
          productivityScore={productivityScore}
          parallelTasks={parallelTasks}
          onSmartPaste={onSmartPaste}
          onMediaControl={onMediaControl}
          proactiveAlert={proactiveAlert}
          onDismissProactive={onDismissProactive}
          onSuggestionClick={onSuggestionClick}
          isWindowIsland={true}
          onRestoreWindow={onRestoreWindow}
        />
      </div>
    );
  }

  return (
    <div className={`flex flex-col w-full h-screen bg-surface text-on-surface font-sans overflow-hidden`}>
      <TitleBar />
      <AnimatePresence mode="wait">
          {isIslandVisible && (
          <DynamicIsland
            key="island"
            mode={appMode}
            setMode={setAppMode}
            status={status}
            setStatus={setStatus}
            onProfileClick={() => onNavigate('island_settings')}
            transcript={transcript}
            attachedFile={attachedFile}
            errorPayload={errorPayload}
            onClearError={onClearError}
            flowState={flowState}
            errorStreak={errorStreak}
            nowPlaying={nowPlaying}
            islandSkills={islandSkills}
            productivityScore={productivityScore}
            parallelTasks={parallelTasks}
            onSmartPaste={onSmartPaste}
            onMediaControl={onMediaControl}
            proactiveAlert={proactiveAlert}
            onDismissProactive={onDismissProactive}
            onSuggestionClick={onSuggestionClick}
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
                  className={`px-6 py-4 rounded-xl border backdrop-blur-2xl bg-[var(--nav-bg)] shadow-2xl font-mono text-[10px] uppercase tracking-widest font-bold
                    ${toast.type === 'success' ? 'bg-success/10 border-success/20 text-success/80' : 
                      toast.type === 'error' ? 'bg-error/10 border-error/20 text-error/80' : 
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
                className={`flex flex-col backdrop-blur-2xl bg-[var(--nav-bg)] border-r border-on-surface/5 transition-all duration-500 ease-[cubic-bezier(0.2,0.8,0.2,1)] relative z-20 shrink-0
                  ${localSidebar === 'expanded' ? 'w-[260px]' : localSidebar === 'icon' ? 'w-20' : 'w-0 border-r-0 opacity-0'}`}
              >
                {/* Logo Area */}
                <div 
                  className={`h-20 flex items-center border-b border-on-surface/5 transition-all
                    ${localSidebar === 'icon' ? 'justify-center px-0' : 'px-8 justify-between'}`}
                >
                  {/* Brand mark mirrors the site's nav-logo: a pulsing dot and
                      wide-tracked uppercase wordmark, no boxed icon. */}
                  <div className="flex items-center gap-3 cursor-pointer group" onClick={onLogoClick}>
                    <span className="w-[7px] h-[7px] rounded-full bg-on-surface shrink-0 transition-transform group-hover:scale-125" />
                    {localSidebar === 'expanded' && (
                      <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em] text-on-surface">
                        {aiName}
                      </span>
                    )}
                  </div>
                  {/* Collapse control lives beside the wordmark. It used to sit at
                      the bottom of the rail, which fell below the fold on short
                      windows — collapsing the sidebar could leave no visible way
                      to bring it back. */}
                  {localSidebar === 'expanded' && (
                    <button
                      onClick={handleSidebarToggle}
                      title="Collapse sidebar"
                      className="p-1.5 rounded text-on-surface/55 hover:text-on-surface hover:bg-on-surface/5 transition-all duration-300 shrink-0"
                    >
                      <ChevronRight size={16} className="rotate-180" />
                    </button>
                  )}
                </div>

                {localSidebar === 'icon' && (
                  <button
                    onClick={handleSidebarToggle}
                    title="Expand sidebar"
                    className="mx-auto mt-3 p-2 rounded text-on-surface/55 hover:text-on-surface hover:bg-on-surface/5 transition-all duration-300"
                  >
                    <ChevronRight size={16} />
                  </button>
                )}

                <nav className="flex-1 flex flex-col gap-1.5 px-4 mt-6">
                  {localSidebar === 'expanded' ? (
                    <>
                      <SidebarLink icon={MessageSquare} label="Synapse_Stream" active={activeLink === 'transcripts'} onClick={() => { onNavigate('chat_expanded_sidebar'); setAppMode('chat'); }} />
                      <SidebarLink icon={FileText} label="Neural_Nodes" active={activeLink === 'notes'} onClick={() => { onNavigate('notes_icon_sidebar'); setAppMode('notes'); }} />
                      <SidebarLink icon={LayoutDashboard} label="Dashboard" active={activeLink === 'summaries'} onClick={() => onNavigate('summaries_expanded')} />
                      <SidebarLink icon={Globe} label="Deep_Research" active={activeLink === 'research'} onClick={() => { onNavigate('research_workspace'); setAppMode('research'); }} />
                      <SidebarLink icon={Calendar} label="Calendar" active={activeLink === 'calendar'} onClick={() => onNavigate('calendar')} />
                      <SidebarLink icon={Mic} label="Recordings" active={activeLink === 'meetings'} onClick={() => onNavigate('meetings')} />
                      <SidebarLink icon={Network} label="Knowledge_Graph" active={activeLink === 'graph'} onClick={() => onNavigate('graph_view')} />
                      <SidebarLink icon={Database} label="Data_Vault" active={activeLink === 'archive'} onClick={() => onNavigate('archive')} />
                      <SidebarLink icon={BookOpen} label="Knowledge_Nexus" active={activeLink === 'knowledge'} onClick={() => onNavigate('knowledge')} />
                      <SidebarLink icon={History} label="System_Logs" active={activeLink === 'logs'} onClick={() => onNavigate('logs')} />
                      <SidebarLink icon={Settings} label="Configure" active={activeLink === 'settings'} onClick={() => onNavigate('island_settings')} />
                    </>
                  ) : (
                    <div className="flex flex-col gap-8 items-center flex-1 py-6">
                      <IconButton icon={MessageSquare} active={activeLink === 'transcripts'} onClick={() => { onNavigate('chat_expanded_sidebar'); setAppMode('chat'); }} label="Synapse" />
                      <IconButton icon={FileText} active={activeLink === 'notes'} onClick={() => { onNavigate('notes_icon_sidebar'); setAppMode('notes'); }} label="Nodes" />
                      <IconButton icon={LayoutDashboard} active={activeLink === 'summaries'} onClick={() => onNavigate('summaries_expanded')} label="Dash" />
                      <IconButton icon={Globe} active={activeLink === 'research'} onClick={() => { onNavigate('research_workspace'); setAppMode('research'); }} label="Research" />
                      <IconButton icon={Calendar} active={activeLink === 'calendar'} onClick={() => onNavigate('calendar')} label="Cal" />
                      <IconButton icon={Mic} active={activeLink === 'meetings'} onClick={() => onNavigate('meetings')} label="Rec" />
                      <IconButton icon={Network} active={activeLink === 'graph'} onClick={() => onNavigate('graph_view')} label="Graph" />
                      <IconButton icon={Database} active={activeLink === 'archive'} onClick={() => onNavigate('archive')} label="Vault" />
                      <IconButton icon={BookOpen} active={activeLink === 'knowledge'} onClick={() => onNavigate('knowledge')} label="Nexus" />
                      <IconButton icon={History} active={activeLink === 'logs'} onClick={() => onNavigate('logs')} label="Logs" />
                      <IconButton icon={Settings} active={activeLink === 'settings'} onClick={() => onNavigate('island_settings')} label="Config" />
                    </div>
                  )}
                </nav>

              </aside>
            )}

            <main className="flex-1 flex flex-col relative overflow-hidden bg-surface">
              {!isZenMode && (
                // Background was a hardcoded bg-surface that survived the token
                // migration — now the themed nav surface.
                <header className="h-20 border-b border-on-surface/5 flex items-center px-12 justify-between backdrop-blur-2xl relative z-30"
                        style={{ background: 'var(--nav-bg)' }}>
                  {/* Page header in the site's idiom: a mono section index above
                      big uppercase Syne, replacing the lowercase italic. */}
                  <div className="flex flex-col text-left gap-1">
                    {subtitle && <span className="px-eyebrow">{subtitle}</span>}
                    <h2 className="px-display px-display-sm text-on-surface">{title}</h2>
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
