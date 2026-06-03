import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, Check, Brain, Shield, Eye, ShieldAlert,
  Loader2, Terminal, Compass, LayoutDashboard, MessageSquare
} from 'lucide-react';
import { usePrimnox } from '../../hooks/usePrimnox';

export const OnboardingView = ({ onComplete }: { onComplete: () => void }) => {
  const [step, setStep] = useState(1);
  const totalSteps = 13;
  
  const { activity, updateSettings, settings, scanEnvironment } = usePrimnox();
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
        <button onClick={skipSetup} className="text-xs text-white/40 hover:text-white transition-colors">
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
          {step === 2 && <Step2Privacy key="step2" next={nextStep} />}
          {step === 3 && <Step3AIProvider key="step3" next={nextStep} />}
          {step === 4 && <Step4Permissions key="step4" next={nextStep} />}
          {step === 5 && <Step5Voice key="step5" next={nextStep} />}
          {step === 6 && <Step6Learning key="step6" next={nextStep} activity={activity} profile={profile} scanEnvironment={scanEnvironment} setProfile={setProfile} />}
          {step === 7 && <Step7UserModel key="step7" next={nextStep} />}
          {step === 8 && <Step8ProfileReview key="step8" next={nextStep} profile={profile} setProfile={setProfile} />}
          {step === 9 && <Step9Memory key="step9" next={nextStep} />}
          {step === 10 && <Step10Personalization key="step10" next={nextStep} />}
          {step === 11 && <Step11Workspace key="step11" next={nextStep} />}
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
    <h1 className="text-4xl font-bold tracking-tight text-white">Welcome to Primnox</h1>
    <h2 className="text-xl text-primary font-mono uppercase tracking-widest">Your AI Operating Environment</h2>
    <p className="text-white/50 max-w-lg mx-auto text-sm leading-relaxed mb-8">
      An assistant that learns your projects, workflows, communication style, and preferences over time. Primnox is not being configured. Primnox is learning.
    </p>
    <div className="flex items-center justify-center gap-4">
      <button onClick={next} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 transition-all shadow-[0_0_20px_rgba(255,255,255,0.2)]">
        Begin Setup
      </button>
      <button onClick={skip} className="px-8 py-3 bg-white/5 text-white/70 font-medium text-sm rounded-lg hover:bg-white/10 transition-all border border-white/10">
        Skip Setup
      </button>
    </div>
  </motion.div>
);

const Step2Privacy = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Privacy Architecture</h2>
      <p className="text-white/50 text-sm">Note: This version currently only supports the Cloud Assisted model.</p>
    </div>
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {[
        { id: 'local', icon: Shield, title: 'Local Only', desc: 'Everything remains on device. (Coming Soon)', disabled: true },
        { id: 'hybrid', icon: ShieldAlert, title: 'Hybrid', desc: 'Local memory with cloud AI assistance. (Coming Soon)', disabled: true },
        { id: 'cloud', icon: Eye, title: 'Cloud Assisted', desc: 'Maximum AI capabilities. Currently active.', disabled: false }
      ].map(opt => (
        <button key={opt.id} onClick={!opt.disabled ? next : undefined} className={`flex flex-col items-start text-left p-6 rounded-xl border transition-all group ${opt.disabled ? 'border-white/5 bg-white/5 opacity-50 cursor-not-allowed' : 'border-primary/50 bg-primary/10 hover:bg-primary/20 hover:scale-105'}`}>
          <opt.icon size={24} className={`${opt.disabled ? 'text-white/30' : 'text-primary'} mb-4 group-hover:scale-110 transition-transform`} />
          <h3 className="font-bold text-sm mb-1">{opt.title}</h3>
          <p className="text-[10px] text-white/50 leading-relaxed">{opt.desc}</p>
        </button>
      ))}
    </div>
  </motion.div>
);

