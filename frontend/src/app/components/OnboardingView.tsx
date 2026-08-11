import { useState, useEffect, useRef, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Sparkles, Check, Brain, Shield, Eye, ShieldAlert,
  Loader2, Terminal, Compass, LayoutDashboard, MessageSquare, Cpu, Plug, RefreshCw
} from 'lucide-react';
import { FlowLocal, FlowCloud } from './FlowDiagram';
import { API_BASE } from '../../config';

/** Mirrors brain.py's _is_local_url / SettingsView's isCustomUrlLocal — a Custom
 *  provider's local-vs-cloud classification (and therefore whether Privacy
 *  Mirror applies) is auto-detected from the base URL, not a separate toggle. */
const isCustomUrlLocal = (url: string): boolean =>
  /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?\/?$/.test((url || '').trim());
// Props are injected from App so we share the single WebSocket connection.
interface OnboardingViewProps {
  onComplete: () => void;
  activity: any[];
  updateSettings: (s: any) => void;
  settings: any;
  scanEnvironment: () => Promise<any>;
}

export const OnboardingView = ({ onComplete, activity, updateSettings, settings, scanEnvironment }: OnboardingViewProps) => {
  const [step, setStep] = useState(1);
  const totalSteps = 13;
  const [profile, setProfile] = useState<any>({
    name: 'User',
    role: 'System Administrator',
    projects: ['<Scanning Local Workspace>'],
    topics: ['<Analyzing Interests>'],
    skills: ['<Mapping Capabilities>'],
    communication_style: ['<Observing Patterns>'],
    knowledge_areas: ['<Building Knowledge Graph>']
  });
  
  // Must be stable. As a fresh closure each render it changed identity on every
  // render, and Step6Learning lists it as an effect dependency — so that effect
  // tore down and re-ran continuously, restarting its scan and never advancing.
  const nextStep = useCallback(() => setStep(prev => Math.min(prev + 1, totalSteps)), [totalSteps]);
  const skipSetup = () => {
    updateSettings({ ...settings, onboarding_completed: true });
    onComplete();
  };

  const estimatedTime = Math.ceil((totalSteps - step) * 0.5);

  const renderStepIndicator = () => (
    <div className="fixed top-8 left-8 right-8 flex justify-between items-center z-50">
      <div className="flex items-center gap-4">
        <div className="w-8 h-8 rounded-full border border-primary/30 flex items-center justify-center bg-primary/10 text-primary">
          <Terminal size={14} />
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-on-surface tracking-tighter uppercase">Primnox</span>
          <span className="text-[8px] font-mono text-primary uppercase tracking-[0.2em]">Initialization</span>
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-end text-right">
          <span className="text-xs text-on-surface/50 font-mono">Step {step} of {totalSteps}</span>
          <span className="text-[10px] text-primary/70 font-mono">~{estimatedTime} Minutes Remaining</span>
        </div>
        <button onClick={skipSetup} className="text-xs text-on-surface/60 hover:text-on-surface transition-all duration-300 ease-out active:scale-95">
          Skip For Now
        </button>
      </div>
    </div>
  );

  return (
    <div className="h-full w-full text-on-surface overflow-hidden relative flex flex-col items-center justify-center font-sans">
      {/* Background Ambience */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/5 via-surface to-surface opacity-50 z-0" />
      
      {renderStepIndicator()}
      
      <div className="w-full max-w-3xl relative z-10 px-8">
        <AnimatePresence mode="wait">
          {step === 1 && <Step1Welcome key="step1" next={nextStep} skip={skipSetup} />}
          {step === 2 && <Step2Privacy key="step2" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 3 && <Step3AIProvider key="step3" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 4 && <Step4Permissions key="step4" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 5 && <Step5Voice key="step5" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 6 && <Step6Learning key="step6" next={nextStep} activity={activity} profile={profile} scanEnvironment={scanEnvironment} setProfile={setProfile} />}
          {step === 7 && <Step7UserModel key="step7" next={nextStep} updateSettings={updateSettings} settings={settings} profile={profile} />}
          {step === 8 && <Step8ProfileReview key="step8" next={nextStep} profile={profile} setProfile={setProfile} />}
          {step === 9 && <Step9Memory key="step9" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 10 && <Step10Personalization key="step10" next={nextStep} updateSettings={updateSettings} settings={settings} />}
          {step === 11 && <Step11Workspace key="step11" next={nextStep} updateSettings={updateSettings} settings={settings} profile={profile} />}
          {step === 12 && <Step12AssistantGen key="step12" next={nextStep} />}
          {step === 13 && <Step13Completion key="step13" onComplete={skipSetup} profile={profile} />}
        </AnimatePresence>
      </div>
    </div>
  );
};

// ============================================================================
// STEP COMPONENTS
// ============================================================================

const Step1Welcome = ({ next, skip }: any) => (
  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="flex flex-col gap-6 text-center">
    <div className="w-20 h-20 rounded-full border border-primary/30 flex items-center justify-center bg-primary/10 text-primary mx-auto mb-4 shadow-[0_0_30px_rgba(79,70,229,0.3)]">
      <Sparkles size={32} />
    </div>
    <h1 className="font-bold lowercase italic tracking-wide text-4xl text-on-surface">Welcome to Primnox</h1>
    <h2 className="font-bold lowercase italic tracking-wide text-xl text-primary font-mono uppercase">Your AI Operating Environment</h2>
    <p className="text-on-surface/50 max-w-lg mx-auto text-sm leading-relaxed mb-8">
      An assistant that learns your projects, workflows, communication style, and preferences over time. Primnox is not being configured. Primnox is learning.
    </p>
    <div className="flex items-center justify-center gap-4">
      <button onClick={next} className="px-8 py-3 bg-on-surface text-surface font-bold text-sm rounded-lg hover:bg-on-surface/90 shadow-[0_0_20px_rgba(255,255,255,0.2)] transition-all duration-300 ease-out active:scale-95">
        Begin Setup
      </button>
      <button onClick={skip} className="px-8 py-3 bg-on-surface/5 text-on-surface/70 font-medium text-sm rounded-lg hover:bg-on-surface/10 border border-on-surface/10 transition-all duration-300 ease-out active:scale-95">
        Skip Setup
      </button>
    </div>
  </motion.div>
);


const Step2Privacy = ({ next, updateSettings, settings }: any) => {
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean, models: string[] } | null>(null);
  const [selected, setSelected] = useState<'cloud' | 'ollama' | 'llamacpp' | 'custom' | null>(null);
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [llamaUrl, setLlamaUrl] = useState('http://localhost:8080');
  const [llamaModel, setLlamaModel] = useState('');
  const [customApiType, setCustomApiType] = useState<'openai' | 'anthropic'>('openai');
  const [customBaseUrl, setCustomBaseUrl] = useState('');
  const [customApiKey, setCustomApiKey] = useState('');
  const [customModel, setCustomModel] = useState('');
  const [customAvailableModels, setCustomAvailableModels] = useState<string[]>([]);
  const [detectingCustomModels, setDetectingCustomModels] = useState(false);
  const [customModelsError, setCustomModelsError] = useState<string | null>(null);

  const detectCustomModels = async () => {
    setDetectingCustomModels(true);
    setCustomModelsError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/custom_provider/models`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ base_url: customBaseUrl, api_type: customApiType, api_key: customApiKey }),
      });
      const d = await resp.json();
      if (d?.models?.length) setCustomAvailableModels(d.models);
      else { setCustomAvailableModels([]); setCustomModelsError(d?.error || 'No models found at that URL.'); }
    } catch {
      setCustomAvailableModels([]);
      setCustomModelsError('Could not reach that URL.');
    }
    setDetectingCustomModels(false);
  };

  useEffect(() => {
    fetch(`${API_BASE}/api/ollama/status`)
      .then(r => r.json())
      .then(d => {
        setOllamaStatus(d);
        if (d.models?.length) setOllamaModel(d.models[0]);
      })
      .catch(() => setOllamaStatus({ running: false, models: [] }));
  }, []);

  const confirmOllama = () => {
    updateSettings({ ...settings, active_model: 'Ollama_Local', ollama_base_url: ollamaUrl, ollama_model: ollamaModel });
    next();
  };
  const confirmLlamaCpp = () => {
    updateSettings({ ...settings, active_model: 'LlamaCpp_Local', llamacpp_base_url: llamaUrl, llamacpp_model: llamaModel });
    next();
  };
  const confirmCloud = () => {
    const cloudModels = ['Groq_Llama_3', 'OpenAI_GPT_4o', 'Anthropic_Claude_3', 'Gemini_Flash'];
    const current = settings?.active_model;
    const model = cloudModels.includes(current) ? current : 'Groq_Llama_3';
    updateSettings({ ...settings, active_model: model, privacy_mirror_enabled: true });
    next();
  };
  const confirmCustom = () => {
    // Settings stores custom endpoints as a named-profile list (so you can save
    // more than one later in Settings), not the flat fields this screen used
    // to write — this profile becomes profile #1, selected as active.
    const id = (crypto.randomUUID?.() || `${Date.now()}`).replace(/-/g, '').slice(0, 8);
    updateSettings({
      ...settings,
      active_model: 'Custom',
      active_custom_provider_id: id,
      custom_providers: [
        ...(settings?.custom_providers || []),
        { id, name: 'Custom', api_type: customApiType, base_url: customBaseUrl, api_key: customApiKey, model: customModel },
      ],
    });
    next();
  };

  const cardBase = 'flex flex-col items-start text-left p-5 rounded-xl border transition-all relative cursor-pointer';

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-6">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Privacy Architecture</h2>
        <p className="text-on-surface/50 text-sm">Choose how Primnox thinks. You can change this any time in Settings.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Cloud */}
        <button
          onClick={() => setSelected(s => s === 'cloud' ? null : 'cloud')}
          className={`${cardBase} ${selected === 'cloud' ? 'border-primary/60 bg-primary/10' : 'border-primary/30 bg-primary/5 hover:bg-primary/10 hover:scale-[1.02]'}`}
        >
          <Eye size={22} className="text-primary mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Cloud Assisted</h3>
          <p className="text-[10px] text-on-surface/50 leading-relaxed">Groq / OpenAI / Anthropic. Maximum speed.</p>
        </button>

        {/* Ollama */}
        <button
          onClick={() => setSelected(s => s === 'ollama' ? null : 'ollama')}
          className={`${cardBase} ${selected === 'ollama' ? 'border-success/60 bg-success/10' : 'border-success/20 bg-success/5 hover:bg-success/10 hover:scale-[1.02]'}`}
        >
          <div className={`absolute top-3 right-3 flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[8px] font-mono ${
            ollamaStatus === null ? 'bg-on-surface/10 text-on-surface/55' :
            ollamaStatus.running ? 'bg-success/20 text-success' : 'bg-on-surface/5 text-on-surface/48'
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${ollamaStatus === null ? 'bg-on-surface/20 animate-pulse' : ollamaStatus.running ? 'bg-success/25 animate-pulse' : 'bg-on-surface/20'}`} />
            {ollamaStatus === null ? 'checking…' : ollamaStatus.running ? 'detected' : 'not running'}
          </div>
          <ShieldAlert size={22} className="text-success mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Ollama — Local</h3>
          <p className="text-[10px] text-on-surface/50 leading-relaxed">On-device via Ollama. No chat leaves your machine.</p>
        </button>

        {/* llama.cpp */}
        <button
          onClick={() => setSelected(s => s === 'llamacpp' ? null : 'llamacpp')}
          className={`${cardBase} ${selected === 'llamacpp' ? 'border-primary/60 bg-primary/10' : 'border-primary/20 bg-primary/5 hover:bg-primary/10 hover:scale-[1.02]'}`}
        >
          <Cpu size={22} className="text-primary mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">llama.cpp — Local GGUF</h3>
          <p className="text-[10px] text-on-surface/50 leading-relaxed">Run any GGUF model via llama-server. Fully offline.</p>
        </button>

        {/* Custom endpoint */}
        <button
          onClick={() => setSelected(s => s === 'custom' ? null : 'custom')}
          className={`${cardBase} ${selected === 'custom' ? 'border-primary/60 bg-primary/10' : 'border-primary/20 bg-primary/5 hover:bg-primary/10 hover:scale-[1.02]'}`}
        >
          <Plug size={22} className="text-primary mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Custom</h3>
          <p className="text-[10px] text-on-surface/50 leading-relaxed">Your own endpoint — vLLM, LM Studio, OpenRouter, a self-hosted proxy, etc.</p>
        </button>

        {/* Local Only — coming soon */}
        <div className={`${cardBase} border-on-surface/5 bg-on-surface/5 opacity-40 cursor-not-allowed`}>
          <span className="absolute top-3 right-3 text-[8px] font-mono text-on-surface/55 bg-on-surface/5 px-2 py-0.5 rounded-full uppercase tracking-widest">soon</span>
          <Shield size={22} className="text-on-surface/55 mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Local Only</h3>
          <p className="text-[10px] text-on-surface/60 leading-relaxed">100% on-device, no server needed. Coming soon.</p>
        </div>
      </div>

      {/* Ollama config panel */}
      <AnimatePresence>
        {selected === 'ollama' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-success/20 bg-success/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-success/70 uppercase tracking-widest font-bold">Ollama Config</p>
              {!ollamaStatus?.running && (
                <p className="text-[10px] text-warn/80 font-mono">
                  Run <span className="bg-on-surface/5 px-1 rounded text-warn">ollama serve</span> then{' '}
                  <span className="bg-on-surface/5 px-1 rounded text-warn">ollama pull llama3.2</span> to get started.
                </p>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Server URL</label>
                  <input value={ollamaUrl} onChange={e => setOllamaUrl(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-success/40 text-on-surface/80"
                    placeholder="http://localhost:11434" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Model</label>
                  {ollamaStatus?.running && ollamaStatus.models.length > 0 ? (
                    <select value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                      className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-success/40 text-on-surface/80 appearance-none">
                      {ollamaStatus.models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                      className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-success/40 text-on-surface/80"
                      placeholder="llama3.2" />
                  )}
                </div>
              </div>
              <div className="border-t border-success/10 pt-2">
                <FlowLocal />
              </div>
              <button onClick={confirmOllama}
                className="w-full py-2.5 bg-success/20 hover:bg-success/30 border border-success/30 text-success rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95">
                Use Ollama → Continue
              </button>
            </div>
          </motion.div>
        )}

        {/* llama.cpp config panel */}
        {selected === 'llamacpp' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-primary/20 bg-primary/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-primary/70 uppercase tracking-widest font-bold">llama.cpp Config</p>
              <p className="text-[10px] text-warn/80 font-mono">
                Start with: <span className="bg-on-surface/5 px-1 rounded text-warn">./llama-server -m model.gguf --port 8080</span>
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Server URL</label>
                  <input value={llamaUrl} onChange={e => setLlamaUrl(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80"
                    placeholder="http://localhost:8080" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Model Name <span className="text-on-surface/48">(optional)</span></label>
                  <input value={llamaModel} onChange={e => setLlamaModel(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80"
                    placeholder="leave blank for default" />
                </div>
              </div>
              <div className="border-t border-primary/10 pt-2">
                <FlowLocal />
              </div>
              <button onClick={confirmLlamaCpp}
                className="w-full py-2.5 bg-primary/20 hover:bg-primary/30 border border-primary/30 text-primary rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95">
                Use llama.cpp → Continue
              </button>
            </div>
          </motion.div>
        )}

        {/* Custom config panel */}
        {selected === 'custom' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-primary/20 bg-primary/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-primary/70 uppercase tracking-widest font-bold">Custom Endpoint Config</p>
              <div className="flex gap-2">
                <button onClick={() => setCustomApiType('openai')}
                  className={`flex-1 py-2 text-[10px] uppercase tracking-wider font-bold rounded border transition-all ${customApiType === 'openai' ? 'bg-primary/20 border-primary text-on-surface' : 'bg-transparent border-on-surface/10 text-on-surface/50 hover:bg-on-surface/5'}`}>
                  OpenAI-compatible
                </button>
                <button onClick={() => setCustomApiType('anthropic')}
                  className={`flex-1 py-2 text-[10px] uppercase tracking-wider font-bold rounded border transition-all ${customApiType === 'anthropic' ? 'bg-primary/20 border-primary text-on-surface' : 'bg-transparent border-on-surface/10 text-on-surface/50 hover:bg-on-surface/5'}`}>
                  Anthropic-compatible
                </button>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Base URL</label>
                  <input value={customBaseUrl} onChange={e => setCustomBaseUrl(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80"
                    placeholder="http://localhost:8000 or https://api.example.com" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">API Key <span className="text-on-surface/48">(optional)</span></label>
                  <input type="password" value={customApiKey} onChange={e => setCustomApiKey(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80"
                    placeholder="leave blank if none needed" />
                </div>
              </div>
              <div className="space-y-1.5">
                <label className="font-mono text-[9px] text-on-surface/55 uppercase tracking-widest">Model</label>
                <div className="flex gap-2">
                  <input value={customModel} onChange={e => setCustomModel(e.target.value)}
                    className="flex-1 bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80"
                    placeholder="model-name" />
                  <button onClick={detectCustomModels} disabled={detectingCustomModels || !customBaseUrl}
                    className="px-4 bg-primary/20 hover:bg-primary/30 border border-primary/30 text-primary rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95 disabled:opacity-40 flex items-center gap-1.5 whitespace-nowrap">
                    <RefreshCw size={11} className={detectingCustomModels ? 'animate-spin' : ''} />
                    {detectingCustomModels ? 'Detecting' : 'Detect'}
                  </button>
                </div>
                {customModelsError && <p className="text-[10px] text-error font-mono">{customModelsError}</p>}
                {customAvailableModels.length > 0 && (
                  <select value={customModel} onChange={e => setCustomModel(e.target.value)}
                    className="w-full bg-surface/60 border border-on-surface/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-primary/40 text-on-surface/80 appearance-none">
                    {customAvailableModels.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                )}
              </div>
              <div className="border-t border-primary/10 pt-2">
                {isCustomUrlLocal(customBaseUrl) ? <FlowLocal /> : <FlowCloud />}
              </div>
              <p className="text-[10px] text-on-surface/55 font-mono">
                Local vs cloud is auto-detected from the URL — localhost/127.0.0.1 skips Privacy Mirror, anything else is scrubbed like a cloud provider.
              </p>
              <button onClick={confirmCustom} disabled={!customBaseUrl}
                className="w-full py-2.5 bg-primary/20 hover:bg-primary/30 border border-primary/30 text-primary rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95 disabled:opacity-40">
                Use Custom → Continue
              </button>
            </div>
          </motion.div>
        )}

        {/* Cloud continue */}
        {selected === 'cloud' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-primary/20 bg-primary/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-primary/60 uppercase tracking-widest font-bold">Cloud + Privacy Mirror</p>
              <FlowCloud />
              <p className="text-[10px] text-on-surface/55 font-mono">
                Privacy Mirror is <span className="text-success">on by default</span> — your name, email, and phone are pseudonymised before leaving your machine. You can toggle it in Settings → Security.
              </p>
              <button onClick={confirmCloud}
                className="w-full py-2.5 bg-primary/20 hover:bg-primary/30 border border-primary/30 text-primary rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95">
                Use Cloud → Continue
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

const Step3AIProvider = ({ next, updateSettings, settings }: any) => {
  const [key, setKey] = useState('');
  const [status, setStatus] = useState<'idle'|'testing'|'success'|'error'>('idle');
  const isLocalMode = settings?.active_model === 'Ollama_Local' || settings?.active_model === 'LlamaCpp_Local' || settings?.active_model === 'Custom';
  const localModelName = settings?.active_model === 'LlamaCpp_Local' ? 'llama.cpp' : settings?.active_model === 'Custom' ? 'your custom endpoint' : 'Ollama';

  const testKey = async () => {
    setStatus('testing');
    try {
      const resp = await fetch('https://api.groq.com/openai/v1/models', {
        headers: { 'Authorization': `Bearer ${key}` }
      });
      if (resp.ok) {
        setStatus('success');
        await updateSettings({ ...settings, groq_api_key: key });
        setTimeout(next, 1000);
      } else {
        setStatus('error');
      }
    } catch {
      setStatus('error');
    }
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">AI Provider Connect</h2>
        {isLocalMode ? (
          <p className="text-on-surface/50 text-sm">
            You chose {localModelName} — no cloud key needed for chat. Optionally add a Groq key for voice transcription (Whisper).
          </p>
        ) : (
          <p className="text-on-surface/50 text-sm">
            Add a Groq API key to get started. Free at <span className="text-primary">console.groq.com</span>. You can add OpenAI / Anthropic keys in Settings later.
          </p>
        )}
      </div>
      <div className="p-6 rounded-xl border border-on-surface/10 bg-on-surface/5 flex flex-col gap-4">
        <label className="text-xs font-mono text-on-surface/70 uppercase tracking-wider">
          Groq API Key {isLocalMode && <span className="text-on-surface/55">(optional — for transcription only)</span>}
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && key) testKey(); }}
            className="flex-1 bg-surface/50 border border-on-surface/10 rounded px-4 py-2 text-sm focus:border-primary/50 outline-none"
            placeholder="gsk_..."
          />
          <button onClick={testKey} disabled={!key || status === 'testing'} className="px-6 bg-primary text-surface text-sm font-bold rounded hover:bg-on-surface disabled:opacity-50 min-w-[120px] transition-all duration-300 ease-out active:scale-95">
            {status === 'testing' ? <Loader2 size={16} className="animate-spin mx-auto" /> : status === 'success' ? '✓ Connected' : 'Test Key'}
          </button>
        </div>
        {status === 'error' && <p className="text-error text-xs">Invalid key or connection failed.</p>}
      </div>
      <button onClick={next} className="text-sm text-on-surface/55 hover:text-on-surface/60 transition-colors text-center">
        {isLocalMode ? `Skip — using ${localModelName} only →` : 'Skip for now — add in Settings later →'}
      </button>
    </motion.div>
  );
};

const Step4Permissions = ({ next, updateSettings, settings }: any) => {
  const [permissions, setPermissions] = useState<string[]>(['Documents', 'Projects', 'Notes']);
  const toggle = (p: string) => setPermissions(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  const handleNext = () => {
    updateSettings({ ...settings, access_permissions: permissions });
    next();
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Access Permissions</h2>
        <p className="text-on-surface/50 text-sm">Nothing is accessed without your explicit consent.</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {['Documents', 'Downloads', 'Desktop', 'Projects', 'Notes', 'Browser Bookmarks', 'Browser History'].map(p => (
          <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-on-surface/5 bg-on-surface/[0.02] cursor-pointer hover:bg-on-surface/5 transition-all duration-300 ease-out active:scale-95">
            <input type="checkbox" checked={permissions.includes(p)} onChange={() => toggle(p)} className="accent-primary w-4 h-4" />
            <span className="text-sm text-on-surface/80">{p}</span>
          </label>
        ))}
      </div>
      <button onClick={handleNext} className="px-8 py-3 bg-on-surface text-surface font-bold text-sm rounded-lg hover:bg-on-surface/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
        Confirm Access
      </button>
    </motion.div>
  );
};

const Step5Voice = ({ next, updateSettings, settings }: any) => {
  const [interactionMode, setInteractionMode] = useState('VAD (Always Listening)');
  const [adaptiveComm, setAdaptiveComm] = useState(true);
  const handleNext = () => {
    updateSettings({ ...settings, interaction_mode: interactionMode, adaptive_communication: adaptiveComm });
    next();
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Voice & Communication</h2>
        <p className="text-on-surface/50 text-sm">How should Primnox listen and respond?</p>
      </div>
      
      <div className="space-y-4">
        <h3 className="font-bold lowercase italic tracking-wide text-xs font-mono text-primary uppercase">Interaction Mode</h3>
        <div className="flex gap-2">
          {[
            { id: 'VAD (Always Listening)', label: 'VAD', available: true },
            { id: 'Push To Talk',           label: 'Push To Talk', available: false },
            { id: 'Hybrid',                 label: 'Hybrid', available: false },
            { id: 'Disabled',               label: 'Text Only', available: true },
          ].map(m => (
            m.available ? (
              <button key={m.id} onClick={() => setInteractionMode(m.id)}
                className={`flex-1 py-3 px-2 text-[10px] uppercase tracking-wider font-bold rounded border transition-all ${interactionMode === m.id ? 'bg-primary/20 border-primary text-on-surface' : 'bg-transparent border-on-surface/10 text-on-surface/50 hover:bg-on-surface/5'}`}>
                {m.label}
              </button>
            ) : (
              <div key={m.id} className="flex-1 relative flex flex-col items-center justify-center py-3 px-2 rounded border border-on-surface/5 bg-transparent opacity-35 cursor-not-allowed select-none">
                <span className="text-[10px] uppercase tracking-wider font-bold text-on-surface/60">{m.label}</span>
                <span className="text-[7px] font-mono text-on-surface/52 mt-0.5 uppercase tracking-widest">soon</span>
              </div>
            )
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="font-bold lowercase italic tracking-wide text-xs font-mono text-primary uppercase">Communication Learning</h3>
        <p className="text-[10px] text-on-surface/60">Allow Primnox to learn your vocabulary, writing style, slang, and response preferences over time.</p>
        <div className="flex items-center gap-3 p-4 rounded-lg border border-primary/30 bg-primary/5">
          <input type="checkbox" checked={adaptiveComm} onChange={e => setAdaptiveComm(e.target.checked)} className="accent-primary w-4 h-4" />
          <span className="text-sm text-on-surface/80">Enable Adaptive Communication</span>
        </div>
      </div>

      <button onClick={handleNext} className="px-8 py-3 bg-on-surface text-surface font-bold text-sm rounded-lg hover:bg-on-surface/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
        Next Step
      </button>
    </motion.div>
  );
};

const Step6Learning = ({ next, activity, profile, scanEnvironment, setProfile }: any) => {
  const [progress, setProgress] = useState(0);
  const [stream, setStream] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Latest values without making them effect dependencies. `activity` ticks
  // every few seconds and the interval below re-renders every 200ms, so any of
  // these in the dependency array restarts the whole step — which is exactly
  // what used to happen: the scan relaunched forever, progress sat at ~90%, and
  // onboarding could never get past this screen.
  const activityRef = useRef(activity);
  activityRef.current = activity;
  const nextRef = useRef(next);
  nextRef.current = next;
  const scanRef = useRef(scanEnvironment);
  scanRef.current = scanEnvironment;
  const setProfileRef = useRef(setProfile);
  setProfileRef.current = setProfile;

  useEffect(() => {
    let p = 0;
    let isDone = false;
    let advanceTimer: ReturnType<typeof setTimeout>;

    const finish = (line: string) => {
      if (isDone) return;
      isDone = true;
      setProgress(100);
      setStream(prev => [...prev, line].slice(-10));
      advanceTimer = setTimeout(() => nextRef.current(), 1500);
    };

    // Fake progress that slows down as it gets closer to 99%
    const interval = setInterval(() => {
      if (isDone) return;
      p += (99 - p) * 0.1;
      setProgress(Math.min(99, p));

      const acts = activityRef.current || [];
      const randomAct = acts.length > 0 ? acts[Math.floor(Math.random() * acts.length)] : null;
      let logMsg = "Scanning system environment...";
      if (randomAct) {
         const name = randomAct.window || randomAct.app || "System Process";
         const cleanName = name.replace(/ - Word| - Google Chrome| - Opera/g, '');
         logMsg = `Analyzing: ${cleanName.substring(0, 40)}`;
      }
      setStream(prev => [...prev, logMsg].slice(-10));
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, 200);

    // Backstop: this screen has no forward button, so if the scan never settles
    // the user is trapped with no way out but abandoning setup. Always advance.
    const failsafe = setTimeout(() => finish('> Scan timed out — continuing with defaults.'), 12000);

    const scan = scanRef.current;
    if (scan) {
      scan()
        .then((data: any) => {
          if (data && data.projects) {
            setProfileRef.current(data);
            finish('> Scan Complete: Real data acquired!');
          } else {
            finish('> Environment mapped.');
          }
        })
        .catch(() => finish('> Using default profile — configure later in Settings.'));
    } else {
      advanceTimer = setTimeout(() => finish('> Environment mapped.'), 2000);
    }

    return () => {
      clearInterval(interval);
      clearTimeout(failsafe);
      clearTimeout(advanceTimer);
    };
    // Mount-only: every value it needs is read through a ref.
  }, []);

  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.05 }} className="flex flex-col gap-8 h-[60vh]">
      <div className="text-center">
        <h2 className="font-bold lowercase italic tracking-wide text-3xl mb-2 bg-gradient-to-r from-primary to-primary/25 bg-clip-text text-transparent">Learning About You</h2>
        <p className="text-on-surface/50 text-sm">Primnox is mapping your digital environment.</p>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-6 min-h-0">
        <div className="flex flex-col border border-on-surface/10 rounded-xl bg-surface/50 overflow-hidden relative">
          <div className="px-4 py-2 border-b border-on-surface/10 bg-on-surface/5 text-[10px] font-mono text-on-surface/50 uppercase flex justify-between items-center">
            <span>Real-Time Discovery Feed</span>
            <div className="w-2 h-2 rounded-full bg-success/20 animate-pulse" />
          </div>
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[10px]">
            {stream.map((log, i) => (
              <div key={i} className="text-on-surface/70 animate-fade-in flex gap-2">
                <span className="text-primary/50">&gt;</span> {log}
              </div>
            ))}
          </div>
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-on-surface/5">
            <div className="h-full bg-gradient-to-r from-primary to-primary/20 transition-all duration-200" style={{ width: `${progress}%` }} />
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="border border-on-surface/10 rounded-xl bg-on-surface/5 p-4 flex-1">
            <div className="text-[10px] font-mono text-on-surface/50 uppercase mb-4 flex justify-between">
              <span>Understanding Confidence</span>
              <span className="text-primary">{Math.floor(progress * 0.91)}%</span>
            </div>
            
            <div className="space-y-4">
              <div>
                <h4 className="text-xs text-on-surface/60 mb-2">Projects Found</h4>
                <div className="flex flex-wrap gap-2">
                  {profile.projects.map((p: string) => <span key={p} className="px-2 py-1 bg-on-surface/10 rounded text-xs">{p}</span>)}
                </div>
              </div>
              <div>
                <h4 className="text-xs text-on-surface/60 mb-2">Topics & Skills</h4>
                <div className="flex flex-wrap gap-2">
                  {[...profile.topics, ...profile.skills].map((t: string) => <span key={t} className="px-2 py-1 bg-primary/20 text-primary rounded text-xs">{t}</span>)}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
};

const Step7UserModel = ({ next, updateSettings, settings, profile }: any) => {
  useEffect(() => { 
    const timer = setTimeout(() => {
      updateSettings({ ...settings, onboarding_profile: profile });
      next();
    }, 2000);
    return () => clearTimeout(timer);
  }, [next, updateSettings, settings, profile]);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center text-center h-[50vh] gap-6">
      <div className="w-16 h-16 relative">
        <Brain className="absolute inset-0 w-full h-full text-primary animate-pulse" />
        <div className="absolute inset-0 w-full h-full border-4 border-t-primary rounded-full animate-spin" />
      </div>
      <h2 className="font-bold lowercase italic tracking-wide text-2xl">Constructing User Model</h2>
      <div className="flex gap-4 text-xs font-mono text-on-surface/60">
        <span className="animate-pulse">Interests</span>
        <span className="animate-pulse delay-75">Knowledge Areas</span>
        <span className="animate-pulse delay-150">Communication Style</span>
      </div>
    </motion.div>
  );
};

const Step8ProfileReview = ({ next, profile, setProfile }: any) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<any>(null);

  const startEdit = () => setDraft({
    topics: [...profile.topics],
    projects: [...profile.projects],
    communication_style: [...profile.communication_style],
  });

  const updateList = (key: string, idx: number, val: string) =>
    setDraft((d: any) => ({ ...d, [key]: d[key].map((x: string, i: number) => i === idx ? val : x) }));

  const saveEdit = () => {
    setProfile({ ...profile, ...draft });
    setEditing(false);
    setDraft(null);
  };

  return (
    <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="flex flex-col gap-8">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Profile Review</h2>
          <p className="text-on-surface/50 text-sm">Transparency is mandatory. Is this accurate?</p>
        </div>
        {!editing && (
          <button onClick={() => { startEdit(); setEditing(true); }}
            className="px-4 py-1.5 bg-on-surface/5 text-on-surface/50 font-bold text-xs rounded-lg hover:bg-on-surface/10 border border-on-surface/10 transition-all active:scale-95">
            Edit
          </button>
        )}
      </div>

      <div className="border border-on-surface/10 rounded-xl bg-on-surface/5 p-6 space-y-6">
        {!editing ? (
          <>
            <p className="font-mono text-primary text-sm uppercase tracking-wider">I think:</p>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h4 className="text-xs text-on-surface/50 mb-2 uppercase">You enjoy:</h4>
                <ul className="list-disc list-inside text-sm text-on-surface/80 space-y-1">
                  {profile.topics.map((t: string) => <li key={t}>{t}</li>)}
                </ul>
              </div>
              <div>
                <h4 className="text-xs text-on-surface/50 mb-2 uppercase">You frequently work on:</h4>
                <ul className="list-disc list-inside text-sm text-on-surface/80 space-y-1">
                  {profile.projects.map((t: string) => <li key={t}>{t}</li>)}
                </ul>
              </div>
              <div className="col-span-2 border-t border-on-surface/5 pt-4">
                <h4 className="text-xs text-on-surface/50 mb-2 uppercase">You appear to prefer:</h4>
                <ul className="list-disc list-inside text-sm text-on-surface/80 space-y-1">
                  {profile.communication_style.map((t: string) => <li key={t}>{t}</li>)}
                </ul>
              </div>
            </div>
          </>
        ) : (
          <div className="space-y-5">
            {([
              { key: 'topics', label: 'Topics you enjoy' },
              { key: 'projects', label: 'Projects' },
              { key: 'communication_style', label: 'Communication style' },
            ] as const).map(({ key, label }) => (
              <div key={key}>
                <h4 className="text-xs text-on-surface/50 mb-2 uppercase">{label}</h4>
                <div className="space-y-1.5">
                  {(draft[key] as string[]).map((val, i) => (
                    <input key={i} value={val} onChange={e => updateList(key, i, e.target.value)}
                      className="w-full bg-surface/60 border border-on-surface/10 rounded-lg px-3 py-1.5 text-sm text-on-surface/80 outline-none focus:border-primary/40" />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="flex gap-4 justify-end">
        {editing ? (
          <>
            <button onClick={() => { setEditing(false); setDraft(null); }}
              className="px-6 py-2 bg-on-surface/5 text-on-surface/50 font-bold text-sm rounded-lg hover:bg-on-surface/10 border border-on-surface/10 transition-all active:scale-95">
              Cancel
            </button>
            <button onClick={saveEdit}
              className="px-8 py-2 bg-primary text-on-surface font-bold text-sm rounded-lg hover:bg-primary/90 transition-all active:scale-95">
              Save
            </button>
          </>
        ) : (
          <button onClick={next}
            className="px-8 py-2 bg-primary text-on-surface font-bold text-sm rounded-lg hover:bg-primary/90 shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all duration-300 ease-out active:scale-95">
            Looks Good
          </button>
        )}
      </div>
    </motion.div>
  );
};

const Step9Memory = ({ next, updateSettings, settings }: any) => {
  const handleSelect = (id: string) => {
    updateSettings({ ...settings, memory_mode: id });
    next();
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Memory Preferences</h2>
        <p className="text-on-surface/50 text-sm">How should Primnox retain context?</p>
      </div>
      
      <div className="grid grid-cols-1 gap-4">
        {[
          { id: 'smart', title: 'Smart Memory', desc: 'Automatically extract and synthesize relevant context. (Recommended)', recommended: true },
          { id: 'ask', title: 'Ask Before Saving', desc: 'Primnox will prompt you before committing to long-term memory.' },
          { id: 'never', title: 'Never Remember', desc: 'Amnesia mode. Sessions are completely ephemeral.' }
        ].map(opt => (
          <button key={opt.id} onClick={() => handleSelect(opt.id)} className="flex items-center gap-4 text-left p-4 rounded-xl border border-on-surface/10 bg-on-surface/5 hover:bg-on-surface/10 relative overflow-hidden transition-all duration-300 ease-out active:scale-95">
            {opt.recommended && <div className="absolute top-0 right-0 bg-primary text-on-surface text-[8px] font-bold uppercase px-2 py-1 rounded-bl">Recommended</div>}
            <div className={`w-4 h-4 rounded-full border ${opt.recommended ? 'border-primary border-4' : 'border-on-surface/30'}`} />
            <div>
              <h3 className="font-bold lowercase italic tracking-wide text-sm">{opt.title}</h3>
              <p className="text-[10px] text-on-surface/50">{opt.desc}</p>
            </div>
          </button>
        ))}
      </div>
    </motion.div>
  );
};

const Step10Personalization = ({ next, updateSettings, settings }: any) => {
  const defaultOptions = ['Vocabulary Learning', 'Slang Learning', 'Writing Style Matching', 'Research Style Learning', 'Productivity Pattern Learning', 'Response Depth Adaptation'];
  const [options, setOptions] = useState<string[]>(defaultOptions);
  
  const toggle = (p: string) => setOptions(prev => prev.includes(p) ? prev.filter(x => x !== p) : [...prev, p]);
  
  const handleNext = () => {
    updateSettings({ ...settings, personalization_options: options });
    next();
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Personalization Evolution</h2>
        <p className="text-on-surface/50 text-sm">The assistant should gradually adapt to you through actual usage patterns.</p>
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        {defaultOptions.map(p => (
          <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-on-surface/5 bg-on-surface/[0.02] cursor-pointer hover:bg-on-surface/5 transition-all duration-300 ease-out active:scale-95">
            <input type="checkbox" checked={options.includes(p)} onChange={() => toggle(p)} className="accent-primary w-4 h-4" />
            <span className="text-sm text-on-surface/80">{p}</span>
          </label>
        ))}
      </div>
      
      <button onClick={handleNext} className="px-8 py-3 bg-on-surface text-surface font-bold text-sm rounded-lg hover:bg-on-surface/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
        Confirm Evolution Options
      </button>
    </motion.div>
  );
};

const Step11Workspace = ({ next, updateSettings, settings, profile }: any) => {
  // Seed from scanned projects; fall back to generic defaults if scan didn't run
  const seedWorkspaces = (): string[] => {
    const projects: string[] = profile?.projects?.filter((p: string) => !p.startsWith('<')) ?? [];
    if (projects.length >= 2) return projects.slice(0, 3);
    return ['Personal Workspace', 'Development Workspace', 'Research Workspace'];
  };

  const [workspaces, setWorkspaces] = useState<string[]>(seedWorkspaces);

  const handleChange = (index: number, val: string) => {
    const newWs = [...workspaces];
    newWs[index] = val;
    setWorkspaces(newWs);
  };

  const addWorkspace = () => setWorkspaces(w => [...w, '']);
  const removeWorkspace = (i: number) => setWorkspaces(w => w.filter((_, idx) => idx !== i));

  const handleNext = () => {
    updateSettings({ ...settings, workspaces: workspaces.filter(w => w.trim()) });
    next();
  };

  const seededFromProfile = (profile?.projects?.filter((p: string) => !p.startsWith('<')) ?? []).length >= 2;

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Workspace Creation</h2>
        <p className="text-on-surface/50 text-sm">
          {seededFromProfile ? 'Seeded from your scanned projects — rename or add more.' : 'Name your workspaces. You can change these any time.'}
        </p>
      </div>

      <div className="space-y-3">
        {workspaces.map((ws, i) => (
          <div key={i} className="flex items-center gap-3 p-4 rounded-xl border border-on-surface/10 bg-on-surface/5 group">
            <LayoutDashboard size={18} className="text-on-surface/55 shrink-0" />
            <input type="text" value={ws} onChange={e => handleChange(i, e.target.value)}
              className="bg-transparent border-none outline-none text-sm text-on-surface/90 flex-1 placeholder-on-surface/20"
              placeholder="Workspace name…" />
            {workspaces.length > 1 && (
              <button onClick={() => removeWorkspace(i)}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-on-surface/48 hover:text-error text-xs font-mono px-1">
                ✕
              </button>
            )}
          </div>
        ))}
        {workspaces.length < 6 && (
          <button onClick={addWorkspace}
            className="w-full py-3 rounded-xl border border-dashed border-on-surface/10 text-on-surface/48 hover:text-on-surface/50 hover:border-on-surface/20 text-xs font-mono uppercase tracking-widest transition-all">
            + Add Workspace
          </button>
        )}
      </div>

      <button onClick={handleNext} className="px-8 py-3 bg-primary text-on-surface font-bold text-sm rounded-lg hover:bg-primary/90 self-end shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all duration-300 ease-out active:scale-95">
        Create Workspaces
      </button>
    </motion.div>
  );
};

const Step12AssistantGen = ({ next }: any) => {
  useEffect(() => { 
    const timer = setTimeout(next, 3000); 
    return () => clearTimeout(timer);
  }, [next]);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center text-center h-[50vh] gap-6">
      <div className="w-24 h-24 relative flex items-center justify-center border-2 border-primary/30 rounded-full">
        <Sparkles className="text-primary animate-pulse" size={32} />
        <div className="absolute inset-0 border-t-2 border-primary rounded-full animate-spin" style={{ animationDuration: '3s' }} />
      </div>
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl">Generating Assistant</h2>
        <p className="text-on-surface/60 text-sm mt-2">Compiling Knowledge Graph & Memory System...</p>
      </div>
    </motion.div>
  );
};

const Step13Completion = ({ onComplete, profile }: any) => {
  const name = profile?.name && !profile.name.startsWith('<') ? profile.name : null;
  const role = profile?.role && profile.role !== 'Developer' ? profile.role : null;
  return (
  <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col gap-8 text-center max-w-xl mx-auto py-10">
    <div className="w-16 h-16 rounded-full bg-success/20 text-success flex items-center justify-center mx-auto mb-4 border border-success/50 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
      <Check size={32} />
    </div>

    <div>
      <h2 className="font-bold lowercase italic tracking-wide text-4xl mb-2">
        {name ? `welcome, ${name}.` : 'Welcome.'}
      </h2>
      {role && <p className="text-primary/70 font-mono text-xs uppercase tracking-widest mb-3">{role}</p>}
      <p className="text-on-surface/60">Primnox has initialized your personalized environment.</p>
    </div>
    
    <div className="bg-on-surface/5 border border-on-surface/10 rounded-xl p-6 text-left space-y-4">
      <p className="text-xs font-mono text-on-surface/60 uppercase tracking-wider">Background Learning System Active</p>
      <p className="text-sm text-on-surface/70 leading-relaxed">
        Primnox will continue observing your notes, research, and conversations. Over time, it will naturally improve its knowledge graph, memory system, and communication matching without imitating you excessively.
      </p>
    </div>

    <div className="grid grid-cols-2 gap-4 mt-4">
      <button onClick={onComplete} className="p-4 rounded-xl border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary flex flex-col items-center gap-2 group transition-all duration-300 ease-out active:scale-95">
        <MessageSquare size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Open Chat</span>
      </button>
      <button onClick={onComplete} className="p-4 rounded-xl border border-on-surface/10 bg-on-surface/5 hover:bg-on-surface/10 text-on-surface flex flex-col items-center gap-2 group transition-all duration-300 ease-out active:scale-95">
        <Compass size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Explore Workspace</span>
      </button>
    </div>
  </motion.div>
  );
};
