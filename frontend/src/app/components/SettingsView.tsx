import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { User, Terminal, Shield, Cpu, Wifi, WifiOff, RefreshCw, DownloadCloud, Brain, Zap, Calendar, Plus, Trash2, Link, Cloud, Key, Copy, Eye, EyeOff, AlertTriangle, CheckCircle, HardDrive } from 'lucide-react';

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
  | 'calendar'
  | 'meetings'
  | 'research_workspace';

// ── Settings mini data-flow components ───────────────────────────────────────
const SFN = ({ label, sub, c }: { label: string; sub?: string; c: string }) => (
  <div className={`flex flex-col items-center px-2 py-1 rounded-md border text-center shrink-0 ${c}`}>
    <span className="font-bold text-[9px] leading-tight whitespace-nowrap">{label}</span>
    {sub && <span className="text-[7px] opacity-50 leading-tight mt-0.5 whitespace-nowrap">{sub}</span>}
  </div>
);
const SFA = ({ c }: { c: string }) => <span className={`text-sm leading-none ${c}`}>→</span>;

const SFlowLocal = () => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <SFN label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <SFA c="text-emerald-800" />
      <SFN label="Primnox" sub="brain.py" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
      <SFA c="text-emerald-800" />
      <SFN label="Local Model" sub="on-device" c="border-emerald-600 bg-emerald-950 text-emerald-300" />
      <SFA c="text-emerald-800" />
      <SFN label="Response" sub="raw" c="border-emerald-800 bg-emerald-950 text-emerald-300" />
    </div>
    <span className="text-[8px] text-emerald-700 font-mono tracking-widest uppercase">nothing leaves your machine</span>
  </div>
);

const SFlowCloud = () => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <SFN label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <SFA c="text-slate-700" />
      <SFN label="Privacy Mirror" sub="DeBERTa NER" c="border-pink-800 bg-pink-950 text-pink-300" />
      <SFA c="text-blue-800" />
      <SFN label="Cloud API" sub="Groq / OpenAI" c="border-blue-800 bg-blue-950 text-blue-300" />
      <SFA c="text-pink-800" />
      <SFN label="Rehydrate" sub="names back" c="border-pink-800 bg-pink-950 text-pink-300" />
      <SFA c="text-slate-700" />
      <SFN label="You" sub="real names" c="border-slate-700 bg-slate-900 text-slate-300" />
    </div>
    <span className="text-[8px] text-pink-800 font-mono tracking-widest uppercase">cloud only sees §NAME_1§ — not your real name</span>
  </div>
);