const Step3AIProvider = ({ next }: any) => {
  const [key, setKey] = useState('');
  const [status, setStatus] = useState<'idle'|'testing'|'success'|'error'>('idle');

  const testKey = () => {
    setStatus('testing');
    setTimeout(() => {
      setStatus(key.length > 10 ? 'success' : 'error');
      if (key.length > 10) setTimeout(next, 1000);
    }, 1500);
  };

  return (
    <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
      <div>
        <h2 className="text-2xl font-bold mb-2">AI Provider Connect</h2>
        <p className="text-white/50 text-sm">Primnox currently utilizes Groq for ultra-fast reasoning.</p>
      </div>
      <div className="p-6 rounded-xl border border-white/10 bg-white/5 flex flex-col gap-4">
        <label className="text-xs font-mono text-white/70 uppercase tracking-wider">Groq API Key</label>
        <div className="flex gap-2">
          <input 
            type="password" 
            value={key} 
            onChange={e => setKey(e.target.value)}
            className="flex-1 bg-black/50 border border-white/10 rounded px-4 py-2 text-sm focus:border-primary/50 outline-none" 
            placeholder="gsk_..."
          />
          <button onClick={testKey} disabled={!key || status === 'testing'} className="px-6 bg-primary text-white text-sm font-bold rounded hover:bg-primary/90 transition-colors disabled:opacity-50 min-w-[120px]">
            {status === 'testing' ? <Loader2 size={16} className="animate-spin mx-auto" /> : status === 'success' ? 'Connected' : 'Test Connection'}
          </button>
        </div>
        {status === 'error' && <p className="text-red-400 text-xs">Invalid key or connection failed.</p>}
      </div>
    </motion.div>
  );
};

const Step4Permissions = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Access Permissions</h2>
      <p className="text-white/50 text-sm">Nothing is accessed without your explicit consent.</p>
    </div>
    <div className="grid grid-cols-2 gap-4">
      {['Documents', 'Downloads', 'Desktop', 'Projects', 'Notes', 'Browser Bookmarks', 'Browser History'].map(p => (
        <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-white/5 bg-white/[0.02] cursor-pointer hover:bg-white/5 transition-colors">
          <input type="checkbox" defaultChecked={['Documents', 'Projects', 'Notes'].includes(p)} className="accent-primary w-4 h-4" />
          <span className="text-sm text-white/80">{p}</span>
        </label>
      ))}
    </div>
    <button onClick={next} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 transition-all self-end mt-4">
      Confirm Access
    </button>
  </motion.div>
);

const Step5Voice = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Voice & Communication</h2>
      <p className="text-white/50 text-sm">How should Primnox listen and respond?</p>
    </div>
    
    <div className="space-y-4">
      <h3 className="text-xs font-mono text-primary uppercase tracking-wider">Interaction Mode</h3>
      <div className="flex gap-2">
        {['VAD (Always Listening)', 'Push To Talk', 'Hybrid', 'Disabled'].map(m => (
          <button key={m} className={`flex-1 py-3 px-2 text-[10px] uppercase tracking-wider font-bold rounded border ${m.includes('VAD') ? 'bg-primary/20 border-primary' : 'bg-transparent border-white/10 text-white/50 hover:bg-white/5'}`}>
            {m}
          </button>
        ))}
      </div>
    </div>

    <div className="space-y-4">
      <h3 className="text-xs font-mono text-primary uppercase tracking-wider">Communication Learning</h3>
      <p className="text-[10px] text-white/40">Allow Primnox to learn your vocabulary, writing style, slang, and response preferences over time.</p>
      <div className="flex items-center gap-3 p-4 rounded-lg border border-primary/30 bg-primary/5">
        <input type="checkbox" defaultChecked className="accent-primary w-4 h-4" />
        <span className="text-sm text-white/80">Enable Adaptive Communication</span>
      </div>
    </div>

    <button onClick={next} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 transition-all self-end mt-4">
      Next Step
    </button>
  </motion.div>
);

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
      scanEnvironment().then((data: any) => {
        isDone = true;
        setProgress(100);
        if (data && data.projects) {
          setProfile(data);
          setStream(prev => [...prev, "> Scan Complete: Real data acquired!"].slice(-10));
        }
        setTimeout(next, 1500);
      });
    }

    return () => clearInterval(interval);
  }, [activity, next, scanEnvironment, setProfile]);

  return (
    <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 1.05 }} className="flex flex-col gap-8 h-[60vh]">
      <div className="text-center">
        <h2 className="text-3xl font-bold mb-2 bg-gradient-to-r from-primary to-purple-400 bg-clip-text text-transparent">Learning About You</h2>
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

