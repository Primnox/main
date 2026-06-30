import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Sparkles, Check, Brain, Shield, Eye, ShieldAlert,
  Loader2, Terminal, Compass, LayoutDashboard, MessageSquare, Cpu
} from 'lucide-react';
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
  
  const nextStep = () => setStep(prev => Math.min(prev + 1, totalSteps));
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
          <span className="font-bold text-white tracking-tighter uppercase">Primnox</span>
          <span className="text-[8px] font-mono text-primary uppercase tracking-[0.2em]">Initialization</span>
        </div>
      </div>
      
      <div className="flex items-center gap-6">
        <div className="flex flex-col items-end text-right">
          <span className="text-xs text-white/50 font-mono">Step {step} of {totalSteps}</span>
          <span className="text-[10px] text-primary/70 font-mono">~{estimatedTime} Minutes Remaining</span>
        </div>
        <button onClick={skipSetup} className="text-xs text-white/40 hover:text-white transition-all duration-300 ease-out active:scale-95">
          Skip For Now
        </button>
      </div>
    </div>
  );

  return (
    <div className="h-full w-full text-white overflow-hidden relative flex flex-col items-center justify-center font-sans">
      {/* Background Ambience */}
      <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,_var(--tw-gradient-stops))] from-primary/5 via-black to-black opacity-50 z-0" />
      
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
    <h1 className="font-bold lowercase italic tracking-wide text-4xl text-white">Welcome to Primnox</h1>
    <h2 className="font-bold lowercase italic tracking-wide text-xl text-primary font-mono uppercase">Your AI Operating Environment</h2>
    <p className="text-white/50 max-w-lg mx-auto text-sm leading-relaxed mb-8">
      An assistant that learns your projects, workflows, communication style, and preferences over time. Primnox is not being configured. Primnox is learning.
    </p>
    <div className="flex items-center justify-center gap-4">
      <button onClick={next} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 shadow-[0_0_20px_rgba(255,255,255,0.2)] transition-all duration-300 ease-out active:scale-95">
        Begin Setup
      </button>
      <button onClick={skip} className="px-8 py-3 bg-white/5 text-white/70 font-medium text-sm rounded-lg hover:bg-white/10 border border-white/10 transition-all duration-300 ease-out active:scale-95">
        Skip Setup
      </button>
    </div>
  </motion.div>
);

// ── Mini data-flow diagrams for Step 2 ──────────────────────────────────────
const FN = ({ label, sub, c }: { label: string; sub?: string; c: string }) => (
  <div className={`flex flex-col items-center px-2 py-1 rounded-md border text-center shrink-0 ${c}`}>
    <span className="font-bold text-[9px] leading-tight whitespace-nowrap">{label}</span>
    {sub && <span className="text-[7px] opacity-50 leading-tight mt-0.5 whitespace-nowrap">{sub}</span>}
  </div>
);
const FA = ({ c }: { c: string }) => <span className={`text-sm leading-none ${c}`}>→</span>;

const FlowLocal = () => (
  <div className="flex flex-col items-center gap-1.5 py-2">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FN label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <FA c="text-emerald-700" />
      <FN label="Primnox" sub="brain.py" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
      <FA c="text-emerald-700" />
      <FN label="Local Model" sub="on-device" c="border-emerald-600 bg-emerald-950 text-emerald-300" />
      <FA c="text-emerald-700" />
      <FN label="Response" sub="raw" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
    </div>
    <span className="text-[8px] text-emerald-600 font-mono tracking-widest uppercase">nothing leaves your machine</span>
  </div>
);

