/**
 * Settings — rebuilt in the website's design language.
 *
 * The previous version was a single 1,625-line component: every control styled
 * inline, `${API_BASE}` written out at 19 call sites, and a floating
 * `max-h-[calc(100vh-4rem)]` panel that was taller than the region it lived in,
 * which pushed the first tab behind the header where it could not be clicked.
 *
 * This is a full-height page, not a floating card, so it cannot mis-size itself
 * again. Controls come from ./settings/primitives; the backend origin comes from
 * ./settings/api. Every setting the old screen exposed is still here.
 */
import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import {
  User, Shield, Cpu, Calendar, Cloud, Plus, Trash2, RefreshCw,
  Check, AlertTriangle, Copy, Eye, EyeOff, HardDrive, Brain,
} from 'lucide-react';
import { FlowLocal, FlowCloud, FlowRaw } from './FlowDiagram';
import { useTheme } from '../hooks/useTheme';
import { getJson, postJson, apiUrl } from './settings/api';
import {
  Section, Row, Toggle, Field, SecretField, Select, Slider, Button, Choice, Status,
} from './settings/primitives';

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

const CLOUD_MODELS = ['Groq_Llama_3', 'OpenAI_GPT_4o', 'Anthropic_Claude_3', 'Gemini_Flash'];

const CLOUD_MODEL_OPTIONS = [
  { value: 'Groq_Llama_3',       label: 'Groq — Llama 3.3 70B (HyperSpeed)' },
  { value: 'OpenAI_GPT_4o',      label: 'OpenAI — GPT-4o' },
  { value: 'Anthropic_Claude_3', label: 'Anthropic — Claude 3' },
  { value: 'Gemini_Flash',       label: 'Google — Gemini Flash' },
];

/** The stored settings do not carry an "architecture" field — it is implied by
 *  which model is active, whether a cloud key exists, and whether the mirror is
 *  on. This reconstructs it so the selector shows the real current state. */
const deriveArch = (
  model: string,
  mirror: boolean,
  key: string
): 'local' | 'hybrid' | 'cloud_shield' | 'cloud_raw' => {
  if (model === 'Ollama_Local' || model === 'LlamaCpp_Local')
    return key ? 'hybrid' : 'local';
  return mirror ? 'cloud_shield' : 'cloud_raw';
};

const TABS = [
  { id: 'System_Core', icon: Cpu },
  { id: 'Identity',    icon: User },
  { id: 'Security',    icon: Shield },
  { id: 'Calendar',    icon: Calendar },
  { id: 'Backup',      icon: Cloud },
] as const;

type TabId = typeof TABS[number]['id'];