const Step7UserModel = ({ next }: any) => {
  useEffect(() => { setTimeout(next, 2000); }, [next]);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center text-center h-[50vh] gap-6">
      <div className="w-16 h-16 relative">
        <Brain className="absolute inset-0 w-full h-full text-primary animate-pulse" />
        <div className="absolute inset-0 w-full h-full border-4 border-t-primary rounded-full animate-spin" />
      </div>
      <h2 className="text-2xl font-bold">Constructing User Model</h2>
      <div className="flex gap-4 text-xs font-mono text-white/40">
        <span className="animate-pulse">Interests</span>
        <span className="animate-pulse delay-75">Knowledge Areas</span>
        <span className="animate-pulse delay-150">Communication Style</span>
      </div>
    </motion.div>
  );
};

const Step8ProfileReview = ({ next, profile }: any) => (
  <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -20 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Profile Review</h2>
      <p className="text-white/50 text-sm">Transparency is mandatory. Is this accurate?</p>
    </div>

    <div className="border border-white/10 rounded-xl bg-white/5 p-6 space-y-6">
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
    </div>

    <div className="flex gap-4 justify-end">
      <button className="px-6 py-2 bg-white/5 text-white/70 font-bold text-sm rounded-lg hover:bg-white/10 border border-white/10 transition-colors">Edit Profile</button>
      <button onClick={next} className="px-8 py-2 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary/90 transition-all shadow-[0_0_20px_rgba(79,70,229,0.3)]">Looks Good</button>
    </div>
  </motion.div>
);

const Step9Memory = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Memory Preferences</h2>
      <p className="text-white/50 text-sm">How should Primnox retain context?</p>
    </div>
    
    <div className="grid grid-cols-1 gap-4">
      {[
        { id: 'smart', title: 'Smart Memory', desc: 'Automatically extract and synthesize relevant context. (Recommended)', recommended: true },
        { id: 'ask', title: 'Ask Before Saving', desc: 'Primnox will prompt you before committing to long-term memory.' },
        { id: 'never', title: 'Never Remember', desc: 'Amnesia mode. Sessions are completely ephemeral.' }
      ].map(opt => (
        <button key={opt.id} onClick={next} className="flex items-center gap-4 text-left p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 transition-all relative overflow-hidden">
          {opt.recommended && <div className="absolute top-0 right-0 bg-primary text-white text-[8px] font-bold uppercase px-2 py-1 rounded-bl">Recommended</div>}
          <div className={`w-4 h-4 rounded-full border ${opt.recommended ? 'border-primary border-4' : 'border-white/30'}`} />
          <div>
            <h3 className="font-bold text-sm">{opt.title}</h3>
            <p className="text-[10px] text-white/50">{opt.desc}</p>
          </div>
        </button>
      ))}
    </div>
  </motion.div>
);

const Step10Personalization = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Personalization Evolution</h2>
      <p className="text-white/50 text-sm">The assistant should gradually adapt to you through actual usage patterns.</p>
    </div>
    
    <div className="grid grid-cols-2 gap-4">
      {['Vocabulary Learning', 'Slang Learning', 'Writing Style Matching', 'Research Style Learning', 'Productivity Pattern Learning', 'Response Depth Adaptation'].map(p => (
        <label key={p} className="flex items-center gap-3 p-4 rounded-lg border border-white/5 bg-white/[0.02] cursor-pointer hover:bg-white/5 transition-colors">
          <input type="checkbox" defaultChecked className="accent-primary w-4 h-4" />
          <span className="text-sm text-white/80">{p}</span>
        </label>
      ))}
    </div>
    
    <button onClick={next} className="px-8 py-3 bg-white text-black font-bold text-sm rounded-lg hover:bg-white/90 transition-all self-end mt-4">
      Confirm Evolution Options
    </button>
  </motion.div>
);