const FlowCloud = () => (
  <div className="flex flex-col items-center gap-1.5 py-2">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <FN label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <FA c="text-slate-600" />
      <FN label="Privacy Mirror" sub="DeBERTa NER" c="border-pink-800 bg-pink-950 text-pink-300" />
      <FA c="text-blue-700" />
      <FN label="Cloud API" sub="Groq / OpenAI" c="border-blue-800 bg-blue-950 text-blue-300" />
      <FA c="text-pink-700" />
      <FN label="Rehydrate" sub="names restored" c="border-pink-800 bg-pink-950 text-pink-300" />
      <FA c="text-slate-600" />
      <FN label="You" sub="real names" c="border-slate-700 bg-slate-900 text-slate-300" />
    </div>
    <span className="text-[8px] text-pink-700 font-mono tracking-widest uppercase">cloud only ever sees §NAME_1§ — not your real name</span>
  </div>
);

// ─────────────────────────────────────────────────────────────────────────────

const Step2Privacy = ({ next, updateSettings, settings }: any) => {
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean, models: string[] } | null>(null);
  const [selected, setSelected] = useState<'cloud' | 'ollama' | 'llamacpp' | null>(null);
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState('llama3.2');
  const [llamaUrl, setLlamaUrl] = useState('http://localhost:8080');
  const [llamaModel, setLlamaModel] = useState('');

  useEffect(() => {
    fetch('http://localhost:4009/api/ollama/status')
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
  const confirmCloud = () => next();

  const cardBase = 'flex flex-col items-start text-left p-5 rounded-xl border transition-all relative cursor-pointer';

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-6">
      <div>
        <h2 className="font-bold lowercase italic tracking-wide text-2xl mb-2">Privacy Architecture</h2>
        <p className="text-white/50 text-sm">Choose how Primnox thinks. You can change this any time in Settings.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Cloud */}
        <button
          onClick={() => setSelected(s => s === 'cloud' ? null : 'cloud')}
          className={`${cardBase} ${selected === 'cloud' ? 'border-primary/60 bg-primary/10' : 'border-primary/30 bg-primary/5 hover:bg-primary/10 hover:scale-[1.02]'}`}
        >
          <Eye size={22} className="text-primary mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Cloud Assisted</h3>
          <p className="text-[10px] text-white/50 leading-relaxed">Groq / OpenAI / Anthropic. Maximum speed.</p>
        </button>

        {/* Ollama */}
        <button
          onClick={() => setSelected(s => s === 'ollama' ? null : 'ollama')}
          className={`${cardBase} ${selected === 'ollama' ? 'border-emerald-500/60 bg-emerald-500/10' : 'border-emerald-500/20 bg-emerald-500/5 hover:bg-emerald-500/10 hover:scale-[1.02]'}`}
        >
          <div className={`absolute top-3 right-3 flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[8px] font-mono ${
            ollamaStatus === null ? 'bg-white/10 text-white/30' :
            ollamaStatus.running ? 'bg-emerald-500/20 text-emerald-400' : 'bg-white/5 text-white/20'
          }`}>
            <div className={`w-1.5 h-1.5 rounded-full ${ollamaStatus === null ? 'bg-white/20 animate-pulse' : ollamaStatus.running ? 'bg-emerald-400 animate-pulse' : 'bg-white/20'}`} />
            {ollamaStatus === null ? 'checking…' : ollamaStatus.running ? 'detected' : 'not running'}
          </div>
          <ShieldAlert size={22} className="text-emerald-400 mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Ollama — Local</h3>
          <p className="text-[10px] text-white/50 leading-relaxed">On-device via Ollama. No chat leaves your machine.</p>
        </button>

        {/* llama.cpp */}
        <button
          onClick={() => setSelected(s => s === 'llamacpp' ? null : 'llamacpp')}
          className={`${cardBase} ${selected === 'llamacpp' ? 'border-violet-500/60 bg-violet-500/10' : 'border-violet-500/20 bg-violet-500/5 hover:bg-violet-500/10 hover:scale-[1.02]'}`}
        >
          <Cpu size={22} className="text-violet-400 mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">llama.cpp — Local GGUF</h3>
          <p className="text-[10px] text-white/50 leading-relaxed">Run any GGUF model via llama-server. Fully offline.</p>
        </button>

        {/* Local Only — coming soon */}
        <div className={`${cardBase} border-white/5 bg-white/5 opacity-40 cursor-not-allowed`}>
          <span className="absolute top-3 right-3 text-[8px] font-mono text-white/30 bg-white/5 px-2 py-0.5 rounded-full uppercase tracking-widest">soon</span>
          <Shield size={22} className="text-white/30 mb-3" />
          <h3 className="font-bold lowercase italic tracking-wide text-sm mb-1">Local Only</h3>
          <p className="text-[10px] text-white/40 leading-relaxed">100% on-device, no server needed. Coming soon.</p>
        </div>
      </div>

      {/* Ollama config panel */}
      <AnimatePresence>
        {selected === 'ollama' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-emerald-500/20 bg-emerald-500/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-emerald-400/70 uppercase tracking-widest font-bold">Ollama Config</p>
              {!ollamaStatus?.running && (
                <p className="text-[10px] text-amber-400/80 font-mono">
                  Run <span className="bg-white/5 px-1 rounded text-amber-300">ollama serve</span> then{' '}
                  <span className="bg-white/5 px-1 rounded text-amber-300">ollama pull llama3.2</span> to get started.
                </p>
              )}
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Server URL</label>
                  <input value={ollamaUrl} onChange={e => setOllamaUrl(e.target.value)}
                    className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80"
                    placeholder="http://localhost:11434" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Model</label>
                  {ollamaStatus?.running && ollamaStatus.models.length > 0 ? (
                    <select value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                      className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80 appearance-none">
                      {ollamaStatus.models.map(m => <option key={m} value={m}>{m}</option>)}
                    </select>
                  ) : (
                    <input value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                      className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80"
                      placeholder="llama3.2" />
                  )}
                </div>
              </div>
              <div className="border-t border-emerald-500/10 pt-2">
                <FlowLocal />
              </div>
              <button onClick={confirmOllama}
                className="w-full py-2.5 bg-emerald-500/20 hover:bg-emerald-500/30 border border-emerald-500/30 text-emerald-400 rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95">
                Use Ollama → Continue
              </button>
            </div>
          </motion.div>
        )}

        {/* llama.cpp config panel */}
        {selected === 'llamacpp' && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <div className="border border-violet-500/20 bg-violet-500/5 rounded-xl p-5 space-y-4">
              <p className="font-mono text-[10px] text-violet-400/70 uppercase tracking-widest font-bold">llama.cpp Config</p>
              <p className="text-[10px] text-amber-400/80 font-mono">
                Start with: <span className="bg-white/5 px-1 rounded text-amber-300">./llama-server -m model.gguf --port 8080</span>
              </p>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Server URL</label>
                  <input value={llamaUrl} onChange={e => setLlamaUrl(e.target.value)}
                    className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-violet-500/40 text-white/80"
                    placeholder="http://localhost:8080" />
                </div>
                <div className="space-y-1.5">
                  <label className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Model Name <span className="text-white/20">(optional)</span></label>
                  <input value={llamaModel} onChange={e => setLlamaModel(e.target.value)}
                    className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-violet-500/40 text-white/80"
                    placeholder="leave blank for default" />
                </div>
              </div>
              <div className="border-t border-violet-500/10 pt-2">
                <FlowLocal />
              </div>
              <button onClick={confirmLlamaCpp}
                className="w-full py-2.5 bg-violet-500/20 hover:bg-violet-500/30 border border-violet-500/30 text-violet-400 rounded-lg font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95">
                Use llama.cpp → Continue
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
              <p className="text-[10px] text-white/30 font-mono">
                Privacy Mirror is <span className="text-emerald-400">on by default</span> — your name, email, and phone are pseudonymised before leaving your machine. You can toggle it in Settings → Security.
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
  const isLocalMode = settings?.active_model === 'Ollama_Local' || settings?.active_model === 'LlamaCpp_Local';
  const localModelName = settings?.active_model === 'LlamaCpp_Local' ? 'llama.cpp' : 'Ollama';

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
          <p className="text-white/50 text-sm">
            You chose {localModelName} — no cloud key needed for chat. Optionally add a Groq key for voice transcription (Whisper).
          </p>
        ) : (
          <p className="text-white/50 text-sm">
            Add a Groq API key to get started. Free at <span className="text-primary">console.groq.com</span>. You can add OpenAI / Anthropic keys in Settings later.
          </p>
        )}
      </div>
      <div className="p-6 rounded-xl border border-white/10 bg-white/5 flex flex-col gap-4">
        <label className="text-xs font-mono text-white/70 uppercase tracking-wider">
          Groq API Key {isLocalMode && <span className="text-white/30">(optional — for transcription only)</span>}
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={key}
            onChange={e => setKey(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && key) testKey(); }}
            className="flex-1 bg-black/50 border border-white/10 rounded px-4 py-2 text-sm focus:border-primary/50 outline-none"
            placeholder="gsk_..."
          />
          <button onClick={testKey} disabled={!key || status === 'testing'} className="px-6 bg-primary text-black text-sm font-bold rounded hover:bg-white disabled:opacity-50 min-w-[120px] transition-all duration-300 ease-out active:scale-95">
            {status === 'testing' ? <Loader2 size={16} className="animate-spin mx-auto" /> : status === 'success' ? '✓ Connected' : 'Test Key'}
          </button>
        </div>
        {status === 'error' && <p className="text-red-400 text-xs">Invalid key or connection failed.</p>}
      </div>
      <button onClick={next} className="text-sm text-white/30 hover:text-white/60 transition-colors text-center">
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
        <p className="text-white/50 text-sm">Nothing is accessed without your explicit consent.</p>
      </div>
      <div className="grid grid-cols-2 gap-4">
        {['Documents', 'Downloads', 'Desktop', 'Projects', 'Notes', 'Browser Bookmarks', 'Browser History'].map(p => (
          <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-white/5 bg-white/[0.02] cursor-pointer hover:bg-white/5 transition-all duration-300 ease-out active:scale-95">
            <input type="checkbox" checked={permissions.includes(p)} onChange={() => toggle(p)} className="accent-primary w-4 h-4" />
            <span className="text-sm text-white/80">{p}</span>
          </label>
        ))}
      </div>
      <button onClick={handleNext} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
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
        <p className="text-white/50 text-sm">How should Primnox listen and respond?</p>
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
                className={`flex-1 py-3 px-2 text-[10px] uppercase tracking-wider font-bold rounded border transition-all ${interactionMode === m.id ? 'bg-primary/20 border-primary text-white' : 'bg-transparent border-white/10 text-white/50 hover:bg-white/5'}`}>
                {m.label}
              </button>
            ) : (
              <div key={m.id} className="flex-1 relative flex flex-col items-center justify-center py-3 px-2 rounded border border-white/5 bg-transparent opacity-35 cursor-not-allowed select-none">
                <span className="text-[10px] uppercase tracking-wider font-bold text-white/40">{m.label}</span>
                <span className="text-[7px] font-mono text-white/25 mt-0.5 uppercase tracking-widest">soon</span>
              </div>
            )
          ))}
        </div>
      </div>

      <div className="space-y-4">
        <h3 className="font-bold lowercase italic tracking-wide text-xs font-mono text-primary uppercase">Communication Learning</h3>
        <p className="text-[10px] text-white/40">Allow Primnox to learn your vocabulary, writing style, slang, and response preferences over time.</p>
        <div className="flex items-center gap-3 p-4 rounded-lg border border-primary/30 bg-primary/5">
          <input type="checkbox" checked={adaptiveComm} onChange={e => setAdaptiveComm(e.target.checked)} className="accent-primary w-4 h-4" />
          <span className="text-sm text-white/80">Enable Adaptive Communication</span>
        </div>
      </div>

      <button onClick={handleNext} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
        Next Step
      </button>
    </motion.div>
  );
};

