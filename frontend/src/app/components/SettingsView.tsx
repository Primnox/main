import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { User, Terminal, Database, Shield, Cpu, Wifi, WifiOff, RefreshCw } from 'lucide-react';

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
  | 'knowledge';

export const IslandSettings = ({ 
  onNavigate,
  operatorAlias,
  setOperatorAlias,
  aiCodename,
  setAiCodename,
  activeModel,
  setActiveModel,
  apiKey,
  setApiKey,
  openaiApiKey,
  setOpenaiApiKey,
  anthropicApiKey,
  setAnthropicApiKey,
  vadSensitivity,
  setVadSensitivity,
  wakeWord,
  setWakeWord,
  wakeWordEnabled,
  setWakeWordEnabled,
  ollamaModel,
  setOllamaModel,
  ollamaBaseUrl,
  setOllamaBaseUrl,
  onSync
}: {
  onNavigate: (id: ScreenId) => void,
  operatorAlias: string,
  setOperatorAlias: (v: string) => void,
  aiCodename: string,
  setAiCodename: (v: string) => void,
  activeModel: string,
  setActiveModel: (v: string) => void,
  apiKey: string,
  setApiKey: (v: string) => void,
  openaiApiKey: string,
  setOpenaiApiKey: (v: string) => void,
  anthropicApiKey: string,
  setAnthropicApiKey: (v: string) => void,
  vadSensitivity: number,
  setVadSensitivity: (v: number) => void,
  wakeWord: string,
  setWakeWord: (v: string) => void,
  wakeWordEnabled: boolean,
  setWakeWordEnabled: (v: boolean) => void,
  ollamaModel: string,
  setOllamaModel: (v: string) => void,
  ollamaBaseUrl: string,
  setOllamaBaseUrl: (v: string) => void,
  onSync: () => void
}) => {
  const [activeTab, setActiveTab] = useState<'System_Core' | 'Identity' | 'Security'>('System_Core');
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean, models: string[] } | null>(null);
  const [checkingOllama, setCheckingOllama] = useState(false);

  const checkOllama = async () => {
    setCheckingOllama(true);
    try {
      const res = await fetch('http://localhost:8000/api/ollama/status');
      if (res.ok) {
        setOllamaStatus(await res.json());
      } else {
        // Non-2xx (e.g. 503 during backend startup) — treat as not running so the
        // icon doesn't stay in the spinning "checking..." state indefinitely.
        setOllamaStatus({ running: false, models: [] });
      }
    } catch (_) { setOllamaStatus({ running: false, models: [] }); }
    setCheckingOllama(false);
  };

  useEffect(() => {
    if (activeModel === 'Ollama_Local') checkOllama();
  }, [activeModel]);

  const tabs = [
    { id: 'System_Core', label: 'System_Core', icon: Cpu },
    { id: 'Identity', label: 'Identity', icon: User },
    { id: 'Security', label: 'Security', icon: Shield }
  ] as const;

  return (
    <div className="min-h-full flex items-center justify-center p-6 md:p-12 lg:p-20 text-left">
      <motion.div 
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-4xl w-full glass-panel rounded-lg shadow-2xl overflow-hidden border border-white/10 flex flex-col md:flex-row bg-[#050505]/80 backdrop-blur-3xl"
      >
        {/* Sidebar Tabs */}
        <div className="w-full md:w-72 border-r border-white/5 bg-zinc-950 p-10 space-y-4 flex flex-col justify-between">
          <div className="space-y-4">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button 
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`w-full text-left px-5 py-4 rounded-xl font-mono text-[11px] uppercase tracking-[0.3em] font-bold transition-all duration-300 ease-out active:scale-95 flex items-center gap-3 border
                    ${isActive 
                      ? 'bg-primary/10 text-primary border-primary/20 shadow-lg shadow-primary/5' 
                      : 'text-white/25 border-transparent hover:text-white hover:bg-white/5'}`}
                >
                  <Icon size={14} />
                  {tab.label}
                </button>
              );
            })}
          </div>
          
          <div className="pt-20">
            <div className="p-6 rounded-2xl border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-sm">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.8)]" />
                <span className="font-mono text-[10px] text-emerald-400 uppercase font-bold tracking-widest">Kernel_Stable</span>
              </div>
              <p className="text-[10px] text-emerald-400/40 font-mono tracking-tighter uppercase whitespace-nowrap leading-none">Active Engine: {activeModel}</p>
            </div>
          </div>
        </div>

        {/* Content Panel */}
        <div className="flex-1 p-10 lg:p-16 space-y-16 flex flex-col justify-between">
          <div className="space-y-12">
            <header className="space-y-4 border-b border-white/5 pb-10">
              <h2 className="font-bold lowercase italic tracking-wide text-4xl text-white">Machine_Cognition_Settings</h2>
              <p className="text-white/30 font-light text-lg">Calibrate the neural interface and operative parameters.</p>
            </header>

            {/* Render Tab Contents */}
            <div className="min-h-[220px]">
              {activeTab === 'System_Core' && (
                <motion.section 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="space-y-6"
                >
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Co_Processor_Engine</label>
                    <div className="relative group">
                      <Database size={16} className="absolute left-5 top-1/2 -translate-y-1/2 text-white/10 group-focus-within:text-primary transition-colors pointer-events-none" />
                      <select 
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none appearance-none cursor-pointer hover:bg-zinc-900 transition-all"
                        value={activeModel}
                        onChange={(e) => setActiveModel(e.target.value)}
                      >
                        <option value="Groq_Llama_3">Groq: Llama 3.3 (HyperSpeed)</option>
                        <option value="OpenAI_GPT_4o">OpenAI: GPT-4o (Max Reasoning)</option>
                        <option value="Anthropic_Claude_3">Anthropic: Claude 3.5 Sonnet</option>
                        <option value="Ollama_Local">⚡ Ollama: Local / Hybrid (No API Key)</option>
                      </select>
                    </div>
                  </div>

                  {/* ── Ollama Config Panel ── */}
                  {activeModel === 'Ollama_Local' && (
                    <motion.div
                      initial={{ opacity: 0, y: -8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className="rounded-xl border border-primary/20 bg-primary/5 p-5 space-y-4"
                    >
                      {/* Status row */}
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {ollamaStatus === null || checkingOllama ? (
                            <RefreshCw size={12} className="text-white/30 animate-spin" />
                          ) : ollamaStatus.running ? (
                            <Wifi size={12} className="text-emerald-400" />
                          ) : (
                            <WifiOff size={12} className="text-red-400" />
                          )}
                          <span className="font-mono text-[10px] uppercase tracking-widest text-white/50">
                            {checkingOllama ? 'Checking...' : ollamaStatus?.running ? `Ollama Running — ${ollamaStatus.models.length} model(s)` : 'Ollama Not Detected'}
                          </span>
                        </div>
                        <button onClick={checkOllama} className="text-[10px] font-mono text-white/30 hover:text-primary transition-colors uppercase tracking-widest">
                          Refresh
                        </button>
                      </div>

                      {!ollamaStatus?.running && (
                        <p className="text-[10px] text-amber-400/70 font-mono">
                          Run <span className="text-amber-300 bg-white/5 px-1 rounded">ollama serve</span> in a terminal, then refresh. Install a model with <span className="text-amber-300 bg-white/5 px-1 rounded">ollama pull llama3.2</span>
                        </p>
                      )}

                      {/* Model picker */}
                      <div className="space-y-2">
                        <label className="block font-mono text-[9px] text-white/30 uppercase tracking-[0.4em]">Local_Model</label>
                        {ollamaStatus?.running && ollamaStatus.models.length > 0 ? (
                          <select
                            className="w-full bg-black/60 border border-white/10 rounded-xl py-3 px-4 font-mono text-xs focus:ring-1 focus:ring-primary outline-none appearance-none"
                            value={ollamaModel}
                            onChange={e => setOllamaModel(e.target.value)}
                          >
                            {ollamaStatus.models.map(m => (
                              <option key={m} value={m}>{m}</option>
                            ))}
                          </select>
                        ) : (
                          <input
                            className="w-full bg-black/60 border border-white/10 rounded-xl py-3 px-4 font-mono text-xs focus:ring-1 focus:ring-primary outline-none"
                            value={ollamaModel}
                            onChange={e => setOllamaModel(e.target.value)}
                            placeholder="e.g. llama3.2, mistral, codellama"
                          />
                        )}
                      </div>

                      {/* Base URL */}
                      <div className="space-y-2">
                        <label className="block font-mono text-[9px] text-white/30 uppercase tracking-[0.4em]">Ollama_URL</label>
                        <input
                          className="w-full bg-black/60 border border-white/10 rounded-xl py-3 px-4 font-mono text-xs focus:ring-1 focus:ring-primary outline-none"
                          value={ollamaBaseUrl}
                          onChange={e => setOllamaBaseUrl(e.target.value)}
                          placeholder="http://localhost:11434"
                        />
                      </div>

                      <p className="text-[9px] text-white/20 font-mono">
                        Note: Transcription (Whisper) still uses Groq even in local mode — add a Groq key in Security tab for that.
                      </p>
                    </motion.div>
                  )}

                  {/* VAD Sensitivity Slider */}
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">VAD_Sensitivity</label>
                    <div className="flex items-center gap-4 bg-black/40 border border-white/5 p-4 rounded-xl">
                      <input 
                        type="range" 
                        min="0" 
                        max="1" 
                        step="0.05"
                        className="w-full h-1 bg-white/10 rounded-lg appearance-none cursor-pointer accent-primary" 
                        value={vadSensitivity}
                        onChange={(e) => setVadSensitivity(parseFloat(e.target.value))}
                      />
                      <span className="font-mono text-xs text-primary font-bold min-w-[36px] text-right">{(vadSensitivity * 100).toFixed(0)}%</span>
                    </div>
                  </div>

                  {/* Wake Word Config */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6 bg-black/40 border border-white/5 p-4 rounded-xl">
                    <div className="space-y-4">
                      <label className="block font-mono text-[10px] text-white/25 uppercase tracking-[0.3em] font-bold">Wake_Word</label>
                      <input 
                        className="w-full bg-zinc-950 border border-white/10 rounded-xl py-3 px-4 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all" 
                        value={wakeWord}
                        onChange={(e) => setWakeWord(e.target.value)}
                        placeholder="Wake word phrase..."
                      />
                    </div>
                    <div className="space-y-4 flex flex-col justify-between">
                      <label className="block font-mono text-[10px] text-white/25 uppercase tracking-[0.3em] font-bold">Wake_Word_Detection</label>
                      <div className="flex items-center h-full pb-1">
                        <button
                          type="button"
                          onClick={() => setWakeWordEnabled(!wakeWordEnabled)}
                          className={`w-full py-3 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold border transition-all active:scale-95 cursor-pointer
                            ${wakeWordEnabled 
                              ? 'bg-primary/10 border-primary/20 text-primary hover:bg-primary/20' 
                              : 'bg-white/5 border-transparent text-white/40 hover:text-white/60'}`}
                        >
                          {wakeWordEnabled ? "Enabled" : "Disabled"}
                        </button>
                      </div>
                    </div>
                  </div>
                </motion.section>
              )}

              {activeTab === 'Identity' && (
                <motion.section 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="grid grid-cols-1 md:grid-cols-2 gap-12"
                >
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Operative_Alias</label>
                    <div className="relative group">
                      <User size={16} className="absolute left-5 top-1/2 -translate-y-1/2 text-white/10 group-focus-within:text-primary transition-colors" />
                      <input 
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5" 
                        value={operatorAlias}
                        onChange={(e) => setOperatorAlias(e.target.value)}
                      />
                    </div>
                  </div>
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Neural_ID</label>
                    <div className="relative group">
                      <Terminal size={16} className="absolute left-5 top-1/2 -translate-y-1/2 text-white/10 group-focus-within:text-primary transition-colors" />
                      <input 
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5" 
                        value={aiCodename}
                        onChange={(e) => setAiCodename(e.target.value)}
                      />
                    </div>
                  </div>
                </motion.section>
              )}

              {activeTab === 'Security' && (
                <motion.section 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="space-y-6"
                >
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Groq_API_Key</label>
                    <div className="relative group">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 font-mono text-[10px] text-white/10 font-bold">HEX</div>
                      <input 
                        type="password"
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5" 
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="Groq API key..."
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">OpenAI_API_Key</label>
                    <div className="relative group">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 font-mono text-[10px] text-white/10 font-bold">HEX</div>
                      <input 
                        type="password"
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5" 
                        value={openaiApiKey}
                        onChange={(e) => setOpenaiApiKey(e.target.value)}
                        placeholder="OpenAI API key..."
                      />
                    </div>
                  </div>

                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Anthropic_API_Key</label>
                    <div className="relative group">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 font-mono text-[10px] text-white/10 font-bold">HEX</div>
                      <input 
                        type="password"
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5" 
                        value={anthropicApiKey}
                        onChange={(e) => setAnthropicApiKey(e.target.value)}
                        placeholder="Anthropic API key..."
                      />
                    </div>
                  </div>
                </motion.section>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between pt-12 border-t border-white/5 pb-8">
            <button 
              type="button"
              onClick={() => onNavigate('summaries_expanded')}
              className="text-white/20 font-mono text-[11px] uppercase tracking-widest hover:text-white transition-colors font-bold"
            >
              Discard_Changes
            </button>
            <button 
              type="button"
              onClick={onSync}
              className="bg-white text-black font-mono px-14 py-4 rounded-2xl uppercase text-[12px] font-bold tracking-[0.2em] hover:bg-primary hover:text-white transition-all shadow-3xl active:scale-90"
            >
              Synchronize_Kernel
            </button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
