/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { usePrimnox } from '../hooks/usePrimnox';
import { CommandPalette } from './components/CommandPalette';

// Components
import { Layout } from './components/Layout';
import { TitleBar } from './components/TitleBar';
import { SummariesExpanded, SummariesSidebarHidden, SummariesEmptyState, SummariesIconSidebar } from './components/SummaryViews';
import { NotesIconSidebar } from './components/NotesView';
import { IslandSettings } from './components/SettingsView';
import { ChatExpandedSidebar } from './components/ChatView';
import { LogsPage } from './components/LogView';
import { DataVaultPage } from './components/MemoryView';
import { KnowledgePage } from './components/AboutView';
import { OnboardingView } from './components/OnboardingView';
import { GraphView } from './components/GraphView';
import { ResearchView } from './components/ResearchView';
import { CalendarView } from './components/CalendarView';
import { MeetingsView } from './components/MeetingsView';

// --- Types ---

export type ScreenId =
  | 'summaries_expanded'
  | 'notes_icon_sidebar'
  | 'summaries_sidebar_hidden'
  | 'summaries_empty_state'
  | 'island_settings'
  | 'summaries_icon_sidebar'
  | 'chat_expanded_sidebar'
  | 'research_workspace'
  | 'settings_neural'
  | 'logs'
  | 'archive'
  | 'knowledge'
  | 'graph_view'
  | 'calendar'
  | 'meetings';

export type SidebarState = 'expanded' | 'icon' | 'hidden';
export type AppMode = 'chat' | 'notes' | 'research';
export type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy' | 'error';