export const IslandSettings = ({
  operatorAlias, setOperatorAlias,
  aiCodename, setAiCodename,
  activeModel, setActiveModel,
  apiKey, setApiKey,
  openaiApiKey, setOpenaiApiKey,
  anthropicApiKey, setAnthropicApiKey,
  vadSensitivity, setVadSensitivity,
  wakeWord, setWakeWord,
  wakeWordEnabled, setWakeWordEnabled,
  dynamicIslandEnabled, setDynamicIslandEnabled,
  privacyMirrorEnabled, setPrivacyMirrorEnabled,
  ollamaModel, setOllamaModel,
  ollamaBaseUrl, setOllamaBaseUrl,
  llamacppBaseUrl, setLlamacppBaseUrl,
  llamacppModel, setLlamacppModel,
  geminiApiKey, setGeminiApiKey,
  calendarProviders, setCalendarProviders,
  meetingRetentionDays, setMeetingRetentionDays,
  onSync,
}: {
  onNavigate: (id: ScreenId) => void,
  operatorAlias: string, setOperatorAlias: (v: string) => void,
  aiCodename: string, setAiCodename: (v: string) => void,
  activeModel: string, setActiveModel: (v: string) => void,
  apiKey: string, setApiKey: (v: string) => void,
  openaiApiKey: string, setOpenaiApiKey: (v: string) => void,
  anthropicApiKey: string, setAnthropicApiKey: (v: string) => void,
  vadSensitivity: number, setVadSensitivity: (v: number) => void,
  wakeWord: string, setWakeWord: (v: string) => void,
  wakeWordEnabled: boolean, setWakeWordEnabled: (v: boolean) => void,
  dynamicIslandEnabled: boolean, setDynamicIslandEnabled: (v: boolean) => void,
  privacyMirrorEnabled: boolean, setPrivacyMirrorEnabled: (v: boolean) => void,
  ollamaModel: string, setOllamaModel: (v: string) => void,
  ollamaBaseUrl: string, setOllamaBaseUrl: (v: string) => void,
  llamacppBaseUrl: string, setLlamacppBaseUrl: (v: string) => void,
  llamacppModel: string, setLlamacppModel: (v: string) => void,
  geminiApiKey: string, setGeminiApiKey: (v: string) => void,
  calendarProviders: any[], setCalendarProviders: (v: any[]) => void,
  meetingRetentionDays: number, setMeetingRetentionDays: (v: number) => void,
  onSync: () => void
}) => {
  const [activeTab, setActiveTab] = useState<TabId>('System_Core');
  const { theme, setTheme, themes } = useTheme();

  // ── Engine / architecture ───────────────────────────────────────────────
  const [archMode, setArchMode] = useState(() => deriveArch(activeModel, privacyMirrorEnabled, apiKey));
  const [localEngine, setLocalEngine] = useState<'ollama' | 'llamacpp'>(
    activeModel === 'LlamaCpp_Local' ? 'llamacpp' : 'ollama'
  );
  const [cloudModel, setCloudModel] = useState(
    () => CLOUD_MODELS.includes(activeModel) ? activeModel : 'Groq_Llama_3'
  );
  const [ollamaStatus, setOllamaStatus] = useState<{ running: boolean, models: string[] } | null>(null);
  const [checkingOllama, setCheckingOllama] = useState(false);

  // Re-sync once the parent finishes its async settings load — the lazy
  // initialisers above may have run while activeModel was still the default.
  useEffect(() => {
    setArchMode(deriveArch(activeModel, privacyMirrorEnabled, apiKey));
    setLocalEngine(activeModel === 'LlamaCpp_Local' ? 'llamacpp' : 'ollama');
    if (CLOUD_MODELS.includes(activeModel)) setCloudModel(activeModel);
  }, [activeModel, privacyMirrorEnabled, apiKey]);

  const checkOllama = async () => {
    setCheckingOllama(true);
    // A non-2xx (503 while the backend boots) must resolve to "not running",
    // otherwise the indicator sticks on "checking" forever.
    const d = await getJson<{ running: boolean, models: string[] }>('/api/ollama/status');
    setOllamaStatus(d ?? { running: false, models: [] });
    setCheckingOllama(false);
  };
  useEffect(() => { if (activeModel === 'Ollama_Local') checkOllama(); }, [activeModel]);

  // ── Security tab state ──────────────────────────────────────────────────
  const [piiModelStatus, setPiiModelStatus] = useState<string | null>(null);
  const [profile, setProfile] = useState<any>(null);
  const [vaultStatus, setVaultStatus] = useState<{ enabled: boolean, locked: boolean } | null>(null);
  const [vaultMnemonic, setVaultMnemonic] = useState('');
  const [vaultMnemonicGenerated, setVaultMnemonicGenerated] = useState('');
  const [vaultOp, setVaultOp] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [vaultOpMsg, setVaultOpMsg] = useState('');
  const [vaultPhrase, setVaultPhrase] = useState<string | null>(null);
  const [showPhrase, setShowPhrase] = useState(false);

  useEffect(() => {
    if (activeTab !== 'Security') return;
    getJson<any>('/api/status', 4000).then(d => setPiiModelStatus(d?.pii_model_status ?? null));
    getJson<any>('/api/vault/status').then(d => { if (d) setVaultStatus(d); });
  }, [activeTab]);

  useEffect(() => { getJson<any>('/api/profile').then(d => d && setProfile(d)); }, []);

  const enableVault = async () => {
    setVaultOp('running'); setVaultOpMsg(''); setVaultMnemonicGenerated('');
    const d = await postJson<any>('/api/vault/setup');
    if (d) {
      setVaultOp('done'); setVaultOpMsg('Vault enabled.');
      setVaultMnemonicGenerated(d.mnemonic);
      setVaultStatus({ enabled: true, locked: false });
    } else { setVaultOp('error'); setVaultOpMsg('Failed to enable vault'); }
  };

  const unlockVault = async () => {
    if (!vaultMnemonic.trim()) return;
    setVaultOp('running'); setVaultOpMsg('');
    const d = await postJson<any>('/api/vault/unlock', { mnemonic: vaultMnemonic.trim() });
    if (d) {
      setVaultOp('done'); setVaultOpMsg('Vault unlocked.');
      setVaultStatus({ enabled: true, locked: false });
      setVaultMnemonic('');
      setTimeout(() => setVaultOp('idle'), 4000);
    } else { setVaultOp('error'); setVaultOpMsg('Unlock failed'); }
  };

  const disableVault = async () => {
    setVaultOp('running'); setVaultOpMsg('');
    const d = await postJson<any>('/api/vault/disable');
    if (d) {
      setVaultOp('done'); setVaultOpMsg('Vault disabled and fully decrypted.');
      setVaultStatus({ enabled: false, locked: false });
      setVaultMnemonicGenerated(''); setVaultPhrase(null); setShowPhrase(false);
    } else { setVaultOp('error'); setVaultOpMsg('Failed to disable vault'); }
    setTimeout(() => { setVaultOp('idle'); setVaultOpMsg(''); }, 4000);
  };

  /** The phrase is behind a one-shot token so it is never sitting on a plain
   *  GET that anything on localhost could read. */
  const fetchVaultPhrase = async () => {
    const tok = await postJson<{ token: string }>('/api/vault/phrase-token');
    if (!tok?.token) {
      setVaultOpMsg('Could not issue phrase token — vault may be locked.');
      return;
    }
    try {
      const res = await fetch(apiUrl('/api/vault/phrase'), { headers: { 'X-Vault-Token': tok.token } });
      if (!res.ok) throw new Error('not found');
      const data = await res.json();
      setVaultPhrase(data.phrase); setShowPhrase(true);
    } catch {
      setVaultPhrase(null);
      setVaultOpMsg('Recovery phrase not available. Re-enable the vault to generate a new one.');
    }
  };

  // ── Calendar tab state ──────────────────────────────────────────────────
  const [showAddCal, setShowAddCal] = useState(false);
  const [calType, setCalType] = useState<'ical' | 'google' | 'outlook' | 'notion'>('ical');
  const [calUrl, setCalUrl] = useState('');
  const [calName, setCalName] = useState('');
  const [calColor, setCalColor] = useState('#6366f1');

  const handleAddCalendar = () => {
    if (!calUrl.trim() && calType === 'ical') return;
    const provider: any = { type: calType, name: calName || calType, color: calColor };
    if (calType === 'ical') provider.url = calUrl.trim();
    setCalendarProviders([...calendarProviders, provider]);
    setCalUrl(''); setCalName(''); setCalColor('#6366f1'); setShowAddCal(false);
  };

  // ── Backup tab state ────────────────────────────────────────────────────
  const [backupStatus, setBackupStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [cloudBackupInfo, setCloudBackupInfo] = useState<any>(null);
  const [cloudBackupList, setCloudBackupList] = useState<any[]>([]);
  const [cloudBackupOp, setCloudBackupOp] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [cloudOpMsg, setCloudOpMsg] = useState('');
  const [showSetup, setShowSetup] = useState(false);
  const [mnemonic, setMnemonic] = useState('');
  const [showMnemonic, setShowMnemonic] = useState(false);
  const [mnemonicGenLoading, setMnemonicGenLoading] = useState(false);
  const [providerType, setProviderType] = useState<'s3' | 'gdrive' | 'dropbox' | 'https'>('s3');
  const [backupInterval, setBackupInterval] = useState(24);
  const [s3Cfg, setS3Cfg] = useState({ bucket: '', endpoint_url: '', region: 'us-east-1', access_key: '', secret_key: '' });
  const [httpsCfg, setHttpsCfg] = useState({ url: '', auth_header: '' });
  const [restoreFile, setRestoreFile] = useState('');
  const [restoreMnemonic, setRestoreMnemonic] = useState('');
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importMnemonic, setImportMnemonic] = useState('');
  const [importOp, setImportOp] = useState<'idle' | 'running' | 'done' | 'error'>('idle');
  const [importMsg, setImportMsg] = useState('');

  useEffect(() => {
    if (activeTab !== 'Backup') return;
    getJson<any>('/api/backup/status').then(d => { if (d) setCloudBackupInfo(d); });
    getJson<any>('/api/backup/list').then(d => { if (d?.backups) setCloudBackupList(d.backups); });
  }, [activeTab]);

  const triggerBackup = async () => {
    setBackupStatus('running');
    const d = await postJson('/api/backup');
    setBackupStatus(d ? 'done' : 'error');
    setTimeout(() => setBackupStatus('idle'), 4000);
  };

  const generateMnemonic = async () => {
    setMnemonicGenLoading(true);
    const d = await postJson<any>('/api/backup/generate-mnemonic');
    if (d?.mnemonic) { setMnemonic(d.mnemonic); setShowMnemonic(true); }
    else setCloudOpMsg('Failed to generate phrase');
    setMnemonicGenLoading(false);
  };

  const setupCloudBackup = async () => {
    if (!mnemonic.trim()) return;
    const cfg = providerType === 's3' ? s3Cfg : providerType === 'https' ? httpsCfg : {};
    setCloudBackupOp('running'); setCloudOpMsg('');
    const d = await postJson<any>('/api/backup/setup', {
      mnemonic: mnemonic.trim(), provider: providerType,
      provider_config: cfg, interval_hours: backupInterval,
    });
    if (d) {
      setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Backup configured');
      setShowSetup(false);
      const st = await getJson<any>('/api/backup/status');   // best-effort refresh
      if (st) setCloudBackupInfo(st);
    } else { setCloudBackupOp('error'); setCloudOpMsg('Setup failed'); }
    setTimeout(() => setCloudBackupOp('idle'), 4000);
  };

  const runCloudBackupNow = async () => {
    setCloudBackupOp('running'); setCloudOpMsg('');
    const d = await postJson<any>('/api/backup/now', {});
    if (d) { setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Backup started'); }
    else { setCloudBackupOp('error'); setCloudOpMsg('Backup failed'); }
    setTimeout(() => { setCloudBackupOp('idle'); setCloudOpMsg(''); }, 5000);
  };

  const runCloudRestore = async () => {
    if (!restoreFile || !restoreMnemonic.trim()) return;
    setCloudBackupOp('running'); setCloudOpMsg('Restoring…');
    const d = await postJson<any>('/api/backup/restore', {
      filename: restoreFile, mnemonic: restoreMnemonic.trim(),
    }, 60000);
    if (d) { setCloudBackupOp('done'); setCloudOpMsg(d.message || 'Restore complete — restart Primnox'); }
    else { setCloudBackupOp('error'); setCloudOpMsg('Restore failed'); }
    setTimeout(() => { setCloudBackupOp('idle'); setCloudOpMsg(''); }, 6000);
  };

  /** Multipart, so it does not go through postJson. */
  const runImport = async () => {
    if (!importFile || !importMnemonic.trim()) return;
    setImportOp('running'); setImportMsg('Decrypting & restoring…');
    try {
      const fd = new FormData();
      fd.append('file', importFile);
      fd.append('mnemonic', importMnemonic.trim());
      const r = await fetch(apiUrl('/api/backup/import'), { method: 'POST', body: fd });
      const d = await r.json();
      if (r.ok) { setImportOp('done'); setImportMsg(d.message || 'Import complete — restart Primnox'); }
      else { setImportOp('error'); setImportMsg(d.detail || 'Import failed'); }
    } catch { setImportOp('error'); setImportMsg('Backend unavailable'); }
  };

  const disableCloudBackup = async () => {
    await postJson('/api/backup/disable');
    setCloudBackupInfo(null); setShowSetup(false); setMnemonic('');
  };

  const purgeData = async () => {
    await postJson('/api/cleanup');
  };

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex overflow-hidden bg-surface text-on-surface">

      {/* Tab rail — mono labels and a hairline divider, matching the app sidebar */}
      <div className="w-[210px] shrink-0 border-r border-on-surface/10 flex flex-col overflow-y-auto">
        <nav className="flex-1 py-8">
          {TABS.map(({ id, icon: Icon }) => {
            const active = activeTab === id;
            return (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`w-full flex items-center gap-3 px-7 py-3.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-all duration-300 border-l-2 ${
                  active
                    ? 'border-primary text-on-surface bg-[var(--p-faint)]'
                    : 'border-transparent text-on-surface/60 hover:text-on-surface hover:bg-[var(--hover)]'
                }`}
              >
                <Icon size={14} className="shrink-0" />
                {id}
              </button>
            );
          })}
        </nav>

        <div className="p-6 border-t border-on-surface/10">
          <div className="flex items-center gap-2 mb-2">
            <span className="w-[6px] h-[6px] rounded-full bg-[var(--green)] animate-pulse shrink-0" />
            <Status tone="good">Kernel_Stable</Status>
          </div>
          <p className="font-mono text-[9px] uppercase tracking-[0.1em] text-on-surface/58 break-all leading-relaxed">
            {activeModel}
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
            className="max-w-[760px] px-12 py-10"
          >
            {/* ── SYSTEM CORE ─────────────────────────────────────────── */}
            {activeTab === 'System_Core' && (
              <>
                <Section index="01" title="Appearance">
                  <Row label="Theme" hint="Ported from primnox.github.io — the app and the site share one palette set." stack>
                    <div className="grid grid-cols-5 gap-2.5 mt-1">
                      {themes.map(t => (
                        <button
                          key={t.id}
                          onClick={() => setTheme(t.id)}
                          title={t.label}
                          className={`group relative p-2 border transition-all ${
                            theme === t.id
                              ? 'border-[var(--p-line-2)] bg-[var(--p-fill)]'
                              : 'border-on-surface/10 hover:border-on-surface/30'
                          }`}
                        >
                          {/* Swatches read the palette's real values, so a retuned
                              theme updates its own preview. */}
                          <span className="flex h-6 rounded-sm overflow-hidden mb-1.5">
                            {t.swatch.map((c, i) => (
                              <span key={i} className="flex-1" style={{ background: c }} />
                            ))}
                          </span>
                          <span className={`block font-mono text-[8px] uppercase tracking-[0.1em] text-center ${
                            theme === t.id ? 'text-primary' : 'text-on-surface/45'
                          }`}>{t.label}</span>
                          {theme === t.id && (
                            <Check size={10} className="absolute top-1 right-1 text-primary" />
                          )}
                        </button>
                      ))}
                    </div>
                  </Row>
                </Section>

                <Section index="02" title="Intelligence">
                  <Row label="Privacy architecture" hint="Where your text is processed, and what leaves this machine." stack>
                    <div className="grid grid-cols-2 gap-2.5">
                      <Choice
                        selected={archMode === 'local'}
                        onClick={() => { setArchMode('local'); setActiveModel(localEngine === 'llamacpp' ? 'LlamaCpp_Local' : 'Ollama_Local'); }}
                        icon={<HardDrive size={12} />}
                        title="Local"
                        hint="Nothing leaves your machine. Ollama or llama.cpp only."
                      />
                      <Choice
                        selected={archMode === 'hybrid'}
                        onClick={() => { setArchMode('hybrid'); setActiveModel(localEngine === 'llamacpp' ? 'LlamaCpp_Local' : 'Ollama_Local'); }}
                        icon={<Cpu size={12} />}
                        title="Hybrid"
                        hint="Local model for chat. Cloud transcription for voice."
                      />
                      <Choice
                        selected={archMode === 'cloud_shield'}
                        onClick={() => { setArchMode('cloud_shield'); setActiveModel(cloudModel); setPrivacyMirrorEnabled(true); }}
                        icon={<Shield size={12} />}
                        title="Cloud + Mirror"
                        hint="Cloud model with PII scrubbed before it leaves this machine."
                      />
                      <Choice
                        selected={archMode === 'cloud_raw'}
                        onClick={() => { setArchMode('cloud_raw'); setActiveModel(cloudModel); setPrivacyMirrorEnabled(false); }}
                        icon={<Cloud size={12} />}
                        title="Cloud Raw"
                        hint="Cloud model, no scrubbing. Data reaches the provider as-is."
                      />
                    </div>

                    {/* What the chosen route actually does with your text. */}
                    <div className="mt-5 p-5 border border-on-surface/10 bg-[var(--hover)]">
                      {archMode === 'local' || archMode === 'hybrid'
                        ? <FlowLocal />
                        : archMode === 'cloud_shield' ? <FlowCloud /> : <FlowRaw />}
                    </div>
                  </Row>

                  {(archMode === 'local' || archMode === 'hybrid') && (
                    <>
                      <Row label="Local engine" hint="Which local runtime serves the model.">
                        <div className="flex gap-2">
                          <Button
                            variant={localEngine === 'ollama' ? 'solid' : 'ghost'}
                            onClick={() => { setLocalEngine('ollama'); setActiveModel('Ollama_Local'); }}
                          >Ollama</Button>
                          <Button
                            variant={localEngine === 'llamacpp' ? 'solid' : 'ghost'}
                            onClick={() => { setLocalEngine('llamacpp'); setActiveModel('LlamaCpp_Local'); }}
                          >llama.cpp</Button>
                        </div>
                      </Row>

                      {localEngine === 'ollama' ? (
                        <>
                          <Row label="Ollama URL" stack>
                            <Field value={ollamaBaseUrl} onChange={setOllamaBaseUrl} mono placeholder="http://localhost:11434" />
                          </Row>
                          <Row label="Ollama model" stack>
                            <Field value={ollamaModel} onChange={setOllamaModel} mono placeholder="llama3.2" />
                          </Row>
                          <Row label="Engine status" hint="Checks whether the Ollama daemon is reachable.">
                            <div className="flex items-center gap-3">
                              {ollamaStatus && (
                                <Status tone={ollamaStatus.running ? 'good' : 'bad'}>
                                  {ollamaStatus.running
                                    ? `Online · ${ollamaStatus.models.length} models`
                                    : 'Offline'}
                                </Status>
                              )}
                              <Button onClick={checkOllama} disabled={checkingOllama}>
                                <RefreshCw size={11} className={`inline mr-2 ${checkingOllama ? 'animate-spin' : ''}`} />
                                {checkingOllama ? 'Checking' : 'Check'}
                              </Button>
                            </div>
                          </Row>
                        </>
                      ) : (
                        <>
                          <Row label="llama.cpp URL" stack>
                            <Field value={llamacppBaseUrl} onChange={setLlamacppBaseUrl} mono placeholder="http://localhost:8080" />
                          </Row>
                          <Row label="llama.cpp model" hint="Optional — only needed if the server hosts more than one." stack>
                            <Field value={llamacppModel} onChange={setLlamacppModel} mono placeholder="(optional)" />
                          </Row>
                        </>
                      )}
                    </>
                  )}

                  {(archMode === 'cloud_shield' || archMode === 'cloud_raw') && (
                    <Row label="Cloud model" hint="Keys are set under Security." stack>
                      <Select
                        value={cloudModel}
                        onChange={(v) => { setCloudModel(v); setActiveModel(v); }}
                        options={CLOUD_MODEL_OPTIONS}
                      />
                    </Row>
                  )}
                </Section>

                <Section index="03" title="Voice">
                  <Row label="VAD sensitivity" hint="How readily the microphone treats sound as speech.">
                    <Slider value={vadSensitivity} onChange={setVadSensitivity} min={0} max={100} format={(v) => `${v}%`} />
                  </Row>
                  <Row label="Wake word" hint="Spoken phrase that starts a voice command." stack>
                    <Field value={wakeWord} onChange={setWakeWord} placeholder="hey primnox" mono />
                  </Row>
                  <Row label="Wake word detection" hint="Listen continuously for the wake word.">
                    <Toggle checked={wakeWordEnabled} onChange={setWakeWordEnabled} label="Wake word detection" />
                  </Row>
                </Section>

                <Section index="04" title="Interface">
                  <Row label="Dynamic Island" hint="Floating pill overlay when minimised. Off = normal minimise to taskbar.">
                    <Toggle checked={dynamicIslandEnabled} onChange={setDynamicIslandEnabled} label="Dynamic Island" />
                  </Row>
                </Section>
              </>
            )}

            {/* ── IDENTITY ────────────────────────────────────────────── */}
            {activeTab === 'Identity' && (
              <Section index="01" title="Identity">
                <Row label="Operative alias" hint="What Primnox calls you." stack>
                  <Field value={operatorAlias} onChange={setOperatorAlias} placeholder="Your name" />
                </Row>
                <Row label="Neural ID" hint="What you call Primnox. Used in the interface and in its own replies." stack>
                  <Field value={aiCodename} onChange={setAiCodename} placeholder="Primnox" />
                </Row>
                {profile && (
                  <>
                    <Row label="Current vibe" hint="Inferred by the profiler from recent activity — read-only.">
                      <span className="font-mono text-[11px] text-on-surface/55">{profile.vibe || profile.current_vibe || '—'}</span>
                    </Row>
                    <Row label="Occupation" hint="Inferred by the profiler — read-only.">
                      <span className="font-mono text-[11px] text-on-surface/55">{profile.occupation || '—'}</span>
                    </Row>
                  </>
                )}
              </Section>
            )}

            {/* ── SECURITY ────────────────────────────────────────────── */}
            {activeTab === 'Security' && (
              <>
                <Section index="01" title="API Keys">
                  <Row label="Groq" stack><SecretField value={apiKey} onChange={setApiKey} placeholder="Groq API key" /></Row>
                  <Row label="OpenAI" stack><SecretField value={openaiApiKey} onChange={setOpenaiApiKey} placeholder="OpenAI API key" /></Row>
                  <Row label="Anthropic" stack><SecretField value={anthropicApiKey} onChange={setAnthropicApiKey} placeholder="Anthropic API key" /></Row>
                  <Row label="Gemini" stack><SecretField value={geminiApiKey} onChange={setGeminiApiKey} placeholder="Google AI Studio API key" /></Row>
                </Section>

                <Section index="02" title="Privacy Shield">
                  <Row label="Privacy Mirror" hint="Scrubs PII from every request before it leaves this machine.">
                    <Toggle checked={privacyMirrorEnabled} onChange={setPrivacyMirrorEnabled} label="Privacy Mirror" />
                  </Row>
                  <Row label="Scrubber model" hint="DeBERTa NER. Loads in the background; regex patterns cover the gap.">
                    <Status tone={
                      piiModelStatus === 'ready' ? 'good'
                      : piiModelStatus === 'loading' ? 'warn'
                      : piiModelStatus ? 'bad' : 'muted'
                    }>
                      {piiModelStatus || 'unknown'}
                    </Status>
                  </Row>
                </Section>

                <Section index="03" title="Local Encryption Vault">
                  <Row
                    label="Vault"
                    hint={vaultStatus?.enabled
                      ? 'Local data is encrypted at rest with a key derived from your recovery phrase.'
                      : 'Encrypt local data at rest. You will be given a 12-word recovery phrase.'}
                  >
                    <div className="flex items-center gap-3">
                      <Status tone={vaultStatus?.enabled ? (vaultStatus.locked ? 'warn' : 'good') : 'muted'}>
                        {vaultStatus?.enabled ? (vaultStatus.locked ? 'Locked' : 'Unlocked') : 'Disabled'}
                      </Status>
                      {!vaultStatus?.enabled
                        ? <Button variant="solid" onClick={enableVault} disabled={vaultOp === 'running'}>Enable</Button>
                        : <Button variant="danger" onClick={disableVault} disabled={vaultOp === 'running'}>Disable</Button>}
                    </div>
                  </Row>

                  {vaultStatus?.enabled && vaultStatus.locked && (
                    <Row label="Unlock with recovery phrase" stack>
                      <div className="flex gap-3 items-end">
                        <Field value={vaultMnemonic} onChange={setVaultMnemonic} mono placeholder="12 words, space separated" />
                        <Button variant="solid" onClick={unlockVault} disabled={vaultOp === 'running'}>Unlock</Button>
                      </div>
                    </Row>
                  )}

                  {vaultStatus?.enabled && !vaultStatus.locked && (
                    <Row label="Recovery phrase" hint="Shown once through a single-use token. Store it offline.">
                      <div className="flex items-center gap-3">
                        {showPhrase && vaultPhrase && (
                          <button
                            onClick={() => navigator.clipboard?.writeText(vaultPhrase)}
                            className="font-mono text-[11px] text-on-surface/70 hover:text-primary transition-colors flex items-center gap-2"
                          >
                            {vaultPhrase} <Copy size={11} />
                          </button>
                        )}
                        <Button onClick={showPhrase ? () => setShowPhrase(false) : fetchVaultPhrase}>
                          {showPhrase ? <><EyeOff size={11} className="inline mr-2" />Hide</> : <><Eye size={11} className="inline mr-2" />Reveal</>}
                        </Button>
                      </div>
                    </Row>
                  )}

                  {vaultMnemonicGenerated && (
                    <div className="mt-4 p-5 border border-[var(--a-line)] bg-[var(--a-fill)]">
                      <div className="flex items-center gap-2 mb-2">
                        <AlertTriangle size={13} className="text-[var(--accent)]" />
                        <Status tone="warn">Write this down — it is shown once</Status>
                      </div>
                      <p className="font-mono text-[12px] leading-relaxed text-on-surface break-words">{vaultMnemonicGenerated}</p>
                    </div>
                  )}

                  {vaultOpMsg && (
                    <div className="mt-3"><Status tone={vaultOp === 'error' ? 'bad' : 'good'}>{vaultOpMsg}</Status></div>
                  )}
                </Section>

                <Section index="04" title="Data Management">
                  <Row label="Meeting retention" hint="Recordings and transcripts older than this are removed by the cleanup pass.">
                    <Slider
                      value={meetingRetentionDays}
                      onChange={setMeetingRetentionDays}
                      min={1} max={365}
                      format={(v) => `${v}d`}
                    />
                  </Row>
                  <Row label="Run cleanup now" hint="Applies retention rules and compresses old memories immediately.">
                    <Button onClick={purgeData}><Brain size={11} className="inline mr-2" />Run</Button>
                  </Row>
                </Section>
              </>
            )}

            {/* ── CALENDAR ────────────────────────────────────────────── */}
            {activeTab === 'Calendar' && (
              <Section index="01" title="Calendar Sources">
                {calendarProviders.length === 0 && !showAddCal && (
                  <p className="py-6 text-[12px] text-on-surface/60 leading-[1.7]">
                    No calendars connected. Add an iCal URL, or connect Google, Outlook or Notion.
                  </p>
                )}

                {calendarProviders.map((p, i) => (
                  <Row key={i} label={p.name || p.type} hint={p.url || p.type}>
                    <div className="flex items-center gap-3">
                      <span className="w-3 h-3 rounded-full shrink-0" style={{ background: p.color || 'var(--primary)' }} />
                      <button
                        onClick={() => setCalendarProviders(calendarProviders.filter((_, j) => j !== i))}
                        aria-label={`Remove ${p.name || p.type}`}
                        className="p-2 text-on-surface/55 hover:text-error transition-colors"
                      >
                        <Trash2 size={13} />
                      </button>
                    </div>
                  </Row>
                ))}

                {showAddCal ? (
                  <div className="py-6 space-y-5 border-b border-on-surface/10">
                    <Row label="Provider type" stack>
                      <Select
                        value={calType}
                        onChange={(v) => setCalType(v as any)}
                        options={[
                          { value: 'ical', label: 'iCal URL' },
                          { value: 'google', label: 'Google Calendar' },
                          { value: 'outlook', label: 'Outlook' },
                          { value: 'notion', label: 'Notion' },
                        ]}
                      />
                    </Row>
                    {calType === 'ical' && (
                      <Row label="iCal URL" stack>
                        <Field value={calUrl} onChange={setCalUrl} mono placeholder="https://…/basic.ics" />
                      </Row>
                    )}
                    <Row label="Display name" stack>
                      <Field value={calName} onChange={setCalName} placeholder="Work" />
                    </Row>
                    <Row label="Colour" stack>
                      <input
                        type="color"
                        value={calColor}
                        onChange={(e) => setCalColor(e.target.value)}
                        className="w-16 h-9 bg-transparent border border-on-surface/20 cursor-pointer"
                      />
                    </Row>
                    <div className="flex gap-3">
                      <Button variant="solid" onClick={handleAddCalendar}>Add calendar</Button>
                      <Button onClick={() => setShowAddCal(false)}>Cancel</Button>
                    </div>
                  </div>
                ) : (
                  <div className="pt-6">
                    <Button onClick={() => setShowAddCal(true)}>
                      <Plus size={11} className="inline mr-2" />Add calendar
                    </Button>
                  </div>
                )}
              </Section>
            )}

            {/* ── BACKUP ──────────────────────────────────────────────── */}
            {activeTab === 'Backup' && (
              <>
                <Section index="01" title="Local Backup">
                  <Row label="Back up now" hint="Writes an encrypted .prx snapshot to this machine.">
                    <div className="flex items-center gap-3">
                      {backupStatus !== 'idle' && (
                        <Status tone={backupStatus === 'done' ? 'good' : backupStatus === 'error' ? 'bad' : 'muted'}>
                          {backupStatus === 'running' ? 'Running' : backupStatus === 'done' ? 'Done' : 'Failed'}
                        </Status>
                      )}
                      <Button variant="solid" onClick={triggerBackup} disabled={backupStatus === 'running'}>Back up</Button>
                    </div>
                  </Row>
                </Section>

                <Section index="02" title="Cloud Backup">
                  <Row
                    label="Status"
                    hint={cloudBackupInfo?.enabled
                      ? `Provider: ${cloudBackupInfo.provider || 'unknown'} · every ${cloudBackupInfo.interval_hours ?? '—'}h`
                      : 'Not configured. Backups are encrypted locally before upload; the provider never sees plaintext.'}
                  >
                    <div className="flex items-center gap-3">
                      <Status tone={cloudBackupInfo?.enabled ? 'good' : 'muted'}>
                        {cloudBackupInfo?.enabled ? 'Active' : 'Not configured'}
                      </Status>
                      {cloudBackupInfo?.enabled ? (
                        <>
                          <Button onClick={runCloudBackupNow} disabled={cloudBackupOp === 'running'}>Run now</Button>
                          <Button variant="danger" onClick={disableCloudBackup}>Disable</Button>
                        </>
                      ) : (
                        <Button variant="solid" onClick={() => setShowSetup(s => !s)}>
                          {showSetup ? 'Cancel' : 'Configure'}
                        </Button>
                      )}
                    </div>
                  </Row>

                  {showSetup && (
                    <>
                      <Row label="Recovery phrase" hint="12 words. Without it the backup cannot be decrypted — not even by you." stack>
                        <div className="flex gap-3 items-end">
                          <Field
                            value={mnemonic}
                            onChange={setMnemonic}
                            mono
                            type={showMnemonic ? 'text' : 'password'}
                            placeholder="12 words, space separated"
                          />
                          <Button onClick={() => setShowMnemonic(s => !s)}>{showMnemonic ? 'Hide' : 'Show'}</Button>
                          <Button variant="solid" onClick={generateMnemonic} disabled={mnemonicGenLoading}>
                            {mnemonicGenLoading ? 'Generating' : 'Generate'}
                          </Button>
                        </div>
                      </Row>

                      <Row label="Storage provider" stack>
                        <Select
                          value={providerType}
                          onChange={(v) => setProviderType(v as any)}
                          options={[
                            { value: 's3', label: 'S3-compatible (AWS, B2, R2, Wasabi, MinIO)' },
                            { value: 'gdrive', label: 'Google Drive' },
                            { value: 'dropbox', label: 'Dropbox' },
                            { value: 'https', label: 'Custom HTTPS endpoint' },
                          ]}
                        />
                      </Row>

                      {providerType === 's3' && (
                        <>
                          <Row label="Bucket" stack>
                            <Field value={s3Cfg.bucket} onChange={(v) => setS3Cfg({ ...s3Cfg, bucket: v })} mono placeholder="primnox-backups" />
                          </Row>
                          <Row label="Endpoint URL" hint="Leave blank for AWS S3." stack>
                            <Field value={s3Cfg.endpoint_url} onChange={(v) => setS3Cfg({ ...s3Cfg, endpoint_url: v })} mono placeholder="https://s3.us-west-000.backblazeb2.com" />
                          </Row>
                          <Row label="Region" stack>
                            <Field value={s3Cfg.region} onChange={(v) => setS3Cfg({ ...s3Cfg, region: v })} mono placeholder="us-east-1" />
                          </Row>
                          <Row label="Access key" stack>
                            <SecretField value={s3Cfg.access_key} onChange={(v) => setS3Cfg({ ...s3Cfg, access_key: v })} placeholder="Access key ID" />
                          </Row>
                          <Row label="Secret key" stack>
                            <SecretField value={s3Cfg.secret_key} onChange={(v) => setS3Cfg({ ...s3Cfg, secret_key: v })} placeholder="Secret access key" />
                          </Row>
                        </>
                      )}

                      {providerType === 'https' && (
                        <>
                          <Row label="Server URL" stack>
                            <Field value={httpsCfg.url} onChange={(v) => setHttpsCfg({ ...httpsCfg, url: v })} mono placeholder="https://backup.example.com/upload" />
                          </Row>
                          <Row label="Auth header" hint="Optional. Sent verbatim as the Authorization header." stack>
                            <SecretField value={httpsCfg.auth_header} onChange={(v) => setHttpsCfg({ ...httpsCfg, auth_header: v })} placeholder="Bearer …" />
                          </Row>
                        </>
                      )}

                      <Row label="Backup every" hint="Hours between automatic uploads.">
                        <Slider value={backupInterval} onChange={setBackupInterval} min={1} max={168} format={(v) => `${v}h`} />
                      </Row>

                      <div className="pt-6">
                        <Button variant="solid" onClick={setupCloudBackup} disabled={cloudBackupOp === 'running' || !mnemonic.trim()}>
                          {cloudBackupOp === 'running' ? 'Configuring' : 'Enable cloud backup'}
                        </Button>
                      </div>
                    </>
                  )}

                  {cloudOpMsg && (
                    <div className="pt-4"><Status tone={cloudBackupOp === 'error' ? 'bad' : 'good'}>{cloudOpMsg}</Status></div>
                  )}
                </Section>

                <Section index="03" title="Restore">
                  <Row label="Restore from cloud" hint="Pick a snapshot and supply its recovery phrase." stack>
                    {cloudBackupList.length > 0 ? (
                      <div className="space-y-4">
                        <Select
                          value={restoreFile}
                          onChange={setRestoreFile}
                          options={[
                            { value: '', label: 'Select a backup…' },
                            ...cloudBackupList.map((b: any) => ({
                              value: b.filename || b.name,
                              label: `${b.filename || b.name}${b.size ? ` · ${b.size}` : ''}`,
                            })),
                          ]}
                        />
                        <div className="flex gap-3 items-end">
                          <Field value={restoreMnemonic} onChange={setRestoreMnemonic} mono type="password" placeholder="12-word recovery phrase" />
                          <Button variant="danger" onClick={runCloudRestore} disabled={!restoreFile || !restoreMnemonic.trim() || cloudBackupOp === 'running'}>
                            Restore
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-[12px] text-on-surface/60">No cloud snapshots found.</p>
                    )}
                  </Row>

                  <Row label="Import from file" hint="Restore directly from a .prx file — no provider needed." stack>
                    <div className="space-y-4">
                      <input
                        type="file"
                        accept=".prx"
                        onChange={(e) => setImportFile(e.target.files?.[0] ?? null)}
                        className="block w-full font-mono text-[11px] text-on-surface/55
                          file:mr-4 file:py-2 file:px-5 file:border file:border-on-surface/20
                          file:rounded-full file:bg-transparent file:text-on-surface
                          file:font-mono file:text-[10px] file:uppercase file:tracking-[0.14em]
                          hover:file:border-primary file:cursor-pointer cursor-pointer"
                      />
                      <div className="flex gap-3 items-end">
                        <Field value={importMnemonic} onChange={setImportMnemonic} mono type="password" placeholder="12-word recovery phrase" />
                        <Button variant="danger" onClick={runImport} disabled={!importFile || !importMnemonic.trim() || importOp === 'running'}>
                          Import
                        </Button>
                      </div>
                      {importMsg && (
                        <Status tone={importOp === 'error' ? 'bad' : importOp === 'done' ? 'good' : 'muted'}>{importMsg}</Status>
                      )}
                    </div>
                  </Row>
                </Section>
              </>
            )}
          </motion.div>
        </div>

        {/* Save bar — pinned, so it is reachable from any scroll position */}
        <div className="shrink-0 border-t border-on-surface/10 bg-[var(--nav-bg)] backdrop-blur-2xl px-12 py-5 flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-on-surface/58">
            Changes apply on synchronise
          </span>
          <Button variant="solid" onClick={onSync}>Synchronize_Kernel</Button>
        </div>
      </div>
    </div>
  );
};