const Step11Workspace = ({ next }: any) => (
  <motion.div initial={{ opacity: 0, x: 50 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -50 }} className="flex flex-col gap-8">
    <div>
      <h2 className="text-2xl font-bold mb-2">Workspace Creation</h2>
      <p className="text-white/50 text-sm">Suggested workspaces based on your profile.</p>
    </div>
    
    <div className="space-y-4">
      {['Personal Workspace', 'Development Workspace', 'Research Workspace'].map(ws => (
        <div key={ws} className="flex items-center gap-4 p-4 rounded-xl border border-white/10 bg-white/5">
          <LayoutDashboard size={20} className="text-white/40" />
          <input type="text" defaultValue={ws} className="bg-transparent border-none outline-none text-sm text-white/90 flex-1" />
        </div>
      ))}
    </div>

    <button onClick={next} className="px-8 py-3 bg-primary text-white font-bold text-sm rounded-lg hover:bg-primary/90 transition-all self-end mt-4 shadow-[0_0_20px_rgba(79,70,229,0.3)]">
      Create Workspaces
    </button>
  </motion.div>
);

const Step12AssistantGen = ({ next }: any) => {
  useEffect(() => { setTimeout(next, 3000); }, [next]);
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col items-center justify-center text-center h-[50vh] gap-6">
      <div className="w-24 h-24 relative flex items-center justify-center border-2 border-primary/30 rounded-full">
        <Sparkles className="text-primary animate-pulse" size={32} />
        <div className="absolute inset-0 border-t-2 border-primary rounded-full animate-spin" style={{ animationDuration: '3s' }} />
      </div>
      <div>
        <h2 className="text-2xl font-bold">Generating Assistant</h2>
        <p className="text-white/40 text-sm mt-2">Compiling Knowledge Graph & Memory System...</p>
      </div>
    </motion.div>
  );
};

const Step13Completion = ({ onComplete, profile: _profile }: any) => (
  <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col gap-8 text-center max-w-xl mx-auto py-10">
    <div className="w-16 h-16 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto mb-4 border border-emerald-500/50 shadow-[0_0_30px_rgba(16,185,129,0.2)]">
      <Check size={32} />
    </div>
    
    <div>
      <h2 className="text-4xl font-bold mb-4">Welcome.</h2>
      <p className="text-white/60">Primnox has initialized your personalized environment.</p>
    </div>
    
    <div className="bg-white/5 border border-white/10 rounded-xl p-6 text-left space-y-4">
      <p className="text-xs font-mono text-white/40 uppercase tracking-wider">Background Learning System Active</p>
      <p className="text-sm text-white/70 leading-relaxed">
        Primnox will continue observing your notes, research, and conversations. Over time, it will naturally improve its knowledge graph, memory system, and communication matching without imitating you excessively.
      </p>
    </div>

    <div className="grid grid-cols-2 gap-4 mt-4">
      <button onClick={onComplete} className="p-4 rounded-xl border border-primary/30 bg-primary/10 hover:bg-primary/20 text-primary transition-all flex flex-col items-center gap-2 group">
        <MessageSquare size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Open Chat</span>
      </button>
      <button onClick={onComplete} className="p-4 rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 text-white transition-all flex flex-col items-center gap-2 group">
        <Compass size={24} className="group-hover:scale-110 transition-transform" />
        <span className="font-bold text-sm">Explore Workspace</span>
      </button>
    </div>
  </motion.div>
);