export default function App() {
  const { 
    messages: liveMessages,
    state: liveState,
    notes,
    tasks,
    memory,
    toasts,
    activity,
    currentTranscript,
    lastAttachedFile,
    settings,

    connectionLost,
    manualReconnect,

    sendMessage,
    updateSettings,
    exportNotes,
    fetchNotes,
    chatSessions,
    chatFolders,
    activeChatId,
    fetchChats,
    loadChat,
    createNewChat,
    islandError,
    clearIslandError,
    privacyScrub,
    flowState,
    errorStreak,
    nowPlaying,
    islandSkills,
    productivityScore,
    parallelTasks,
    proactiveAlert,
    dismissProactiveAlert,
    triggerSmartPaste,
    triggerMediaControl,
    scanEnvironment,
    fetchMemory,
    fetchTasks,
  } = usePrimnox();

  // Detect if this is the dedicated island-overlay BrowserWindow.
  // electron.cjs creates a separate 900×220 always-on-top window and loads it
  // with ?primnox_island=1. This is a permanent constant — the window is ALWAYS
  // in island mode or always in full mode; it never switches at runtime.
  const isIslandMode = new URLSearchParams(window.location.search).get('primnox_island') === '1';

  const [currentScreen, setCurrentScreen] = useState<ScreenId>('summaries_expanded');
  // Sidebar width is a user preference, not a property of the destination. It
  // used to be derived from currentScreen, so only Chat and Dashboard kept the
  // labelled sidebar and every other nav item silently collapsed it to icons.
  const [sidebarState, setSidebarState] = useState<SidebarState>(() => {
    try {
      const stored = localStorage.getItem('primnox.sidebar');
      if (stored === 'expanded' || stored === 'icon' || stored === 'hidden') return stored;
    } catch { /* private mode */ }
    return 'expanded';
  });
  const changeSidebarState = useCallback((s: SidebarState) => {
    setSidebarState(s);
    try { localStorage.setItem('primnox.sidebar', s); } catch { /* private mode */ }
  }, []);
  const [appMode, setAppMode] = useState<AppMode>('notes');
  const [status, setStatus] = useState<AiStatus>('idle');
  const [isIslandVisible, setIsIslandVisible] = useState(true);
  const [cmdPaletteOpen, setCmdPaletteOpen] = useState(false);

  // Global Ctrl+K handler
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setCmdPaletteOpen(p => !p);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  const handlePaletteNavigate = useCallback((screen: ScreenId) => {
    setCurrentScreen(screen);
    if (screen === 'notes_icon_sidebar') setAppMode('notes');
    if (screen === 'chat_expanded_sidebar') setAppMode('chat');
    if (screen === 'research_workspace') setAppMode('research');
  }, []);

  // Send "restore full window" to Electron (island pill logo click / restore button)
  const handleRestoreWindow = () => {
    if ((window as any).electron) {
      (window as any).electron.ipcRenderer.send('show-full-window');
    }
  };

  // Sync live state + island error to UI status — error takes priority
  useEffect(() => {
    if (islandError) {
      setStatus('error');
    } else if (liveState === 'thinking') {
      setStatus('thinking');
    } else if (liveState === 'listening') {
      setStatus('listening');
    } else if (liveState === 'speaking') {
      setStatus('transcript');
    } else {
      setStatus('idle');
    }
  }, [liveState, islandError]);

  const handleClearError = () => {
    clearIslandError();
    setStatus('idle');
  };

  // IPC listeners
  useEffect(() => {
    if ((window as any).electron) {
      const cleanup = (window as any).electron.ipcRenderer.on('friday:open-notes', () => {
        setAppMode('notes');
        setCurrentScreen('notes_icon_sidebar');
      });
      return cleanup || (() => {});
    }
  }, []);

  // Listen for backend-driven navigation events (navigate_ui tool + handle_route)
  useEffect(() => {
    const handler = (e: Event) => {
      const screen = (e as CustomEvent<{ screen: string }>).detail?.screen;
      if (screen) setCurrentScreen(screen as ScreenId);
    };
    window.addEventListener('primnox:navigate', handler);
    return () => window.removeEventListener('primnox:navigate', handler);
  }, []);

  // System State (Local overrides)
  const [operatorAlias, setOperatorAlias] = useState('Operator');
  const [aiCodename, setAiCodename] = useState('PRIMNOX');
  const [activeModel, setActiveModel] = useState('Groq_Llama_3');
  const [apiKey, setApiKey] = useState('');
  const [openaiApiKey, setOpenaiApiKey] = useState('');
  const [anthropicApiKey, setAnthropicApiKey] = useState('');
  const [vadSensitivity, setVadSensitivity] = useState(0.5);
  const [wakeWord, setWakeWord] = useState('hey primnox');
  const [wakeWordEnabled, setWakeWordEnabled] = useState(true);
  const [dynamicIslandEnabled, setDynamicIslandEnabled] = useState(true);
  const [privacyMirrorEnabled, setPrivacyMirrorEnabled] = useState(false);
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [ollamaBaseUrl, setOllamaBaseUrl] = useState('http://localhost:11434');
  const [llamacppBaseUrl, setLlamacppBaseUrl] = useState('http://localhost:8080');
  const [llamacppModel, setLlamacppModel] = useState('');
  const [geminiApiKey, setGeminiApiKey] = useState('');
  const [calendarProviders,   setCalendarProviders]   = useState<any[]>([]);
  const [meetingRetentionDays,setMeetingRetentionDays]= useState(10);

  // Sync settings to local state
  useEffect(() => {
    if (settings.operator_alias) setOperatorAlias(settings.operator_alias);
    if (settings.ai_codename) setAiCodename(settings.ai_codename);
    if (settings.groq_api_key !== undefined) setApiKey(settings.groq_api_key);
    if (settings.active_model) setActiveModel(settings.active_model);
    if (settings.openai_api_key !== undefined) setOpenaiApiKey(settings.openai_api_key);
    if (settings.anthropic_api_key !== undefined) setAnthropicApiKey(settings.anthropic_api_key);
    if (settings.vad_sensitivity !== undefined) setVadSensitivity(settings.vad_sensitivity);
    if (settings.wake_word !== undefined) setWakeWord(settings.wake_word);
    if (settings.wake_word_enabled !== undefined) setWakeWordEnabled(settings.wake_word_enabled);
    if (settings.dynamic_island_enabled !== undefined) setDynamicIslandEnabled(settings.dynamic_island_enabled);
    if (settings.privacy_mirror_enabled !== undefined) setPrivacyMirrorEnabled(settings.privacy_mirror_enabled);
    if (settings.ollama_model !== undefined) setOllamaModel(settings.ollama_model);
    if (settings.ollama_base_url !== undefined) setOllamaBaseUrl(settings.ollama_base_url);
    if (settings.llamacpp_base_url !== undefined) setLlamacppBaseUrl(settings.llamacpp_base_url);
    if (settings.llamacpp_model !== undefined) setLlamacppModel(settings.llamacpp_model);
    if (settings.gemini_api_key !== undefined) setGeminiApiKey(settings.gemini_api_key);
    if (settings.calendar_providers !== undefined) setCalendarProviders(settings.calendar_providers);
    if (settings.screenshot_retention !== undefined) setMeetingRetentionDays(settings.screenshot_retention);
  }, [settings]);

  const handleSync = () => {
    updateSettings({
      ...settings,
      operator_alias: operatorAlias,
      ai_codename: aiCodename,
      groq_api_key: apiKey,
      active_model: activeModel,
      openai_api_key: openaiApiKey,
      anthropic_api_key: anthropicApiKey,
      vad_sensitivity: vadSensitivity,
      wake_word: wakeWord,
      wake_word_enabled: wakeWordEnabled,
      dynamic_island_enabled: dynamicIslandEnabled,
      privacy_mirror_enabled: privacyMirrorEnabled,
      ollama_model: ollamaModel,
      ollama_base_url: ollamaBaseUrl,
      llamacpp_base_url: llamacppBaseUrl,
      llamacpp_model: llamacppModel,
      gemini_api_key: geminiApiKey,
      calendar_providers: calendarProviders,
      screenshot_retention: meetingRetentionDays,
    });
    setCurrentScreen('summaries_expanded');
  };

  const renderScreen = () => {
    let targetScreen = currentScreen;

    switch (targetScreen) {
      case 'summaries_expanded':
        return <SummariesExpanded onNavigate={setCurrentScreen} activity={activity} tasks={tasks} onTaskCompleted={fetchTasks} />;
      case 'graph_view':
        return <GraphView onNodeClick={(id) => {
          // Open the specific note
          window.dispatchEvent(new CustomEvent('primnox:open-note', { detail: { id } }));
          setCurrentScreen('notes_icon_sidebar');
          setAppMode('notes');
        }} />;
      case 'logs':
        return <LogsPage activity={activity} />;
      case 'archive':
        return <DataVaultPage memory={memory} onMemoryDeleted={() => fetchMemory()} />;
      case 'summaries_sidebar_hidden':
        return <SummariesSidebarHidden onNavigate={setCurrentScreen} />;
      case 'summaries_empty_state':
        return <SummariesEmptyState onNavigate={setCurrentScreen} />;
      case 'knowledge':
        return <KnowledgePage activeModel={activeModel} />;
      case 'island_settings':
        return (
          <IslandSettings 
            onNavigate={setCurrentScreen} 
            operatorAlias={operatorAlias}
            setOperatorAlias={setOperatorAlias}
            aiCodename={aiCodename}
            setAiCodename={setAiCodename}
            activeModel={activeModel}
            setActiveModel={setActiveModel}
            apiKey={apiKey}
            setApiKey={setApiKey}
            openaiApiKey={openaiApiKey}
            setOpenaiApiKey={setOpenaiApiKey}
            anthropicApiKey={anthropicApiKey}
            setAnthropicApiKey={setAnthropicApiKey}
            vadSensitivity={vadSensitivity}
            setVadSensitivity={setVadSensitivity}
            wakeWord={wakeWord}
            setWakeWord={setWakeWord}
            wakeWordEnabled={wakeWordEnabled}
            setWakeWordEnabled={setWakeWordEnabled}
            dynamicIslandEnabled={dynamicIslandEnabled}
            setDynamicIslandEnabled={setDynamicIslandEnabled}
            privacyMirrorEnabled={privacyMirrorEnabled}
            setPrivacyMirrorEnabled={setPrivacyMirrorEnabled}
            ollamaModel={ollamaModel}
            setOllamaModel={setOllamaModel}
            ollamaBaseUrl={ollamaBaseUrl}
            setOllamaBaseUrl={setOllamaBaseUrl}
            llamacppBaseUrl={llamacppBaseUrl}
            setLlamacppBaseUrl={setLlamacppBaseUrl}
            llamacppModel={llamacppModel}
            setLlamacppModel={setLlamacppModel}
            geminiApiKey={geminiApiKey}
            setGeminiApiKey={setGeminiApiKey}
            calendarProviders={calendarProviders}
            setCalendarProviders={setCalendarProviders}
            meetingRetentionDays={meetingRetentionDays}
            setMeetingRetentionDays={setMeetingRetentionDays}
            onSync={handleSync}
          />
        );
      case 'summaries_icon_sidebar':
        return <SummariesIconSidebar onNavigate={setCurrentScreen} notes={notes} />;
      case 'notes_icon_sidebar':
        return <NotesIconSidebar notes={notes} onExport={exportNotes} sendMessage={sendMessage} onRefresh={fetchNotes} />;
      case 'chat_expanded_sidebar':
        return (
          <ChatExpandedSidebar 
            aiName={aiCodename} 
            userName={operatorAlias} 
            setStatus={setStatus}
            liveMessages={liveMessages}
            sendMessage={sendMessage}
            chatSessions={chatSessions}
            chatFolders={chatFolders}
            activeChatId={activeChatId}
            loadChat={loadChat}
            createNewChat={createNewChat}
            refreshChats={fetchChats}
            privacyScrub={privacyScrub}
          />
        );
      case 'research_workspace':
        return <ResearchView />;
      case 'calendar':
        return <CalendarView onNavigate={setCurrentScreen} />;
      case 'meetings':
        return <MeetingsView onNavigate={setCurrentScreen} />;
      default:
        return <SummariesExpanded onNavigate={setCurrentScreen} activity={activity} tasks={tasks} onTaskCompleted={fetchTasks} />;
    }
  };

  const getActiveLink = () => {
    if (currentScreen === 'island_settings') return 'settings';
    if (currentScreen === 'notes_icon_sidebar') return 'notes';
    if (currentScreen === 'graph_view') return 'graph';
    if (currentScreen.includes('summaries')) return 'summaries';
    if (currentScreen === 'logs') return 'logs';
    if (currentScreen === 'archive') return 'archive';
    if (currentScreen === 'knowledge') return 'knowledge';
    if (currentScreen === 'research_workspace') return 'research';
    if (currentScreen === 'calendar') return 'calendar';
    if (currentScreen === 'meetings') return 'meetings';
    if (currentScreen === 'chat_expanded_sidebar') return 'transcripts';
    if (appMode === 'chat') return 'transcripts';
    if (appMode === 'research') return 'research';
    return 'notes';
  };

  const headerActions = (<div />);

  // Onboarding is a full-screen takeover. It used to be returned from
  // renderScreen(), which renders as Layout's children — so the sidebar rail,
  // the page header ("DASHBOARD") and the Island pill all showed through around
  // a first-run screen that is supposed to own the window. TitleBar is kept so
  // the window controls stay reachable during setup.
  if (!isIslandMode && settings && settings.onboarding_completed === false) {
    return (
      <div className="h-screen w-full flex flex-col bg-surface text-on-surface overflow-hidden">
        <TitleBar />
        <div className="flex-1 overflow-y-auto">
          <OnboardingView
            onComplete={() => setCurrentScreen('summaries_expanded')}
            activity={activity}
            updateSettings={updateSettings}
            settings={settings}
            scanEnvironment={scanEnvironment}
          />
        </div>
      </div>
    );
  }

  return (
    <div className={`${isIslandMode ? 'bg-transparent' : 'bg-surface text-on-surface selection:bg-primary/30 selection:text-on-surface'} h-screen w-full relative`}>
      <CommandPalette
        isOpen={cmdPaletteOpen}
        onClose={() => setCmdPaletteOpen(false)}
        onNavigate={handlePaletteNavigate}
        onNewNote={() => window.dispatchEvent(new CustomEvent('primnox:new-note'))}
        onNewChat={createNewChat}
        onSendMessage={(t) => sendMessage(t, activeChatId)}
      />
      {/* Disconnect Banner — hidden in island-pill mode */}
      {connectionLost && !isIslandMode && (
        <div className="fixed top-0 left-0 right-0 z-[300] bg-error/90 backdrop-blur-sm text-on-surface text-center py-3 px-6 flex items-center justify-center gap-4 shadow-lg">
          <div className="w-2 h-2 rounded-full bg-on-surface animate-pulse" />
          <span className="font-mono text-xs uppercase tracking-widest font-bold">Connection Lost — Backend Unreachable</span>
          <button onClick={manualReconnect} className="ml-4 px-4 py-1 bg-on-surface/20 hover:bg-on-surface/30 rounded text-xs font-bold transition-colors">Reconnect</button>
        </div>
      )}
      <Layout 
        sidebarState={sidebarState}
        onSidebarStateChange={changeSidebarState}
        onNavigate={setCurrentScreen}
        activeLink={getActiveLink()}
        isIslandVisible={isIslandVisible}
        onLogoClick={() => setIsIslandVisible(!isIslandVisible)}
        isZenMode={false}
        title={
          currentScreen === 'logs' ? 'System_Logs' :
          currentScreen === 'archive' ? 'Data_Vault' :
          currentScreen === 'knowledge' ? 'Knowledge_Nexus' :
          currentScreen === 'graph_view' ? 'Knowledge_Graph' :
          // Titles must match the sidebar label for the same screen. `summaries`
          // is Dashboard; it read `Neural_Nodes`, which is the Notes view, so
          // clicking Dashboard highlighted Dashboard but headed the page Notes.
          currentScreen.includes('summaries') ? 'Dashboard' :
          currentScreen === 'research_workspace' ? 'Deep_Research' :
          currentScreen === 'calendar' ? 'Calendar' :
          currentScreen === 'island_settings' ? 'Configure' :
          currentScreen === 'meetings' ? 'Recordings' :
          appMode === 'research' ? 'Deep_Research' :
          appMode === 'chat' ? 'Synapse_Stream' : 'Neural_Nodes'
        }
        subtitle={
          currentScreen === 'logs' ? 'DIAGNOSTIC_BUFFER' :
          currentScreen === 'archive' ? 'COLD_STORAGE' :
          currentScreen === 'knowledge' ? 'SYSTEM_CORE_DOCS' :
          currentScreen === 'graph_view' ? 'VISUALIZE_CONNECTIONS' :
          currentScreen.includes('summaries') ? 'SYNTHETIC_PROCESSING' :
          currentScreen === 'research_workspace' ? 'WEB_SEARCH_ENGINE' :
          currentScreen === 'calendar' ? 'SCHEDULE_GRID' :
          currentScreen === 'island_settings' ? 'SYSTEM_CORE' :
          currentScreen === 'meetings' ? 'MANUAL_REVIEW' :
          appMode === 'research' ? 'KNOWLEDGE_SYNTHESIS' :
          appMode === 'chat' ? 'NEURAL_INTERFACE' : 'WORKSPACE_v2'
        }
        aiName={aiCodename}
        appMode={appMode}
        setAppMode={(mode) => {
          setAppMode(mode);
          if (mode === 'notes') setCurrentScreen('notes_icon_sidebar');
          if (mode === 'chat') setCurrentScreen('chat_expanded_sidebar');
          if (mode === 'research') setCurrentScreen('research_workspace');
        }}
        status={status}
        setStatus={setStatus}
        toasts={toasts}
        transcript={currentTranscript}
        attachedFile={lastAttachedFile}
        errorPayload={islandError}
        onClearError={handleClearError}
        flowState={flowState}
        errorStreak={errorStreak}
        nowPlaying={nowPlaying}
        islandSkills={islandSkills}
        productivityScore={productivityScore}
        parallelTasks={parallelTasks}
        onSmartPaste={triggerSmartPaste}
        onMediaControl={triggerMediaControl}
        proactiveAlert={proactiveAlert}
        onDismissProactive={dismissProactiveAlert}
        onSuggestionClick={(s) => { sendMessage(s, activeChatId); dismissProactiveAlert(); }}
        isIslandMode={isIslandMode}
        onRestoreWindow={handleRestoreWindow}
        actions={headerActions}
      >
        <AnimatePresence mode="wait">
          <motion.div
             key={`${currentScreen}-${appMode}`}
             initial={{ opacity: 0, filter: 'blur(10px)', y: 10 }}
             animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }}
             exit={{ opacity: 0, filter: 'blur(10px)', y: -10 }}
             transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
             className="h-full w-full flex flex-col overflow-hidden"
          >
            {renderScreen()}
          </motion.div>
        </AnimatePresence>
      </Layout>
    </div>
  );
}