const SFlowRaw = () => (
  <div className="flex flex-col items-center gap-1.5 py-1.5">
    <div className="flex items-center gap-1 flex-wrap justify-center">
      <SFN label="You" c="border-slate-700 bg-slate-900 text-slate-300" />
      <SFA c="text-slate-700" />
      <SFN label="Primnox" sub="brain.py" c="border-slate-700 bg-slate-900 text-slate-400" />
      <SFA c="text-slate-600" />
      <SFN label="Cloud API" sub="Groq / OpenAI" c="border-slate-600 bg-slate-900 text-slate-300" />
      <SFA c="text-slate-700" />
      <SFN label="You" sub="response" c="border-slate-700 bg-slate-900 text-slate-300" />
    </div>
    <span className="text-[8px] text-amber-700 font-mono tracking-widest uppercase">your data reaches the cloud as-is</span>
  </div>
);
// ─────────────────────────────────────────────────────────────────────────────

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
  dynamicIslandEnabled,
  setDynamicIslandEnabled,
  privacyMirrorEnabled,
  setPrivacyMirrorEnabled,
  ollamaModel,
  setOllamaModel,
  ollamaBaseUrl,
  setOllamaBaseUrl,
  llamacppBaseUrl,
  setLlamacppBaseUrl,
  llamacppModel,
  setLlamacppModel,
  geminiApiKey,
  setGeminiApiKey,
  calendarProviders,
  setCalendarProviders,
  meetingRetentionDays,
  setMeetingRetentionDays,
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
  dynamicIslandEnabled: boolean,
  setDynamicIslandEnabled: (v: boolean) => void,
  privacyMirrorEnabled: boolean,
  setPrivacyMirrorEnabled: (v: boolean) => void,
  ollamaModel: string,
  setOllamaModel: (v: string) => void,
  ollamaBaseUrl: string,
  setOllamaBaseUrl: (v: string) => void,
  llamacppBaseUrl: string,
  setLlamacppBaseUrl: (v: string) => void,
  llamacppModel: string,
  setLlamacppModel: (v: string) => void,
  geminiApiKey: string,
  setGeminiApiKey: (v: string) => void,
  calendarProviders: any[],
  setCalendarProviders: (v: any[]) => void,
  meetingRetentionDays: number,
  setMeetingRetentionDays: (v: number) => void,
  onSync: () => void
}) => {
  const [activeTab, setActiveTab] = useState<'System_Core' | 'Identity' | 'Security' | 'Calendar' | 'Backup'>('System_Core');
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean, models: string[] } | null>(null);
  const [checkingOllama, setCheckingOllama] = useState(false);
  const [backupStatus, setBackupStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [profile, setProfile] = useState<any>(null);

  // ── Cloud backup state ────────────────────────────────────────────────────────
  const [cloudBackupInfo, setCloudBackupInfo]         = useState<any>(null);
  const [cloudBackupList, setCloudBackupList]         = useState<any[]>([]);
  const [cloudBackupOp, setCloudBackupOp]             = useState<'idle'|'running'|'done'|'error'>('idle');
  const [cloudOpMsg, setCloudOpMsg]                   = useState('');
  const [showSetup, setShowSetup]                     = useState(false);
  const [mnemonic, setMnemonic]                       = useState('');
  const [showMnemonic, setShowMnemonic]               = useState(false);
  const [mnemonicGenLoading, setMnemonicGenLoading]   = useState(false);
  const [providerType, setProviderType]               = useState<'s3'|'gdrive'|'dropbox'|'https'>('s3');
  const [backupInterval, setBackupInterval]           = useState(24);
  const [s3Cfg, setS3Cfg] = useState({ bucket: '', endpoint_url: '', region: 'us-east-1', access_key: '', secret_key: '' });
  const [httpsCfg, setHttpsCfg]                       = useState({ url: '', auth_header: '' });
  const [restoreFile, setRestoreFile]                 = useState('');
  const [restoreMnemonic, setRestoreMnemonic]         = useState('');
  const [showRestoreMnemonic, setShowRestoreMnemonic] = useState(false);
  // Import a .prx backup straight from disk (no cloud provider required)
  const [importFile, setImportFile]                   = useState<File | null>(null);
  const [importMnemonic, setImportMnemonic]           = useState('');
  const [showImportMnemonic, setShowImportMnemonic]   = useState(false);
  const [importOp, setImportOp]                       = useState<'idle'|'running'|'done'|'error'>('idle');
  const [importMsg, setImportMsg]                     = useState('');

  // ── PII model status ──────────────────────────────────────────────────────────
  const [piiModelStatus, setPiiModelStatus] = useState<'loading'|'ready'|'failed'|'unavailable'|null>(null);

  // ── Architecture mode (derived from props on mount) ───────────────────────
  const [archMode, setArchMode] = useState<'local' | 'hybrid' | 'cloud_shield' | 'cloud_raw'>(() => {
    if (activeModel === 'Ollama_Local' || activeModel === 'LlamaCpp_Local')
      return apiKey ? 'hybrid' : 'local';
    return privacyMirrorEnabled ? 'cloud_shield' : 'cloud_raw';
  });
  const [localEngine, setLocalEngine] = useState<'ollama' | 'llamacpp'>(
    activeModel === 'LlamaCpp_Local' ? 'llamacpp' : 'ollama'
  );
  const [cloudModel, setCloudModel] = useState(() => {
    const cloud = ['Groq_Llama_3', 'OpenAI_GPT_4o', 'Anthropic_Claude_3', 'Gemini_Flash'];
    return cloud.includes(activeModel) ? activeModel : 'Groq_Llama_3';
  });
  useEffect(() => {
    if (activeTab !== 'Security') return;
    fetch('http://localhost:4009/api/status', { signal: AbortSignal.timeout(4000) })
      .then(r => r.json())
      .then(d => setPiiModelStatus(d.pii_model_status ?? null))
      .catch(() => setPiiModelStatus(null));
  }, [activeTab]);

  // ── Local Vault state ─────────────────────────────────────────────────────────
  const [vaultStatus, setVaultStatus] = useState<{enabled: boolean, locked: boolean} | null>(null);
  const [vaultMnemonic, setVaultMnemonic] = useState('');
  const [vaultMnemonicGenerated, setVaultMnemonicGenerated] = useState('');
  const [vaultOp, setVaultOp] = useState<'idle'|'running'|'done'|'error'>('idle');
  const [vaultOpMsg, setVaultOpMsg] = useState('');
  const [vaultPhrase, setVaultPhrase] = useState<string | null>(null);
  const [showPhrase, setShowPhrase] = useState(false);

  useEffect(() => {
    if (activeTab !== 'Security') return;
    fetch('http://localhost:4009/api/vault/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setVaultStatus(d); })
      .catch(() => {});
  }, [activeTab]);

  useEffect(() => {
    fetch('http://localhost:4009/api/profile')
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setProfile(d))
      .catch(() => {});
  }, []);

  // Load cloud backup status + list whenever the Backup tab is opened
  useEffect(() => {
    if (activeTab !== 'Backup') return;
    fetch('http://localhost:4009/api/backup/status')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setCloudBackupInfo(d); })
      .catch(() => {});
    fetch('http://localhost:4009/api/backup/list')
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d?.backups) setCloudBackupList(d.backups); })
      .catch(() => {});
  }, [activeTab]);

  const triggerBackup = async () => {
    setBackupStatus('running');
    try {
      const res = await fetch('http://localhost:4009/api/backup', { method: 'POST' });
      if (res.ok) setBackupStatus('done');
      else setBackupStatus('error');
    } catch {
      setBackupStatus('error');
    }
    setTimeout(() => setBackupStatus('idle'), 4000);
  };

  const checkOllama = async () => {
    setCheckingOllama(true);
    try {
      const res = await fetch('http://localhost:4009/api/ollama/status');
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

  const generateMnemonic = async () => {
    setMnemonicGenLoading(true);
    try {
      const r = await fetch('http://localhost:4009/api/backup/generate-mnemonic', { method: 'POST' });
      const d = await r.json();
      if (r.ok) { setMnemonic(d.mnemonic); setShowMnemonic(true); }
      else setCloudOpMsg(d.detail || 'Failed to generate phrase');
    } catch { setCloudOpMsg('Backend unavailable'); }
    setMnemonicGenLoading(false);
  };

  const setupCloudBackup = async () => {
    if (!mnemonic.trim()) return;
    const cfg = providerType === 's3' ? s3Cfg : providerType === 'https' ? httpsCfg : {};
    setCloudBackupOp('running'); setCloudOpMsg('');
    try {
      const r = await fetch('http://localhost:4009/api/backup/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mnemonic: mnemonic.trim(), provider: providerType, provider_config: cfg, interval_hours: backupInterval }),
      });
      const d = await r.json();
      if (r.ok) {
        setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Backup configured');
        setShowSetup(false);
        try {
          const st = await fetch('http://localhost:4009/api/backup/status').then(x => x.json());
          setCloudBackupInfo(st);
        } catch { /* status refresh is best-effort */ }
      } else {
        setCloudBackupOp('error'); setCloudOpMsg(d.detail || 'Setup failed');
      }
    } catch { setCloudBackupOp('error'); setCloudOpMsg('Backend unavailable'); }
    setTimeout(() => setCloudBackupOp('idle'), 4000);
  };

  const runCloudBackupNow = async () => {
    setCloudBackupOp('running'); setCloudOpMsg('');
    try {
      const r = await fetch('http://localhost:4009/api/backup/now', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      const d = await r.json();
      if (r.ok) { setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Backup started'); }
      else { setCloudBackupOp('error'); setCloudOpMsg(d.detail || 'Backup failed'); }
    } catch { setCloudBackupOp('error'); setCloudOpMsg('Backend unavailable'); }
    setTimeout(() => { setCloudBackupOp('idle'); setCloudOpMsg(''); }, 5000);
  };

  const runCloudRestore = async () => {
    if (!restoreFile || !restoreMnemonic.trim()) return;
    setCloudBackupOp('running'); setCloudOpMsg('Restoring…');
    try {
      const r = await fetch('http://localhost:4009/api/backup/restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: restoreFile, mnemonic: restoreMnemonic.trim() }),
      });
      const d = await r.json();
      if (r.ok) { setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Restore complete — restart Primnox'); }
      else { setCloudBackupOp('error'); setCloudOpMsg(d.detail || 'Restore failed'); }
    } catch { setCloudBackupOp('error'); setCloudOpMsg('Backend unavailable'); }
    setTimeout(() => { setCloudBackupOp('idle'); setCloudOpMsg(''); }, 6000);
  };

  const runImport = async () => {
    if (!importFile || !importMnemonic.trim()) return;
    setImportOp('running'); setImportMsg('Decrypting & restoring…');
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      fd.append('mnemonic', importMnemonic.trim());
      const r = await fetch('http://localhost:4009/api/backup/import', { method: 'POST', body: fd });
      const d = await r.json();
      if (r.ok) { setImportOp('done'); setImportMsg(d.message || 'Import complete — restart Primnox'); }
      else { setImportOp('error'); setImportMsg(d.detail || 'Import failed'); }
    } catch { setImportOp('error'); setImportMsg('Backend unavailable'); }
    setTimeout(() => { if (importOp !== 'done') { setImportOp('idle'); setImportMsg(''); } }, 8000);
  };

  const disableCloudBackup = async () => {
    await fetch('http://localhost:4009/api/backup/disable', { method: 'POST' });
    setCloudBackupInfo(null); setShowSetup(false); setMnemonic('');
  };

  const enableVault = async () => {
    setVaultOp('running'); setVaultOpMsg(''); setVaultMnemonicGenerated('');
    try {
      const res = await fetch('http://localhost:4009/api/vault/setup', { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setVaultOp('done');
        setVaultOpMsg('Vault enabled!');
        setVaultMnemonicGenerated(data.mnemonic);
        setVaultStatus({ enabled: true, locked: false });
      } else {
        setVaultOp('error'); setVaultOpMsg(data.detail || 'Failed');
      }
    } catch { setVaultOp('error'); setVaultOpMsg('Backend unavailable'); }
  };

  const unlockVault = async () => {
    if (!vaultMnemonic.trim()) return;
    setVaultOp('running'); setVaultOpMsg('');
    try {
      const res = await fetch('http://localhost:4009/api/vault/unlock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mnemonic: vaultMnemonic.trim() })
      });
      if (res.ok) {
        setVaultOp('done'); setVaultOpMsg('Vault unlocked!');
        setVaultStatus({ enabled: true, locked: false });
        setVaultMnemonic('');
      } else {
        const data = await res.json();
        setVaultOp('error'); setVaultOpMsg(data.detail || 'Unlock failed');
      }
    } catch { setVaultOp('error'); setVaultOpMsg('Backend unavailable'); }
    setTimeout(() => { if (vaultOp !== 'error') setVaultOp('idle'); }, 4000);
  };

  const disableVault = async () => {
    setVaultOp('running'); setVaultOpMsg('');
    try {
      const res = await fetch('http://localhost:4009/api/vault/disable', { method: 'POST' });
      if (res.ok) {
        setVaultOp('done'); setVaultOpMsg('Vault disabled and fully decrypted.');
        setVaultStatus({ enabled: false, locked: false });
        setVaultMnemonicGenerated('');
        setVaultPhrase(null); setShowPhrase(false);
      } else {
        const data = await res.json();
        setVaultOp('error'); setVaultOpMsg(data.detail || 'Failed');
      }
    } catch { setVaultOp('error'); setVaultOpMsg('Backend unavailable'); }
    setTimeout(() => { setVaultOp('idle'); setVaultOpMsg(''); }, 4000);
  };

  const fetchVaultPhrase = async () => {
    try {
      const tokenRes = await fetch('http://localhost:4009/api/vault/phrase-token', { method: 'POST' });
      if (!tokenRes.ok) {
        const err = await tokenRes.json().catch(() => ({}));
        setVaultOpMsg(err.detail || 'Could not issue phrase token — vault may be locked.');
        return;
      }
      const { token } = await tokenRes.json();
      const res = await fetch('http://localhost:4009/api/vault/phrase', { headers: { 'X-Vault-Token': token } });
      if (!res.ok) throw new Error('Not found');
      const data = await res.json();
      setVaultPhrase(data.phrase);
      setShowPhrase(true);
    } catch {
      setVaultPhrase(null);
      setVaultOpMsg('Recovery phrase not available. Re-enable the vault to generate a new one.');
    }
  };

  const tabs = [
    { id: 'System_Core', label: 'System_Core', icon: Cpu },
    { id: 'Identity', label: 'Identity', icon: User },
    { id: 'Security', label: 'Security', icon: Shield },
    { id: 'Calendar', label: 'Calendar', icon: Calendar },
    { id: 'Backup', label: 'Backup', icon: Cloud },
  ] as const;

  // ── Calendar add-form state ──────────────────────────────────────────────
  const [showAddCal, setShowAddCal] = useState(false);
  const [calType,    setCalType]    = useState<'ical' | 'google' | 'outlook' | 'notion'>('ical');
  const [calUrl,     setCalUrl]     = useState('');
  const [calName,    setCalName]    = useState('');
  const [calColor,   setCalColor]   = useState('#6366f1');

  const handleAddCalendar = () => {
    if (!calUrl.trim() && calType === 'ical') return;
    const newProvider: any = { type: calType, name: calName || calType, color: calColor };
    if (calType === 'ical') newProvider.url = calUrl.trim();
    setCalendarProviders([...calendarProviders, newProvider]);
    setCalUrl(''); setCalName(''); setCalColor('#6366f1'); setShowAddCal(false);
  };

  return (
    <div className="h-full flex items-start justify-center p-4 md:p-6 lg:p-8 text-left overflow-y-auto">
      <motion.div
        initial={{ scale: 0.95, opacity: 0, y: 20 }}
        animate={{ scale: 1, opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className="max-w-4xl w-full max-h-[calc(100vh-4rem)] glass-panel rounded-lg shadow-2xl border border-white/10 flex flex-col md:flex-row bg-[#050505]/80 backdrop-blur-3xl overflow-hidden"
      >
        {/* Sidebar Tabs */}
        <div className="w-full md:w-60 shrink-0 border-r border-white/5 bg-zinc-950 p-6 space-y-2 flex flex-col justify-between">
          <div className="space-y-2">
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
          
          <div className="pt-4">
            <div className="p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 backdrop-blur-sm">
              <div className="flex items-center gap-3 mb-3">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_10px_rgba(16,185,129,0.8)]" />
                <span className="font-mono text-[10px] text-emerald-400 uppercase font-bold tracking-widest">Kernel_Stable</span>
              </div>
              <p className="text-[10px] text-emerald-400/40 font-mono tracking-tighter uppercase whitespace-nowrap leading-none">Active Engine: {activeModel}</p>
            </div>
          </div>
        </div>

        {/* Content Panel */}
        <div className="flex-1 overflow-y-auto p-6 lg:p-8 space-y-6 flex flex-col justify-between">
          <div className="space-y-6">
            <header className="space-y-1 border-b border-white/5 pb-5">
              <h2 className="font-bold lowercase italic tracking-wide text-2xl text-white">Machine_Cognition_Settings</h2>
              <p className="text-white/30 font-light text-sm">Calibrate the neural interface and operative parameters.</p>
            </header>

            {/* Render Tab Contents */}
            <div className="min-h-[220px]">
              {activeTab === 'System_Core' && (
                <motion.section 
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="space-y-6"
                >
                  {/* ── Privacy Architecture Selector ── */}
                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Privacy_Architecture</label>
                    <div className="grid grid-cols-2 gap-3">
                      {/* Local */}
                      <button onClick={() => { setArchMode('local'); setActiveModel(localEngine === 'llamacpp' ? 'LlamaCpp_Local' : 'Ollama_Local'); }}
                        className={`p-3 rounded-xl border text-left transition-all ${archMode === 'local' ? 'border-emerald-500/50 bg-emerald-500/10' : 'border-white/5 bg-black/30 hover:border-white/10'}`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <HardDrive size={12} className={archMode === 'local' ? 'text-emerald-400' : 'text-white/25'} />
                          <span className={`font-mono text-[10px] font-bold uppercase tracking-widest ${archMode === 'local' ? 'text-emerald-400' : 'text-white/35'}`}>Local</span>
                        </div>
                        <p className="text-[9px] text-white/25 leading-relaxed">Nothing leaves your machine. Ollama or llama.cpp only.</p>
                      </button>

                      {/* Hybrid */}
                      <button onClick={() => { setArchMode('hybrid'); setActiveModel(localEngine === 'llamacpp' ? 'LlamaCpp_Local' : 'Ollama_Local'); }}
                        className={`p-3 rounded-xl border text-left transition-all ${archMode === 'hybrid' ? 'border-orange-500/50 bg-orange-500/10' : 'border-white/5 bg-black/30 hover:border-white/10'}`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <Zap size={12} className={archMode === 'hybrid' ? 'text-orange-400' : 'text-white/25'} />
                          <span className={`font-mono text-[10px] font-bold uppercase tracking-widest ${archMode === 'hybrid' ? 'text-orange-400' : 'text-white/35'}`}>Hybrid</span>
                        </div>
                        <p className="text-[9px] text-white/25 leading-relaxed">Local model for chat. Cloud transcription for voice.</p>
                      </button>

                      {/* Cloud + Mirror */}
                      <button onClick={() => { setArchMode('cloud_shield'); setActiveModel(cloudModel); setPrivacyMirrorEnabled(true); }}
                        className={`p-3 rounded-xl border text-left transition-all ${archMode === 'cloud_shield' ? 'border-blue-500/50 bg-blue-500/10' : 'border-white/5 bg-black/30 hover:border-white/10'}`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <Shield size={12} className={archMode === 'cloud_shield' ? 'text-blue-400' : 'text-white/25'} />
                          <span className={`font-mono text-[10px] font-bold uppercase tracking-widest ${archMode === 'cloud_shield' ? 'text-blue-400' : 'text-white/35'}`}>Cloud + Mirror</span>
                        </div>
                        <p className="text-[9px] text-white/25 leading-relaxed">Cloud model with PII scrubbed before it leaves this machine.</p>
                      </button>

                      {/* Cloud Raw */}
                      <button onClick={() => { setArchMode('cloud_raw'); setActiveModel(cloudModel); setPrivacyMirrorEnabled(false); }}
                        className={`p-3 rounded-xl border text-left transition-all ${archMode === 'cloud_raw' ? 'border-slate-500/50 bg-slate-500/10' : 'border-white/5 bg-black/30 hover:border-white/10'}`}>
                        <div className="flex items-center gap-2 mb-1.5">
                          <Cloud size={12} className={archMode === 'cloud_raw' ? 'text-slate-300' : 'text-white/25'} />
                          <span className={`font-mono text-[10px] font-bold uppercase tracking-widest ${archMode === 'cloud_raw' ? 'text-slate-300' : 'text-white/35'}`}>Cloud Raw</span>
                        </div>
                        <p className="text-[9px] text-white/25 leading-relaxed">Cloud model, no scrubbing. Data reaches provider as-is.</p>
                      </button>
                    </div>

                    {/* ── Local / Hybrid expanded panel ── */}
                    {(archMode === 'local' || archMode === 'hybrid') && (
                      <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
                        className={`rounded-xl border p-5 space-y-4 ${archMode === 'hybrid' ? 'border-orange-500/20 bg-orange-500/5' : 'border-emerald-500/20 bg-emerald-500/5'}`}>
                        <SFlowLocal />

                        {/* Engine toggle */}
                        <div className="flex gap-2">
                          <button onClick={() => { setLocalEngine('ollama'); setActiveModel('Ollama_Local'); }}
                            className={`flex-1 py-2 rounded-lg font-mono text-[9px] uppercase tracking-widest font-bold border transition-all
                              ${localEngine === 'ollama' ? 'border-emerald-500/40 bg-emerald-500/10 text-emerald-400' : 'border-white/5 text-white/30 hover:text-white/50'}`}>
                            Ollama
                          </button>
                          <button onClick={() => { setLocalEngine('llamacpp'); setActiveModel('LlamaCpp_Local'); }}
                            className={`flex-1 py-2 rounded-lg font-mono text-[9px] uppercase tracking-widest font-bold border transition-all
                              ${localEngine === 'llamacpp' ? 'border-violet-500/40 bg-violet-500/10 text-violet-400' : 'border-white/5 text-white/30 hover:text-white/50'}`}>
                            llama.cpp
                          </button>
                        </div>

                        {/* Ollama config */}
                        {localEngine === 'ollama' && (
                          <div className="space-y-3">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2">
                                {checkingOllama ? <RefreshCw size={12} className="text-white/30 animate-spin" /> :
                                 ollamaStatus?.running ? <Wifi size={12} className="text-emerald-400" /> : <WifiOff size={12} className="text-red-400" />}
                                <span className="font-mono text-[9px] uppercase tracking-widest text-white/40">
                                  {checkingOllama ? 'Checking…' : ollamaStatus?.running ? `Running — ${ollamaStatus.models.length} model(s)` : 'Not detected'}
                                </span>
                              </div>
                              <button onClick={checkOllama} className="text-[9px] font-mono text-white/25 hover:text-emerald-400 transition-colors uppercase tracking-widest">Refresh</button>
                            </div>
                            {!ollamaStatus?.running && (
                              <p className="text-[9px] text-amber-400/70 font-mono">Run <span className="text-amber-300 bg-white/5 px-1 rounded">ollama serve</span> then refresh. Pull a model: <span className="text-amber-300 bg-white/5 px-1 rounded">ollama pull llama3.2</span></p>
                            )}
                            <div className="grid grid-cols-2 gap-3">
                              <div className="space-y-1.5">
                                <label className="font-mono text-[9px] text-white/25 uppercase tracking-widest">URL</label>
                                <input value={ollamaBaseUrl} onChange={e => setOllamaBaseUrl(e.target.value)}
                                  className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80"
                                  placeholder="http://localhost:11434" />
                              </div>
                              <div className="space-y-1.5">
                                <label className="font-mono text-[9px] text-white/25 uppercase tracking-widest">Model</label>
                                {ollamaStatus?.running && ollamaStatus.models.length > 0 ? (
                                  <select value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                                    className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80 appearance-none">
                                    {ollamaStatus.models.map(m => <option key={m}>{m}</option>)}
                                  </select>
                                ) : (
                                  <input value={ollamaModel} onChange={e => setOllamaModel(e.target.value)}
                                    className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-emerald-500/40 text-white/80"
                                    placeholder="llama3.2" />
                                )}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* llama.cpp config */}
                        {localEngine === 'llamacpp' && (
                          <div className="space-y-3">
                            <p className="text-[9px] text-amber-400/70 font-mono">Start: <span className="text-amber-300 bg-white/5 px-1 rounded">./llama-server -m model.gguf --port 8080</span></p>
                            <div className="grid grid-cols-2 gap-3">
                              <div className="space-y-1.5">
                                <label className="font-mono text-[9px] text-white/25 uppercase tracking-widest">URL</label>
                                <input value={llamacppBaseUrl} onChange={e => setLlamacppBaseUrl(e.target.value)}
                                  className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-violet-500/40 text-white/80"
                                  placeholder="http://localhost:8080" />
                              </div>
                              <div className="space-y-1.5">
                                <label className="font-mono text-[9px] text-white/25 uppercase tracking-widest">Model <span className="opacity-40">(optional)</span></label>
                                <input value={llamacppModel} onChange={e => setLlamacppModel(e.target.value)}
                                  className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[11px] outline-none focus:border-violet-500/40 text-white/80"
                                  placeholder="leave blank for default" />
                              </div>
                            </div>
                          </div>
                        )}

                        {archMode === 'hybrid' && (
                          <p className="text-[9px] text-orange-400/60 font-mono border-t border-orange-500/10 pt-3">
                            Voice transcription uses Groq Whisper when available — add your Groq key in the{' '}
                            <button type="button" className="text-orange-400 underline" onClick={() => setActiveTab('Security')}>Security tab</button>.
                          </p>
                        )}
                      </motion.div>
                    )}

                    {/* ── Cloud + Mirror / Cloud Raw expanded panel ── */}
                    {(archMode === 'cloud_shield' || archMode === 'cloud_raw') && (
                      <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }}
                        className={`rounded-xl border p-5 space-y-4 ${archMode === 'cloud_shield' ? 'border-blue-500/20 bg-blue-500/5' : 'border-slate-500/20 bg-slate-500/5'}`}>
                        {archMode === 'cloud_shield' ? <SFlowCloud /> : <SFlowRaw />}

                        <div className="space-y-1.5">
                          <label className="font-mono text-[9px] text-white/25 uppercase tracking-widest">Cloud_Model</label>
                          <select value={cloudModel} onChange={e => { setCloudModel(e.target.value); setActiveModel(e.target.value); }}
                            className="w-full bg-black/60 border border-white/10 rounded-lg py-2.5 px-3 font-mono text-[11px] outline-none focus:border-blue-500/40 text-white/80 appearance-none">
                            <option value="Groq_Llama_3">Groq — Llama 3.3 70B (HyperSpeed)</option>
                            <option value="OpenAI_GPT_4o">OpenAI — GPT-4o (Max Reasoning)</option>
                            <option value="Anthropic_Claude_3">Anthropic — Claude 3.5 Sonnet</option>
                            <option value="Gemini_Flash">Google — Gemini Flash 2.0</option>
                          </select>
                        </div>

                        {archMode === 'cloud_shield' ? (
                          <p className="text-[9px] text-blue-400/50 font-mono">
                            Privacy Mirror is <span className="text-emerald-400">active</span> — DeBERTa NER scrubs PII from every request before it leaves this machine.
                          </p>
                        ) : (
                          <div className="flex items-start gap-2 p-3 rounded-lg border border-amber-500/20 bg-amber-500/5">
                            <AlertTriangle size={11} className="text-amber-400 shrink-0 mt-0.5" />
                            <p className="text-[9px] text-amber-400/70 font-mono">Privacy Mirror is off. Your messages reach the cloud provider exactly as typed — names, emails, and other PII included.</p>
                          </div>
                        )}
                      </motion.div>
                    )}
                  </div>

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

                  {/* Dynamic Island toggle (#13) */}
                  <div className="bg-black/40 border border-white/5 p-4 rounded-xl flex items-center justify-between gap-6">
                    <div className="space-y-1 min-w-0">
                      <label className="block font-mono text-[10px] text-white/25 uppercase tracking-[0.3em] font-bold">Dynamic_Island</label>
                      <p className="text-[11px] text-white/30 font-light">Floating pill overlay when minimized. Off = normal minimize to taskbar.</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const v = !dynamicIslandEnabled;
                        setDynamicIslandEnabled(v);
                        (window as any).electron?.ipcRenderer?.send('island:set-enabled', v);
                      }}
                      className={`shrink-0 w-32 py-3 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold border transition-all active:scale-95 cursor-pointer
                        ${dynamicIslandEnabled
                          ? 'bg-primary/10 border-primary/20 text-primary hover:bg-primary/20'
                          : 'bg-white/5 border-transparent text-white/40 hover:text-white/60'}`}
                    >
                      {dynamicIslandEnabled ? "Enabled" : "Disabled"}
                    </button>
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

                  <div className="space-y-4">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Gemini_API_Key</label>
                    <div className="relative group">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 font-mono text-[10px] text-white/10 font-bold">HEX</div>
                      <input
                        type="password"
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-4 pl-14 pr-6 font-mono text-xs focus:ring-1 focus:ring-primary outline-none transition-all placeholder-white/5"
                        value={geminiApiKey}
                        onChange={(e) => setGeminiApiKey(e.target.value)}
                        placeholder="Google AI Studio API key..."
                      />
                    </div>
                  </div>

                  {/* Privacy Shield (PII scrubber) */}
                  <div className="space-y-4 pt-2 border-t border-white/5">
                    <div className="flex items-center justify-between">
                      <div>
                        <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Privacy_Shield</label>
                        <p className="text-xs text-white/40 font-light mt-1">
                          Scrubs PII from context before it reaches the AI. Uses a local DeBERTa model — no data leaves your machine.
                        </p>
                      </div>
                      <button
                        onClick={() => setPrivacyMirrorEnabled(!privacyMirrorEnabled)}
                        className={`relative shrink-0 w-10 h-5 rounded-full border transition-all duration-200 ${
                          privacyMirrorEnabled
                            ? 'bg-emerald-500/20 border-emerald-500/40'
                            : 'bg-white/5 border-white/10'
                        }`}
                      >
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full transition-all duration-200 ${
                          privacyMirrorEnabled
                            ? 'left-5 bg-emerald-400'
                            : 'left-0.5 bg-white/20'
                        }`} />
                      </button>
                    </div>

                    {/* Model status row */}
                    {privacyMirrorEnabled && (
                      <div className={`flex items-center gap-2.5 px-3 py-2 rounded-lg border text-xs font-mono ${
                        piiModelStatus === 'ready'
                          ? 'bg-emerald-500/8 border-emerald-500/20 text-emerald-400/70'
                          : piiModelStatus === 'loading'
                          ? 'bg-amber-500/8 border-amber-500/20 text-amber-400/70'
                          : piiModelStatus === 'failed'
                          ? 'bg-red-500/10 border-red-500/25 text-red-400/80'
                          : 'bg-white/5 border-white/10 text-white/30'
                      }`}>
                        <Shield size={11} className="shrink-0" />
                        {piiModelStatus === 'ready'    && 'Model loaded — shield active'}
                        {piiModelStatus === 'loading'  && 'Model loading in background…'}
                        {piiModelStatus === 'failed'   && 'Model failed to load — disable Privacy Shield or check your internet connection and restart'}
                        {piiModelStatus === 'unavailable' && 'Status unavailable — is the backend running?'}
                        {piiModelStatus === null        && 'Checking model status…'}
                      </div>
                    )}
                  </div>

                  {/* Local Encryption Vault */}
                  <div className="space-y-4 pt-2 border-t border-white/5">
                    <div className="flex items-center justify-between">
                      <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Local_Encryption_Vault</label>
                      {vaultStatus?.enabled && (
                        <div className={`px-2 py-1 rounded text-[9px] font-mono uppercase tracking-widest ${vaultStatus.locked ? 'bg-red-500/20 text-red-400' : 'bg-emerald-500/20 text-emerald-400'}`}>
                          {vaultStatus.locked ? 'LOCKED' : 'UNLOCKED'}
                        </div>
                      )}
                    </div>
                    <p className="text-xs text-white/50 font-light">
                      Encrypts your SQLite databases at rest using AES-GCM and a 12-word seed phrase.
                    </p>

                    {!vaultStatus?.enabled && (
                      <div className="space-y-4">
                        <button
                          onClick={enableVault}
                          disabled={vaultOp === 'running'}
                          className="w-full bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-xl py-3 text-xs font-mono uppercase tracking-widest transition-all active:scale-95 flex items-center justify-center gap-2"
                        >
                          <Shield size={14} /> Enable Local Vault
                        </button>
                        {vaultMnemonicGenerated && (
                          <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-xl space-y-3">
                            <div className="flex items-center gap-2 text-emerald-400">
                              <AlertTriangle size={14} />
                              <span className="text-xs font-bold uppercase tracking-wider">Save This Recovery Phrase</span>
                            </div>
                            <p className="text-xs text-white/70">
                              This is the only key that can decrypt your local database. If you lose it, you lose your data.
                            </p>
                            <div className="p-3 bg-black/60 rounded border border-emerald-500/20 font-mono text-sm text-white select-all text-center tracking-wide leading-relaxed">
                              {vaultMnemonicGenerated}
                            </div>
                          </div>
                        )}
                      </div>
                    )}

                    {vaultStatus?.enabled && vaultStatus?.locked && (
                      <div className="space-y-3 p-4 bg-red-500/5 border border-red-500/10 rounded-xl">
                        <p className="text-xs text-white/70">Enter your 12-word recovery phrase to unlock your database.</p>
                        <div className="relative group">
                          <input
                            type="text"
                            value={vaultMnemonic}
                            onChange={(e) => setVaultMnemonic(e.target.value)}
                            placeholder="Enter 12-word phrase..."
                            className="w-full bg-black/60 border border-white/10 rounded-xl py-3 px-4 font-mono text-xs focus:ring-1 focus:ring-red-500 outline-none transition-all placeholder-white/20 text-white"
                          />
                        </div>
                        <button
                          onClick={unlockVault}
                          disabled={!vaultMnemonic.trim() || vaultOp === 'running'}
                          className="w-full bg-red-500/20 hover:bg-red-500/30 border border-red-500/30 text-red-400 rounded-xl py-3 text-xs font-mono uppercase tracking-widest transition-all active:scale-95 disabled:opacity-50"
                        >
                          {vaultOp === 'running' ? 'Unlocking...' : 'Unlock Vault'}
                        </button>
                      </div>
                    )}

                    {vaultStatus?.enabled && !vaultStatus?.locked && (
                      <div className="p-4 bg-white/5 border border-white/10 rounded-xl">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <CheckCircle size={16} className="text-emerald-400" />
                            <span className="text-xs text-white/70">Vault is active and decrypted for this session.</span>
                          </div>
                          <div className="flex items-center gap-2">
                            <button
                              onClick={disableVault}
                              disabled={vaultOp === 'running'}
                              className="text-xs text-red-400 hover:text-red-300 font-mono tracking-widest uppercase transition-colors"
                            >
                              Disable Vault
                            </button>
                            <button
                              onClick={fetchVaultPhrase}
                              className="ml-2 px-3 py-1 text-[10px] font-mono uppercase tracking-widest border border-amber-500/30 text-amber-400 rounded hover:bg-amber-500/10 transition-colors"
                            >
                              Show Recovery Phrase
                            </button>
                          </div>
                        </div>
                        {showPhrase && vaultPhrase && (
                          <div className="mt-3 p-3 rounded-lg bg-amber-950/30 border border-amber-500/20">
                            <p className="text-[9px] uppercase tracking-widest text-amber-400/60 mb-2">Recovery Phrase — keep this safe</p>
                            <p className="font-mono text-xs text-amber-200 leading-relaxed select-all break-words">{vaultPhrase}</p>
                            <button
                              onClick={() => setShowPhrase(false)}
                              className="mt-2 text-[9px] text-white/30 hover:text-white/60 underline transition-colors"
                            >Hide</button>
                          </div>
                        )}
                      </div>
                    )}

                    {vaultOpMsg && (
                      <p className={`text-[10px] font-mono tracking-wider ${vaultOp === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>
                        {vaultOpMsg}
                      </p>
                    )}
                  </div>

                  {/* Data Backup + Retention */}
                  <div className="space-y-4 pt-2 border-t border-white/5">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Data_Management</label>

                    {/* Backup row */}
                    <div className="flex items-center gap-4 p-4 bg-black/30 border border-white/5 rounded-xl">
                      <div className="flex-1">
                        <p className="text-xs text-white/60 font-light">Backup memories, notes, and chat to a local zip file. Auto-backups run every 6 hours.</p>
                      </div>
                      <button
                        onClick={triggerBackup}
                        disabled={backupStatus === 'running'}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95 shrink-0 ${
                          backupStatus === 'done' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
                          backupStatus === 'error' ? 'bg-red-500/20 text-red-400 border border-red-500/30' :
                          'bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-black'
                        }`}
                      >
                        <DownloadCloud size={14} />
                        {backupStatus === 'running' ? 'Backing up...' : backupStatus === 'done' ? 'Done ✓' : backupStatus === 'error' ? 'Failed ✗' : 'Backup Now'}
                      </button>
                    </div>

                    {/* Retention / Cleanup */}
                    <div className="space-y-3 p-4 bg-black/30 border border-white/5 rounded-xl">
                      <p className="text-[10px] text-white/30 font-mono uppercase tracking-widest mb-3">Data_Retention</p>

                      {/* Memory note */}
                      <div className="flex items-start gap-3 p-3 rounded-lg bg-white/[0.03] border border-white/[0.05]">
                        <Brain size={13} className="text-indigo-400/50 mt-0.5 shrink-0" />
                        <div>
                          <p className="text-[11px] text-white/50">Memories older than 7 days are automatically compressed into weekly summaries.</p>
                          <p className="text-[10px] text-white/25 mt-0.5 font-mono">Edit or delete individual memories in Data_Vault.</p>
                        </div>
                      </div>

                      {/* Meeting recordings auto-delete */}
                      <div className="flex items-center justify-between gap-4 pt-1">
                        <div>
                          <p className="text-xs text-white/60 font-light">Meeting recordings auto-delete</p>
                          <p className="font-mono text-[9px] text-white/20 mt-0.5">Delete folders older than N days (0 = keep forever)</p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <input
                            type="number" min="0" max="365"
                            value={meetingRetentionDays}
                            onChange={e => setMeetingRetentionDays(Number(e.target.value))}
                            className="w-16 bg-black/60 border border-white/10 rounded-lg px-2 py-1.5 text-xs text-white text-center outline-none focus:border-primary/40 font-mono"
                          />
                          <span className="font-mono text-[9px] text-white/25">days</span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between pt-2 border-t border-white/[0.04]">
                        <button
                          onClick={() => { onNavigate('meetings' as any); }}
                          className="flex items-center gap-1.5 text-[10px] font-mono text-white/30 hover:text-white/60 transition-colors"
                        >
                          <span>View Recordings →</span>
                        </button>
                        <button
                          onClick={async () => {
                            try {
                              const r = await fetch('http://localhost:4009/api/cleanup', { method: 'POST' });
                              const d = await r.json();
                              const parts = [
                                d.memories_compressed > 0 ? `compressed: ${d.memories_compressed}` : null,
                                `meetings: ${d.meetings_deleted}`,
                              ].filter(Boolean).join(' · ');
                              alert(`Cleanup done${parts ? ` — ${parts}` : ' — nothing to do'}`);
                            } catch { alert('Cleanup failed — is backend running?'); }
                          }}
                          className="flex items-center gap-2 px-4 py-2 rounded-xl font-mono text-[10px] uppercase tracking-widest bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all active:scale-95"
                        >
                          <RefreshCw size={11} /> Run Cleanup Now
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* User Profile */}
                  {profile && (profile.mood || profile.onboarding_profile?.occupation) && (
                    <div className="space-y-3 pt-2 border-t border-white/5">
                      <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">Neural_Profile</label>
                      <div className="grid grid-cols-2 gap-3">
                        {profile.mood && (
                          <div className="p-4 bg-violet-500/5 border border-violet-500/20 rounded-xl flex items-start gap-3">
                            <Brain size={14} className="text-violet-400 mt-0.5 shrink-0" />
                            <div>
                              <p className="font-mono text-[9px] text-white/30 uppercase tracking-widest mb-1">Current_Vibe</p>
                              <p className="text-sm font-bold text-violet-300">{profile.mood}</p>
                            </div>
                          </div>
                        )}
                        {profile.onboarding_profile?.occupation && (
                          <div className="p-4 bg-primary/5 border border-primary/20 rounded-xl flex items-start gap-3">
                            <Zap size={14} className="text-primary mt-0.5 shrink-0" />
                            <div>
                              <p className="font-mono text-[9px] text-white/30 uppercase tracking-widest mb-1">Occupation</p>
                              <p className="text-sm font-bold text-primary/80">{profile.onboarding_profile.occupation}</p>
                            </div>
                          </div>
                        )}
                      </div>
                      {profile.onboarding_profile?.recommended_notes_style && (
                        <p className="text-[10px] text-white/30 font-mono italic px-1">
                          Notes style: {profile.onboarding_profile.recommended_notes_style}
                        </p>
                      )}
                    </div>
                  )}
                </motion.section>
              )}

              {activeTab === 'Calendar' && (
                <motion.section
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="space-y-6"
                >
                  {/* Hint */}
                  <div className="p-4 bg-indigo-500/5 border border-indigo-500/20 rounded-xl text-[10px] font-mono text-indigo-300/60 leading-relaxed">
                    <p className="mb-1 font-bold text-indigo-300/80 uppercase tracking-widest">How to get your iCal URL</p>
                    <p><span className="text-white/40">Google:</span> Calendar settings → your calendar → <em>Secret address in iCal format</em></p>
                    <p><span className="text-white/40">Outlook:</span> Calendar → Shared calendars → <em>Publish a calendar</em> → copy ICS link</p>
                    <p><span className="text-white/40">ProtonCalendar:</span> Calendar settings → <em>Other calendars</em> → copy link</p>
                    <p><span className="text-white/40">Apple iCloud:</span> iCloud.com → Calendar → share icon → copy URL</p>
                  </div>

                  {/* Connected calendars list */}
                  <div className="space-y-3">
                    <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">
                      Connected_Calendars {calendarProviders.length > 0 && <span className="text-primary">({calendarProviders.length})</span>}
                    </label>
                    {calendarProviders.length === 0 ? (
                      <p className="text-[11px] text-white/20 font-mono italic pl-1">No calendars connected yet.</p>
                    ) : (
                      <div className="space-y-2">
                        {calendarProviders.map((p, i) => (
                          <div key={i} className="flex items-center gap-3 px-4 py-3 bg-black/30 border border-white/5 rounded-xl group">
                            <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: p.color || '#6366f1' }} />
                            <div className="flex-1 min-w-0">
                              <span className="text-xs font-medium text-white/70 truncate block">{p.name || p.type}</span>
                              {p.url && <span className="font-mono text-[9px] text-white/20 truncate block">{p.url}</span>}
                            </div>
                            <span className="font-mono text-[9px] text-white/20 uppercase shrink-0">{p.type}</span>
                            <button
                              onClick={() => setCalendarProviders(calendarProviders.filter((_, j) => j !== i))}
                              className="opacity-0 group-hover:opacity-100 transition-opacity text-red-400/60 hover:text-red-400 p-1 rounded"
                              title="Remove"
                            >
                              <Trash2 size={12} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Add calendar form */}
                  {!showAddCal ? (
                    <button
                      onClick={() => setShowAddCal(true)}
                      className="flex items-center gap-2 px-5 py-3 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-black transition-all active:scale-95"
                    >
                      <Plus size={13} /> Add_Calendar
                    </button>
                  ) : (
                    <div className="space-y-4 p-5 bg-black/30 border border-white/10 rounded-xl">
                      {/* Type selector */}
                      <div className="space-y-2">
                        <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Provider_Type</label>
                        <div className="flex gap-2 flex-wrap">
                          {(['ical', 'google', 'outlook', 'notion'] as const).map(t => (
                            <button
                              key={t}
                              onClick={() => setCalType(t)}
                              className={`px-3 py-1.5 rounded-lg font-mono text-[9px] uppercase tracking-widest font-bold border transition-all ${
                                calType === t
                                  ? 'bg-primary/20 text-primary border-primary/30'
                                  : 'text-white/20 border-white/10 hover:text-white/50'
                              }`}
                            >
                              {t === 'ical' ? 'iCal URL' : t === 'google' ? 'Google' : t === 'outlook' ? 'Outlook' : 'Notion'}
                            </button>
                          ))}
                        </div>
                        {calType !== 'ical' && (
                          <p className="text-[9px] text-amber-400/60 font-mono italic mt-1">
                            {calType === 'google' && 'Requires google-api-python-client. Use iCal URL for quick setup.'}
                            {calType === 'outlook' && 'Requires msal. Use iCal URL from Outlook for quick setup.'}
                            {calType === 'notion' && 'Requires Notion integration token + database ID.'}
                          </p>
                        )}
                      </div>

                      {/* iCal URL field */}
                      {calType === 'ical' && (
                        <div className="space-y-2">
                          <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">iCal_URL</label>
                          <div className="relative">
                            <Link size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/10" />
                            <input
                              type="url"
                              value={calUrl}
                              onChange={e => setCalUrl(e.target.value)}
                              placeholder="https://calendar.google.com/calendar/ical/..."
                              className="w-full bg-black/60 border border-white/10 rounded-xl py-3 pl-10 pr-4 font-mono text-[11px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                            />
                          </div>
                        </div>
                      )}

                      {/* Name + color */}
                      <div className="flex gap-3">
                        <div className="flex-1 space-y-2">
                          <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Display_Name</label>
                          <input
                            type="text"
                            value={calName}
                            onChange={e => setCalName(e.target.value)}
                            placeholder="My Classes"
                            className="w-full bg-black/60 border border-white/10 rounded-xl py-3 px-4 font-mono text-[11px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                          />
                        </div>
                        <div className="space-y-2">
                          <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Color</label>
                          <input
                            type="color"
                            value={calColor}
                            onChange={e => setCalColor(e.target.value)}
                            className="h-[46px] w-14 rounded-xl border border-white/10 bg-black/60 cursor-pointer p-1"
                          />
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex gap-3 pt-1">
                        <button
                          onClick={handleAddCalendar}
                          disabled={calType === 'ical' && !calUrl.trim()}
                          className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-black transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none"
                        >
                          <Plus size={12} /> Add
                        </button>
                        <button
                          onClick={() => { setShowAddCal(false); setCalUrl(''); setCalName(''); }}
                          className="px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest text-white/20 hover:text-white/50 transition-colors"
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </motion.section>
              )}

              {activeTab === 'Backup' && (
                <motion.section
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="space-y-6"
                >
                  {/* Status banner */}
                  {cloudBackupInfo?.enabled ? (
                    <div className="flex items-center gap-3 p-4 rounded-xl bg-emerald-500/5 border border-emerald-500/20">
                      <CheckCircle size={14} className="text-emerald-400 shrink-0" />
                      <div className="flex-1 min-w-0">
                        <p className="font-mono text-[10px] text-emerald-300 uppercase tracking-widest font-bold">Cloud_Backup_Active</p>
                        <p className="text-[10px] text-white/30 font-mono mt-0.5">
                          Provider: <span className="text-white/50">{cloudBackupInfo.provider}</span>
                          {cloudBackupInfo.last_sync && <> · Last sync: <span className="text-white/50">{new Date(cloudBackupInfo.last_sync).toLocaleString()}</span></>}
                          {cloudBackupInfo.key_unlocked && <> · Key_Unlocked</>}
                        </p>
                      </div>
                      <button
                        onClick={disableCloudBackup}
                        className="shrink-0 font-mono text-[9px] text-red-400/50 hover:text-red-400 uppercase tracking-widest transition-colors"
                      >
                        Disable
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-start gap-3 p-4 rounded-xl bg-amber-500/5 border border-amber-500/20">
                      <AlertTriangle size={14} className="text-amber-400 shrink-0 mt-0.5" />
                      <div>
                        <p className="font-mono text-[10px] text-amber-300 uppercase tracking-widest font-bold">Cloud_Backup_Not_Configured</p>
                        <p className="text-[10px] text-white/30 mt-0.5">
                          Your data is only saved locally. Set up cloud backup to protect against data loss.
                        </p>
                      </div>
                    </div>
                  )}

                  {/* Op message */}
                  {cloudOpMsg && (
                    <p className={`text-[11px] font-mono px-1 ${cloudBackupOp === 'error' ? 'text-red-400' : 'text-emerald-400'}`}>
                      {cloudOpMsg}
                    </p>
                  )}

                  {/* Backup Now + Test Connection (when configured) */}
                  {cloudBackupInfo?.enabled && !showSetup && (
                    <div className="flex items-center gap-3 flex-wrap">
                      <button
                        onClick={runCloudBackupNow}
                        disabled={cloudBackupOp === 'running'}
                        className={`flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold transition-all active:scale-95 border ${
                          cloudBackupOp === 'done'    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' :
                          cloudBackupOp === 'error'   ? 'bg-red-500/20 text-red-400 border-red-500/30' :
                          cloudBackupOp === 'running' ? 'bg-white/5 text-white/30 border-white/10' :
                          'bg-primary/10 text-primary border-primary/20 hover:bg-primary hover:text-black'
                        }`}
                      >
                        <Cloud size={13} />
                        {cloudBackupOp === 'running' ? 'Uploading…' : cloudBackupOp === 'done' ? 'Done ✓' : 'Backup_Now'}
                      </button>
                      <button
                        onClick={() => setShowSetup(true)}
                        className="px-4 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest text-white/25 hover:text-white/60 border border-white/5 hover:border-white/20 transition-all"
                      >
                        Reconfigure
                      </button>
                    </div>
                  )}

                  {/* Setup panel */}
                  {(!cloudBackupInfo?.enabled || showSetup) && (
                    <div className="space-y-5 p-5 bg-black/30 border border-white/10 rounded-xl">
                      <p className="font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">
                        {showSetup ? 'Reconfigure_Backup' : 'Setup_Cloud_Backup'}
                      </p>

                      {/* Mnemonic */}
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Seed_Phrase (12 words)</label>
                          <a
                            href="https://seed.primnox.com"
                            target="_blank"
                            rel="noopener noreferrer"
                            className="font-mono text-[9px] text-primary/60 hover:text-primary transition-colors uppercase tracking-widest"
                          >
                            Get phrase at seed.primnox.com ↗
                          </a>
                        </div>
                        <div className="relative">
                          <Key size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/10 pointer-events-none" />
                          <input
                            type={showMnemonic ? 'text' : 'password'}
                            value={mnemonic}
                            onChange={e => setMnemonic(e.target.value)}
                            placeholder="word1 word2 word3 … word12"
                            className="w-full bg-black/60 border border-white/10 rounded-xl py-3 pl-10 pr-20 font-mono text-[11px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                          />
                          <div className="absolute right-3 top-1/2 -translate-y-1/2 flex items-center gap-2">
                            <button type="button" onClick={() => setShowMnemonic(v => !v)} className="text-white/20 hover:text-white/60 transition-colors">
                              {showMnemonic ? <EyeOff size={13} /> : <Eye size={13} />}
                            </button>
                            {mnemonic && (
                              <button type="button" onClick={() => navigator.clipboard.writeText(mnemonic)} className="text-white/20 hover:text-primary transition-colors" title="Copy">
                                <Copy size={13} />
                              </button>
                            )}
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          <button
                            type="button"
                            onClick={generateMnemonic}
                            disabled={mnemonicGenLoading}
                            className="flex items-center gap-2 px-4 py-2 rounded-xl font-mono text-[9px] uppercase tracking-widest bg-white/5 text-white/30 border border-white/10 hover:text-white/60 hover:bg-white/10 transition-all active:scale-95 disabled:opacity-40"
                          >
                            <RefreshCw size={11} className={mnemonicGenLoading ? 'animate-spin' : ''} />
                            Generate New Phrase
                          </button>
                          <p className="text-[9px] text-white/20 font-mono italic">
                            Write it down — it cannot be recovered.
                          </p>
                        </div>
                      </div>

                      {/* Provider selector */}
                      <div className="space-y-3">
                        <label className="font-mono text-[9px] text-white/20 uppercase tracking-widest">Storage_Provider</label>
                        <div className="flex gap-2 flex-wrap">
                          {(['s3', 'gdrive', 'dropbox', 'https'] as const).map(t => (
                            <button key={t} type="button" onClick={() => setProviderType(t)}
                              className={`px-3 py-1.5 rounded-lg font-mono text-[9px] uppercase tracking-widest font-bold border transition-all ${
                                providerType === t ? 'bg-primary/20 text-primary border-primary/30' : 'text-white/20 border-white/10 hover:text-white/50'
                              }`}
                            >
                              {t === 's3' ? 'S3 / B2 / R2' : t === 'gdrive' ? 'Google Drive' : t === 'dropbox' ? 'Dropbox' : 'Self-Hosted'}
                            </button>
                          ))}
                        </div>
                        {(providerType === 'gdrive' || providerType === 'dropbox') && (
                          <p className="text-[9px] text-amber-400/60 font-mono italic">
                            {providerType === 'gdrive' ? 'Requires google-api-python-client. Use OAuth token from Google Cloud Console.' : 'Requires Dropbox SDK. Coming soon — use S3 or self-hosted for now.'}
                          </p>
                        )}
                      </div>

                      {/* S3 config */}
                      {providerType === 's3' && (
                        <div className="grid grid-cols-2 gap-3">
                          {[
                            { key: 'bucket',       label: 'Bucket Name',    placeholder: 'my-primnox-backup', pw: false },
                            { key: 'endpoint_url', label: 'Endpoint URL',   placeholder: 'https://s3.wasabisys.com (blank for AWS)', pw: false },
                            { key: 'region',       label: 'Region',         placeholder: 'us-east-1', pw: false },
                            { key: 'access_key',   label: 'Access Key ID',  placeholder: 'AKIAIOSFODNN7EXAMPLE', pw: false },
                            { key: 'secret_key',   label: 'Secret Key',     placeholder: '••••••••', pw: true },
                          ].map(({ key, label, placeholder, pw }) => (
                            <div key={key} className={`space-y-1 ${key === 'endpoint_url' || key === 'secret_key' ? 'col-span-2' : ''}`}>
                              <label className="font-mono text-[8px] text-white/20 uppercase tracking-widest">{label}</label>
                              <input
                                type={pw ? 'password' : 'text'}
                                value={(s3Cfg as any)[key]}
                                onChange={e => setS3Cfg(c => ({ ...c, [key]: e.target.value }))}
                                placeholder={placeholder}
                                className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[10px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                              />
                            </div>
                          ))}
                        </div>
                      )}

                      {/* HTTPS config */}
                      {providerType === 'https' && (
                        <div className="space-y-3">
                          <div className="space-y-1">
                            <label className="font-mono text-[8px] text-white/20 uppercase tracking-widest">Server URL</label>
                            <input
                              type="url" value={httpsCfg.url}
                              onChange={e => setHttpsCfg(c => ({ ...c, url: e.target.value }))}
                              placeholder="https://myserver.com/primnox-backup"
                              className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[10px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                            />
                          </div>
                          <div className="space-y-1">
                            <label className="font-mono text-[8px] text-white/20 uppercase tracking-widest">Auth Header (optional)</label>
                            <input
                              type="password" value={httpsCfg.auth_header}
                              onChange={e => setHttpsCfg(c => ({ ...c, auth_header: e.target.value }))}
                              placeholder="Bearer your-token"
                              className="w-full bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[10px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                            />
                          </div>
                        </div>
                      )}

                      <div className="space-y-1">
                        <label className="font-mono text-[8px] text-white/20 uppercase tracking-widest">Backup Every (hours)</label>
                        <input
                          type="number" min={1} max={168} value={backupInterval}
                          onChange={e => setBackupInterval(Math.max(1, parseInt(e.target.value) || 24))}
                          className="w-24 bg-black/60 border border-white/10 rounded-lg py-2 px-3 font-mono text-[10px] focus:ring-1 focus:ring-primary outline-none"
                        />
                      </div>

                      <div className="flex gap-3 pt-1">
                        <button
                          type="button"
                          onClick={setupCloudBackup}
                          disabled={!mnemonic.trim() || cloudBackupOp === 'running' || providerType === 'gdrive' || providerType === 'dropbox'}
                          className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold bg-primary/10 text-primary border border-primary/20 hover:bg-primary hover:text-black transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none"
                        >
                          {cloudBackupOp === 'running' ? <RefreshCw size={12} className="animate-spin" /> : <HardDrive size={12} />}
                          {cloudBackupOp === 'running' ? 'Saving…' : 'Save_Setup'}
                        </button>
                        {showSetup && (
                          <button type="button" onClick={() => setShowSetup(false)}
                            className="px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest text-white/20 hover:text-white/50 transition-colors"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Backup list */}
                  {cloudBackupInfo?.enabled && cloudBackupList.length > 0 && (
                    <div className="space-y-3">
                      <label className="block font-mono text-[10px] text-white/20 uppercase tracking-[0.5em] font-bold">
                        Remote_Backups <span className="text-primary">({cloudBackupList.length})</span>
                      </label>
                      <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                        {cloudBackupList.map((b: any) => (
                          <div key={b.name} className="flex items-center gap-3 px-4 py-3 bg-black/30 border border-white/5 rounded-xl group">
                            <HardDrive size={12} className="text-white/20 shrink-0" />
                            <div className="flex-1 min-w-0">
                              <span className="font-mono text-[10px] text-white/60 truncate block">{b.name}</span>
                              <span className="font-mono text-[9px] text-white/20">
                                {b.timestamp ? new Date(b.timestamp).toLocaleString() : ''}
                                {b.size ? ` · ${Math.ceil(b.size / 1024)} KB` : ''}
                              </span>
                            </div>
                            <button
                              type="button"
                              onClick={() => { setRestoreFile(b.name); }}
                              className="opacity-0 group-hover:opacity-100 transition-opacity font-mono text-[9px] text-primary/60 hover:text-primary uppercase tracking-widest"
                            >
                              Restore
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Restore panel */}
                  {cloudBackupInfo?.enabled && restoreFile && (
                    <div className="space-y-4 p-5 bg-red-500/5 border border-red-500/20 rounded-xl">
                      <p className="font-mono text-[10px] text-red-300 uppercase tracking-widest font-bold">Restore_From_Backup</p>
                      <p className="text-[10px] text-white/30 font-mono">
                        Restoring <span className="text-white/60">{restoreFile}</span> will overwrite current data. Enter your seed phrase to decrypt.
                      </p>
                      <div className="relative">
                        <Key size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/10 pointer-events-none" />
                        <input
                          type={showRestoreMnemonic ? 'text' : 'password'}
                          value={restoreMnemonic}
                          onChange={e => setRestoreMnemonic(e.target.value)}
                          placeholder="Enter your 12-word seed phrase…"
                          className="w-full bg-black/60 border border-red-500/20 rounded-xl py-3 pl-10 pr-10 font-mono text-[11px] focus:ring-1 focus:ring-red-500 outline-none placeholder-white/10"
                        />
                        <button type="button" onClick={() => setShowRestoreMnemonic(v => !v)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/60 transition-colors">
                          {showRestoreMnemonic ? <EyeOff size={13} /> : <Eye size={13} />}
                        </button>
                      </div>
                      <div className="flex gap-3">
                        <button
                          type="button"
                          onClick={runCloudRestore}
                          disabled={!restoreMnemonic.trim() || cloudBackupOp === 'running'}
                          className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold bg-red-500/10 text-red-400 border border-red-500/20 hover:bg-red-500/20 transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none"
                        >
                          {cloudBackupOp === 'running' ? <RefreshCw size={12} className="animate-spin" /> : null}
                          {cloudBackupOp === 'running' ? 'Restoring…' : 'Confirm_Restore'}
                        </button>
                        <button type="button" onClick={() => { setRestoreFile(''); setRestoreMnemonic(''); }}
                          className="px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest text-white/20 hover:text-white/50 transition-colors">
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Import a .prx backup from disk — works with no cloud provider configured */}
                  <div className="space-y-4 p-5 bg-black/30 border border-white/10 rounded-xl">
                    <p className="font-mono text-[10px] text-white/50 uppercase tracking-widest font-bold">Import_From_File</p>
                    <p className="text-[10px] text-white/30 font-mono leading-5">
                      Restore from a <span className="text-white/50">.prx</span> backup on disk — no cloud setup needed, just the file and your seed phrase. Overwrites current data.
                    </p>
                    <label className="flex items-center gap-3 px-4 py-3 bg-black/40 border border-white/10 rounded-xl cursor-pointer hover:border-primary/30 transition-colors">
                      <DownloadCloud size={14} className="text-white/30 shrink-0" />
                      <span className="font-mono text-[11px] text-white/60 truncate">
                        {importFile ? importFile.name : 'Choose a .prx backup file…'}
                      </span>
                      <input
                        type="file"
                        accept=".prx"
                        className="hidden"
                        onChange={e => { setImportFile(e.target.files?.[0] || null); setImportOp('idle'); setImportMsg(''); }}
                      />
                    </label>
                    <div className="relative">
                      <Key size={13} className="absolute left-4 top-1/2 -translate-y-1/2 text-white/10 pointer-events-none" />
                      <input
                        type={showImportMnemonic ? 'text' : 'password'}
                        value={importMnemonic}
                        onChange={e => setImportMnemonic(e.target.value)}
                        placeholder="Enter the seed phrase for this backup…"
                        className="w-full bg-black/60 border border-white/10 rounded-xl py-3 pl-10 pr-10 font-mono text-[11px] focus:ring-1 focus:ring-primary outline-none placeholder-white/10"
                      />
                      <button type="button" onClick={() => setShowImportMnemonic(v => !v)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-white/20 hover:text-white/60 transition-colors">
                        {showImportMnemonic ? <EyeOff size={13} /> : <Eye size={13} />}
                      </button>
                    </div>
                    {importMsg && (
                      <p className={`text-[10px] font-mono ${importOp === 'error' ? 'text-red-400' : importOp === 'done' ? 'text-green-400' : 'text-white/40'}`}>
                        {importMsg}
                      </p>
                    )}
                    <button
                      type="button"
                      onClick={runImport}
                      disabled={!importFile || !importMnemonic.trim() || importOp === 'running'}
                      className="flex items-center gap-2 px-5 py-2.5 rounded-xl font-mono text-[10px] uppercase tracking-widest font-bold bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-all active:scale-95 disabled:opacity-30 disabled:pointer-events-none"
                    >
                      {importOp === 'running' ? <RefreshCw size={12} className="animate-spin" /> : null}
                      {importOp === 'running' ? 'Importing…' : importOp === 'done' ? 'Imported ✓' : 'Import_Backup'}
                    </button>
                  </div>
                </motion.section>
              )}
            </div>
          </div>

          <div className="flex items-center justify-between pt-5 border-t border-white/5 pb-2">
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
