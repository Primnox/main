/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { usePrimnox } from '../hooks/usePrimnox';
import { Mic, MicOff, Sparkles } from 'lucide-react';

// Components
import { Layout } from './components/Layout';
import { SummariesExpanded, SummariesSidebarHidden, SummariesEmptyState, SummariesIconSidebar } from './components/SummaryViews';
import { NotesIconSidebar } from './components/NotesView';
import { IslandSettings } from './components/SettingsView';
import { ChatExpandedSidebar } from './components/ChatView';
import { LogsPage } from './components/LogView';
import { DataVaultPage } from './components/MemoryView';
import { KnowledgePage } from './components/AboutView';
import { OnboardingView } from './components/OnboardingView';
import { GraphView } from './components/GraphView';

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
  | 'graph_view';

export type SidebarState = 'expanded' | 'icon' | 'hidden';
export type AppMode = 'chat' | 'notes' | 'research';
export type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

const ResearchWorkspace = () => (
  <div className="h-full flex flex-col items-center justify-center p-10 text-center">
    <div className="w-16 h-16 rounded-2xl bg-white/5 border border-white/10 flex items-center justify-center mb-6 shadow-2xl">
      <Sparkles className="text-white/40" size={24} />
    </div>
    <h2 className="text-xl font-mono text-white/80 uppercase tracking-widest mb-2">Deep_Research</h2>
    <p className="text-white/40 font-light max-w-md">The Research workspace is currently locked. Data aggregation engines and knowledge synthesis protocols will be deployed here soon.</p>
  </div>
);

export default function App() {
  const { 
    messages: liveMessages, 
    state: liveState, 
    vadLevel, 
    notes, 
    memory,
    toasts,
    activity,
    currentTranscript,
    lastAttachedFile,
    settings,
    micMuted,
    connectionLost,
    manualReconnect,
    toggleMic,
    sendMessage,
    updateSettings,
    exportNotes,
    chatSessions,
    chatFolders,
    activeChatId,
    fetchChats: _fetchChats,
    loadChat,
    createNewChat,
    addToast
  } = usePrimnox();

  const [currentScreen, setCurrentScreen] = useState<ScreenId>('summaries_expanded');
  const [appMode, setAppMode] = useState<AppMode>('notes');
  const [status, setStatus] = useState<AiStatus>('idle');
  const [isIslandVisible, setIsIslandVisible] = useState(true);
  
  // Sync live state to UI status
  useEffect(() => {
    if (liveState === 'thinking') setStatus('thinking');
    else if (liveState === 'listening') setStatus('listening');
    else if (liveState === 'speaking') setStatus('transcript');
    else setStatus('idle');
  }, [liveState]);

  // IPC listeners
  useEffect(() => {
    if ((window as any).electron) {
      const cleanup = (window as any).electron.ipcRenderer.on('friday:open-notes', () => {
        setAppMode('notes');
        setCurrentScreen('notes_icon_sidebar');
      });
      return cleanup;
    }
  }, []);

  // System State (Local overrides)
  const [operatorAlias, setOperatorAlias] = useState('ANIKETH_P_01');
  const [aiCodename, setAiCodename] = useState('PRIMNOX');
  const [activeModel, setActiveModel] = useState('Groq_Llama_3');
  const [apiKey, setApiKey] = useState('');
  const [openaiApiKey, setOpenaiApiKey] = useState('');
  const [anthropicApiKey, setAnthropicApiKey] = useState('');
  const [vadSensitivity, setVadSensitivity] = useState(0.5);
  const [wakeWord, setWakeWord] = useState('hey primnox');
  const [wakeWordEnabled, setWakeWordEnabled] = useState(true);

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
      wake_word_enabled: wakeWordEnabled
    });
    setCurrentScreen('summaries_expanded');
  };

  const renderScreen = () => {
    let targetScreen = currentScreen;

    if (settings && settings.onboarding_completed === false) {
      return <OnboardingView onComplete={() => setCurrentScreen('summaries_expanded')} />;
    }

    switch (targetScreen) {
      case 'summaries_expanded':
        return <SummariesExpanded onNavigate={setCurrentScreen} activity={activity} />;
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
        return <DataVaultPage onAccess={() => addToast('info', 'Data Vault Access: Synchronizing...')} memory={memory} />;
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
            onSync={handleSync}
          />
        );
      case 'summaries_icon_sidebar':
        return <SummariesIconSidebar onNavigate={setCurrentScreen} notes={notes} />;
      case 'notes_icon_sidebar':
        return <NotesIconSidebar notes={notes} onExport={exportNotes} sendMessage={sendMessage} />;
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
          />
        );
      case 'research_workspace':
        return <ResearchWorkspace />;
      default:
        return <SummariesExpanded onNavigate={setCurrentScreen} />;
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
    if (appMode === 'chat') return 'transcripts';
    return 'notes';
  };

  const headerActions = (
    <div className="flex items-center gap-4">
      <button 
        onClick={toggleMic}
        className={`px-4 py-2 rounded-xl border font-mono text-[9px] uppercase tracking-widest font-bold flex items-center gap-2 active:scale-95 transition-all cursor-pointer
          ${micMuted 
            ? 'bg-red-500/10 border-red-500/20 text-red-500 hover:bg-red-500/20' 
            : 'bg-primary/10 border-primary/20 text-primary hover:bg-primary/20'}`}
        title={micMuted ? "Unmute Microphone" : "Mute Microphone"}
      >
        {micMuted ? <MicOff size={12} /> : <Mic size={12} />}
        <span>{micMuted ? "Mic_Off" : "Mic_On"}</span>
      </button>
    </div>
  );

  return (
    <div className={`bg-black text-on-surface h-screen w-full relative selection:bg-primary/30 selection:text-white`}>
      {/* Disconnect Banner */}
      {connectionLost && (
        <div className="fixed top-0 left-0 right-0 z-[300] bg-red-500/90 backdrop-blur-sm text-white text-center py-3 px-6 flex items-center justify-center gap-4 shadow-lg">
          <div className="w-2 h-2 rounded-full bg-white animate-pulse" />
          <span className="font-mono text-xs uppercase tracking-widest font-bold">Connection Lost — Backend Unreachable</span>
          <button onClick={manualReconnect} className="ml-4 px-4 py-1 bg-white/20 hover:bg-white/30 rounded text-xs font-bold transition-colors">Reconnect</button>
        </div>
      )}
      <Layout 
        sidebarState={currentScreen === 'chat_expanded_sidebar' || currentScreen === 'summaries_expanded' ? 'expanded' : currentScreen === 'summaries_sidebar_hidden' ? 'hidden' : 'icon'} 
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
          currentScreen.includes('summaries') ? 'Neural_Nodes' : 
          appMode === 'research' ? 'Deep_Research' :
          appMode === 'chat' ? 'Synapse_Stream' : 'Neural_Nodes'
        }
        subtitle={
          currentScreen === 'logs' ? 'DIAGNOSTIC_BUFFER' :
          currentScreen === 'archive' ? 'COLD_STORAGE' :
          currentScreen === 'knowledge' ? 'SYSTEM_CORE_DOCS' :
          currentScreen === 'graph_view' ? 'VISUALIZE_CONNECTIONS' :
          currentScreen.includes('summaries') ? 'SYNTHETIC_PROCESSING' : 
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
        vadLevel={vadLevel}
        transcript={currentTranscript}
        attachedFile={lastAttachedFile}
        micMuted={micMuted}
        onMicClick={toggleMic}
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