const Step6Learning = ({ next, activity, profile, scanEnvironment, setProfile }: any) => {
  const [progress, setProgress] = useState(0);
  const [stream, setStream] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let p = 0;
    let isDone = false;
    
    // Fake progress that slows down as it gets closer to 99%
    const interval = setInterval(() => {
      if (isDone) return;
      p += (99 - p) * 0.1;
      setProgress(Math.min(99, p));
      
      const randomAct = activity.length > 0 ? activity[Math.floor(Math.random() * activity.length)] : null;
      let logMsg = "Scanning system environment...";
      if (randomAct) {
         const name = randomAct.window || randomAct.app || "System Process";
         const cleanName = name.replace(/ - Word| - Google Chrome| - Opera/g, '');
         logMsg = `Analyzing: ${cleanName.substring(0, 40)}`;
      }
      setStream(prev => [...prev, logMsg].slice(-10));
      if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }, 200);

    // Run the actual backend scan
    if (scanEnvironment) {
      scanEnvironment()
        .then((data: any) => {
          isDone = true;
          setProgress(100);
          if (data && data.projects) {
            setProfile(data);
            setStream(prev => [...prev, '> Scan Complete: Real data acquired!'].slice(-10));
          } else {
            setStream(prev => [...prev, '> Environment mapped.'].slice(-10));
          }
          setTimeout(next, 1500);
        })
        .catch(() => {
          // Backend unreachable — just move on with defaults
          isDone = true;
          setProgress(100);
          setStream(prev => [...prev, '> Using default profile — configure later in Settings.'].slice(-10));
          setTimeout(next, 1500);
        });
    } else {
      // No scanner available — advance after a short delay
      setTimeout(() => { isDone = true; setProgress(100); next(); }, 2000);
    }

    return () => clearInterval(interval);
  }, [activity, next, scanEnvironment, setProfile]);

  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.05 }} className="flex flex-col gap-8 h-[60vh]">
      <div className="text-center">
        <h2 className="font-bold lowercase italic tracking-wide text-3xl mb-2 bg-gradient-to-r from-primary to-purple-400 bg-clip-text text-transparent">Learning About You</h2>
        <p className="text-white/50 text-sm">Primnox is mapping your digital environment.</p>
      </div>

      <div className="flex-1 grid grid-cols-2 gap-6 min-h-0">
        <div className="flex flex-col border border-white/10 rounded-xl bg-black/50 overflow-hidden relative">
          <div className="px-4 py-2 border-b border-white/10 bg-white/5 text-[10px] font-mono text-white/50 uppercase flex justify-between items-center">
            <span>Real-Time Discovery Feed</span>
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          </div>
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-[10px]">
            {stream.map((log, i) => (
              <div key={i} className="text-white/70 animate-fade-in flex gap-2">
                <span className="text-primary/50">&gt;</span> {log}
              </div>
            ))}
          </div>
          <div className="absolute bottom-0 left-0 right-0 h-1 bg-white/5">
            <div className="h-full bg-gradient-to-r from-primary to-purple-500 transition-all duration-200" style={{ width: `${progress}%` }} />
          </div>
        </div>

        <div className="flex flex-col gap-4">
          <div className="border border-white/10 rounded-xl bg-white/5 p-4 flex-1">
            <div className="text-[10px] font-mono text-white/50 uppercase mb-4 flex justify-between">
              <span>Understanding Confidence</span>
              <span className="text-primary">{Math.floor(progress * 0.91)}%</span>
            </div>
            
            <div className="space-y-4">
              <div>
                <h4 className="text-xs text-white/40 mb-2">Projects Found</h4>
                <div className="flex flex-wrap gap-2">
                  {profile.projects.map((p: string) => <span key={p} className="px-2 py-1 bg-white/10 rounded text-xs">{p}</span>)}
                </div>
              </div>
              <div>
                <h4 className="text-xs text-white/40 mb-2">Topics & Skills</h4>
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
      <div className="flex gap-4 text-xs font-mono text-white/40">
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
          <p className="text-white/50 text-sm">Transparency is mandatory. Is this accurate?</p>
        </div>
        {!editing && (
          <button onClick={() => { startEdit(); setEditing(true); }}
            className="px-4 py-1.5 bg-white/5 text-white/50 font-bold text-xs rounded-lg hover:bg-white/10 border border-white/10 transition-all active:scale-95">
            Edit
          </button>
        )}
      </div>

      <div className="border border-white/10 rounded-xl bg-white/5 p-6 space-y-6">
        {!editing ? (
          <>
            <p className="font-mono text-primary text-sm uppercase tracking-wider">I think:</p>
            <div className="grid grid-cols-2 gap-6">
              <div>
                <h4 className="text-xs text-white/50 mb-2 uppercase">You enjoy:</h4>
                <ul className="list-disc list-inside text-sm text-white/80 space-y-1">
                  {profile.topics.map((t: string) => <li key={t}>{t}</li>)}
                </ul>
              </div>
              <div>
                <h4 className="text-xs text-white/50 mb-2 uppercase">You frequently work on:</h4>
                <ul className="list-disc list-inside text-sm text-white/80 space-y-1">
                  {profile.projects.map((t: string) => <li key={t}>{t}</li>)}
                </ul>
              </div>
              <div className="col-span-2 border-t border-white/5 pt-4">
                <h4 className="text-xs text-white/50 mb-2 uppercase">You appear to prefer:</h4>
                <ul className="list-disc list-inside text-sm text-white/80 space-y-1">
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
                <h4 className="text-xs text-white/50 mb-2 uppercase">{label}</h4>
                <div className="space-y-1.5">
                  {(draft[key] as string[]).map((val, i) => (
                    <input key={i} value={val} onChange={e => updateList(key, i, e.target.value)}
                      className="w-full bg-black/60 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white/80 outline-none focus:border-primary/40" />
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
              className="px-6 py-2 bg-white/5 text-white/50 font-bold text-sm rounded-lg hover:bg-white/10 border border-white/10 transition-all active:scale-95">
              Cancel
            </button>
            <button onClick={saveEdit}
              className="px-8 py-2 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary/90 transition-all active:scale-95">
              Save
            </button>
          </>
        ) : (
          <button onClick={next}
            className="px-8 py-2 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary/90 shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all duration-300 ease-out active:scale-95">
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
        <p className="text-white/50 text-sm">How should Primnox retain context?</p>
      </div>
      
      <div className="grid grid-cols-1 gap-4">
        {[
          { id: 'smart', title: 'Smart Memory', desc: 'Automatically extract and synthesize relevant context. (Recommended)', recommended: true },
          { id: 'ask', title: 'Ask Before Saving', desc: 'Primnox will prompt you before committing to long-term memory.' },
          { id: 'never', title: 'Never Remember', desc: 'Amnesia mode. Sessions are completely ephemeral.' }
        ].map(opt => (
          <button key={opt.id} onClick={() => handleSelect(opt.id)} className="flex items-center gap-4 text-left p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 relative overflow-hidden transition-all duration-300 ease-out active:scale-95">
            {opt.recommended && <div className="absolute top-0 right-0 bg-primary text-white text-[8px] font-bold uppercase px-2 py-1 rounded-bl">Recommended</div>}
            <div className={`w-4 h-4 rounded-full border ${opt.recommended ? 'border-primary border-4' : 'border-white/30'}`} />
            <div>
              <h3 className="font-bold lowercase italic tracking-wide text-sm">{opt.title}</h3>
              <p className="text-[10px] text-white/50">{opt.desc}</p>
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
        <p className="text-white/50 text-sm">The assistant should gradually adapt to you through actual usage patterns.</p>
      </div>
      
      <div className="grid grid-cols-2 gap-4">
        {defaultOptions.map(p => (
          <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-white/5 bg-white/[0.02] cursor-pointer hover:bg-white/5 transition-all duration-300 ease-out active:scale-95">
            <input type="checkbox" checked={options.includes(p)} onChange={() => toggle(p)} className="accent-primary w-4 h-4" />
            <span className="text-sm text-white/80">{p}</span>
          </label>
        ))}
      </div>
      
      <button onClick={handleNext} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 self-end mt-4 transition-all duration-300 ease-out active:scale-95">
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
        <p className="text-white/50 text-sm">
          {seededFromProfile ? 'Seeded from your scanned projects — rename or add more.' : 'Name your workspaces. You can change these any time.'}
        </p>
      </div>

      <div className="space-y-3">
        {workspaces.map((ws, i) => (
          <div key={i} className="flex items-center gap-3 p-4 rounded-xl border border-white/10 bg-white/5 group">
            <LayoutDashboard size={18} className="text-white/30 shrink-0" />
            <input type="text" value={ws} onChange={e => handleChange(i, e.target.value)}
              className="bg-transparent border-none outline-none text-sm text-white/90 flex-1 placeholder-white/20"
              placeholder="Workspace name…" />
            {workspaces.length > 1 && (
              <button onClick={() => removeWorkspace(i)}
                className="opacity-0 group-hover:opacity-100 transition-opacity text-white/20 hover:text-red-400 text-xs font-mono px-1">
                ✕
              </button>
            )}
          </div>
        ))}
        {workspaces.length < 6 && (
          <button onClick={addWorkspace}
            className="w-full py-3 rounded-xl border border-dashed border-white/10 text-white/20 hover:text-white/50 hover:border-white/20 text-xs font-mono uppercase tracking-widest transition-all">
            + Add Workspace
          </button>
        )}
      </div>

      <button onClick={handleNext} className="px-8 py-3 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary/90 self-end shadow-[0_0_20px_rgba(79,70,229,0.3)] transition-all duration-300 ease-out active:scale-95">
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
        <p className="text-white/40 text-sm mt-2">Compiling Knowledge Graph & Memory System...</p>
      </div>
    </motion.div>
  );
};

const Step13Completion = ({ onComplete, profile }: any) => {
  const name = profile?.name && !profile.name.startsWith('<') ? profile.name : null;
  const role = profile?.role && profile.role !== 'Developer' ? profile.role : null;
  return (
  <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col gap-8 text-center max-w-xl mx-auto py-10">
    <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto mb-4 border border-emerald-500/50 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
      <Check size={32} />
    </div>

    <div>
      <h2 className="font-bold lowercase italic tracking-wide text-4xl mb-2">
        {name ? `welcome, ${name}.` : 'Welcome.'}
      </h2>
      {role && <p className="text-primary/70 font-mono text-xs uppercase tracking-widest mb-3">{role}</p>}
      <p className="text-white/60">Primnox has initialized your personalized environment.</p>
    </div>
    
    <div className="bg-white/5 border border-white/10 rounded-xl p-6 text-left space-y-4">
      <p className="text-xs font-mono text-white/40 uppercase tracking-wider">Background Learning System Active</p>
      <p className="text-sm text-white/70 leading-relaxed">
        Primnox will continue observing your notes, research, and conversations. Over time, it will naturally improve its knowledge graph, memory system, and communication matching without imitating you excessively.
      </p>
    </div>

    <div className="grid grid-cols-2 gap-4 mt-4">
      <button onClick={onComplete} className="p-4 rounded-xl border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary flex flex-col items-center gap-2 group transition-all duration-300 ease-out active:scale-95">
        <MessageSquare size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Open Chat</span>
      </button>
      <button onClick={onComplete} className="p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white flex flex-col items-center gap-2 group transition-all duration-300 ease-out active:scale-95">
        <Compass size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Explore Workspace</span>
      </button>
    </div>
  </motion.div>
  );
};
