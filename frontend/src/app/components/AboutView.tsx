import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Shield, Cpu, Terminal, Eye, Zap, FileText, Bell, HardDrive, RefreshCw, Puzzle, Plus, Pencil, Trash2, Volume2, Check } from 'lucide-react';
import { API_BASE } from '../../config';
import {
  BUILTIN_PROVIDERS, useProviderModels, type CustomProvider,
} from '../hooks/useProviderModels';
import { deleteJson } from './settings/api';
import { Select, Button, Status } from './settings/primitives';
import { CustomProviderForm } from './settings/CustomProviderForm';

const API_BASE_URL = `${API_BASE}`;

type ModelLibraryProps = {
  apiKey: string; openaiApiKey: string; anthropicApiKey: string; geminiApiKey: string;
  openaiModel: string; setOpenaiModel: (v: string) => void;
  anthropicModel: string; setAnthropicModel: (v: string) => void;
  groqModel: string; setGroqModel: (v: string) => void;
  geminiModel: string; setGeminiModel: (v: string) => void;
  groqTtsModel: string; setGroqTtsModel: (v: string) => void;
  openaiTtsModel: string; setOpenaiTtsModel: (v: string) => void;
  anthropicTtsModel: string; setAnthropicTtsModel: (v: string) => void;
  geminiTtsModel: string; setGeminiTtsModel: (v: string) => void;
  customProviders: CustomProvider[]; setCustomProviders: (v: CustomProvider[]) => void;
  activeCustomProviderId: string;
  settings: any; updateSettings: (s: any) => void | Promise<void>;
};

export const KnowledgePage = ({
  activeModel = "llama-3.3-70b-versatile",
  apiKey = '', openaiApiKey = '', anthropicApiKey = '', geminiApiKey = '',
  openaiModel = '', setOpenaiModel = () => {}, anthropicModel = '', setAnthropicModel = () => {},
  groqModel = '', setGroqModel = () => {}, geminiModel = '', setGeminiModel = () => {},
  groqTtsModel = '', setGroqTtsModel = () => {}, openaiTtsModel = '', setOpenaiTtsModel = () => {},
  anthropicTtsModel = '', setAnthropicTtsModel = () => {}, geminiTtsModel = '', setGeminiTtsModel = () => {},
  customProviders = [], setCustomProviders = () => {},
  activeCustomProviderId = '',
  settings = {}, updateSettings = () => {},
}: Partial<ModelLibraryProps> & { activeModel?: string }) => {
  const [status, setStatus] = useState<any>(null);
  const [skills, setSkills] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const fetchStatus = async (showSpin = false) => {
    if (showSpin) setRefreshing(true);
    try {
      const [statusRes, skillsRes] = await Promise.all([
        fetch(`${API_BASE_URL}/api/status`),
        fetch(`${API_BASE_URL}/api/skills`),
      ]);
      if (statusRes.ok) setStatus(await statusRes.json());
      if (skillsRes.ok) {
        const sd = await skillsRes.json();
        setSkills(sd.skills ?? []);
      }
    } catch { /* backend not running */ }
    finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { fetchStatus(); }, []);

  // ── Model Library ──────────────────────────────────────────────────────
  const apiKeys = { groq: apiKey, openai: openaiApiKey, anthropic: anthropicApiKey, gemini: geminiApiKey };
  const chatModels = useProviderModels({ apiKeys, customProviders, capability: 'chat' });
  const ttsModels = useProviderModels({ apiKeys, customProviders, capability: 'tts' });

  const allProviderKeys = [...BUILTIN_PROVIDERS.map(p => p.key), ...customProviders.map(p => p.id)];
  useEffect(() => {
    allProviderKeys.forEach(key => {
      if (!chatModels.providerModelsCache[key]) chatModels.detectModelsFor(key);
      if (!ttsModels.providerModelsCache[key] && BUILTIN_PROVIDERS.some(p => p.key === key)) {
        ttsModels.detectModelsFor(key);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customProviders.length]);

  const chatModelFor = (key: string): string => {
    if (key === 'groq') return groqModel;
    if (key === 'openai') return openaiModel;
    if (key === 'anthropic') return anthropicModel;
    if (key === 'gemini') return geminiModel;
    return customProviders.find(p => p.id === key)?.model || '';
  };
  const setChatModelFor = (key: string, model: string) => {
    if (key === 'groq') setGroqModel(model);
    else if (key === 'openai') setOpenaiModel(model);
    else if (key === 'anthropic') setAnthropicModel(model);
    else if (key === 'gemini') setGeminiModel(model);
    else setCustomProviders(customProviders.map(p => p.id === key ? { ...p, model } : p));
  };
  const ttsModelFor = (key: string): string =>
    key === 'groq' ? groqTtsModel : key === 'openai' ? openaiTtsModel
    : key === 'anthropic' ? anthropicTtsModel : key === 'gemini' ? geminiTtsModel : '';
  const setTtsModelFor = (key: string, model: string) => {
    if (key === 'groq') setGroqTtsModel(model);
    else if (key === 'openai') setOpenaiTtsModel(model);
    else if (key === 'anthropic') setAnthropicTtsModel(model);
    else if (key === 'gemini') setGeminiTtsModel(model);
  };

  const [dirty, setDirty] = useState(false);
  const [saved, setSaved] = useState(false);
  const markDirty = (fn: () => void) => { fn(); setDirty(true); setSaved(false); };

  const saveModelLibrary = async () => {
    await updateSettings({
      ...settings,
      openai_model: openaiModel, anthropic_model: anthropicModel, groq_model: groqModel, gemini_model: geminiModel,
      groq_tts_model: groqTtsModel, openai_tts_model: openaiTtsModel,
      anthropic_tts_model: anthropicTtsModel, gemini_tts_model: geminiTtsModel,
      custom_providers: customProviders,
    });
    setDirty(false);
    setSaved(true);
  };

  // Custom-endpoint add/edit/delete hit their own REST endpoints immediately
  // (same as Settings) — the dirty/Save flow below is only for the model
  // preference dropdowns, which are plain settings fields with no CRUD of
  // their own.
  const [customFormState, setCustomFormState] = useState<'closed' | 'new' | CustomProvider>('closed');
  const handleCustomSaved = (profile: CustomProvider, isNew: boolean) => {
    setCustomProviders(
      isNew ? [...customProviders, profile] : customProviders.map(p => p.id === profile.id ? profile : p)
    );
    setCustomFormState('closed');
  };
  const deleteCustomProfile = async (id: string) => {
    const ok = await deleteJson(`/api/custom_providers/${id}`);
    if (!ok) return;
    setCustomProviders(customProviders.filter(p => p.id !== id));
  };

  const statCards = status ? [
    { icon: FileText, label: 'Notes', value: status.notes_count ?? '—', sub: `${(status.db_sizes_kb?.['chat.db'] ?? 0)} KB chat DB` },
    { icon: Bell, label: 'Reminders', value: status.reminders_count ?? '—', sub: 'pending triggers' },
    { icon: HardDrive, label: 'Last Backup', value: status.last_backup ? '✓' : 'None', sub: status.last_backup ?? 'run a backup' },
    { icon: Cpu, label: 'Active Model', value: (status.active_model ?? activeModel).replace(/_/g, ' '), sub: status.has_api_key ? 'API key ✓' : 'no key set' },
  ] : [];

  return (
    <div className="flex-1 flex flex-col h-full bg-surface animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden text-left">
      <div className="p-8 lg:p-12 border-b border-on-surface/5 bg-surface flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Information_Nexus</span>
          <h2 className="text-on-surface text-xl font-bold tracking-tighter italic">system_knowledge.md</h2>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => fetchStatus(true)}
            className="p-2 text-on-surface/55 hover:text-on-surface transition-colors"
            title="Refresh system stats"
          >
            <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          </button>
          <div className="px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg">
            <span className="font-mono text-[10px] text-primary font-bold">
              {status ? (status.incognito ? 'INCOGNITO ON' : 'SOVEREIGN V2 ARCH') : 'LOADING…'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar">
        <div className="max-w-4xl w-full space-y-12 pb-24">

          {/* Live stat grid */}
          {!loading && statCards.length > 0 && (
            <section className="space-y-4">
              <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
                <Cpu size={18} className="text-primary" />
                Live System Snapshot
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {statCards.map(({ icon: Icon, label, value, sub }) => (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-5 bg-surface border border-on-surface/5 rounded-2xl flex flex-col gap-2"
                  >
                    <div className="flex items-center gap-2 text-primary">
                      <Icon size={13} />
                      <span className="font-mono text-[9px] uppercase tracking-widest text-on-surface/60">{label}</span>
                    </div>
                    <span className="text-on-surface text-2xl font-bold tracking-tight">{value}</span>
                    <span className="text-on-surface/55 text-[10px] font-mono">{sub}</span>
                  </motion.div>
                ))}
              </div>
              {status?.active_window && (
                <div className="px-4 py-2 bg-on-surface/3 border border-on-surface/5 rounded-xl font-mono text-[10px] text-on-surface/55">
                  active window: <span className="text-on-surface/60">{status.active_window}</span>
                </div>
              )}
            </section>
          )}

          {loading && (
            <div className="flex items-center gap-3 text-on-surface/55 font-mono text-sm">
              <RefreshCw size={14} className="animate-spin" />
              fetching system status…
            </div>
          )}

          {/* Skills section */}
          {skills.length > 0 && (
            <section className="space-y-4 border-t border-on-surface/5 pt-10">
              <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
                <Puzzle size={18} className="text-primary" />
                Loaded Skills ({skills.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {skills.map((s: any) => (
                  <div key={s.name} className="p-4 bg-surface border border-on-surface/5 rounded-xl flex flex-col gap-2 hover:border-primary/20 transition-all">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-on-surface">{s.name}</span>
                      <span className="font-mono text-[8px] bg-primary/10 text-primary px-2 py-0.5 rounded-full uppercase tracking-wider">skill</span>
                    </div>
                    {s.description && (
                      <p className="text-xs text-on-surface/60 leading-relaxed">{s.description}</p>
                    )}
                    {s.trigger_words && s.trigger_words.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {s.trigger_words.slice(0, 4).map((tw: string) => (
                          <span key={tw} className="font-mono text-[8px] bg-on-surface/5 text-on-surface/55 px-1.5 py-0.5 rounded">
                            {tw}
                          </span>
                        ))}
                        {s.trigger_words.length > 4 && (
                          <span className="font-mono text-[8px] text-on-surface/48">+{s.trigger_words.length - 4} more</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Model Library */}
          <section className="space-y-4 border-t border-on-surface/5 pt-10">
            <div className="flex items-center justify-between">
              <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
                <Volume2 size={18} className="text-primary" />
                Model Library
              </h3>
              {dirty ? (
                <Button variant="solid" onClick={saveModelLibrary}>Save changes</Button>
              ) : saved ? (
                <span className="flex items-center gap-1.5 text-[10px] font-mono text-[var(--green)]"><Check size={12} />Saved</span>
              ) : null}
            </div>
            <p className="text-xs text-on-surface/55 leading-relaxed">
              Every model available from an API key you've entered — chat and voice-synthesis. Picking a voice-synthesis
              model here saves your preference; actual voice output still uses the local text-to-speech engine until a
              future update wires cloud playback in.
            </p>

            <div className="space-y-3">
              {[...BUILTIN_PROVIDERS.map(p => ({ key: p.key as string, name: p.label, isCustom: false })),
                ...customProviders.map(p => ({ key: p.id, name: p.name, isCustom: true }))].map(({ key, name, isCustom }) => (
                <div key={key} className="p-4 bg-surface border border-on-surface/5 rounded-xl space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-bold text-on-surface flex items-center gap-2">
                      {name}
                      {(() => {
                        const currentActive = status?.active_model ?? activeModel;
                        const isActive = currentActive === 'Custom'
                          ? key === activeCustomProviderId
                          : key === BUILTIN_PROVIDERS.find(p => p.activeModel === currentActive)?.key;
                        return isActive && (
                          <span className="font-mono text-[8px] bg-primary/10 text-primary px-2 py-0.5 rounded-full uppercase tracking-wider">active</span>
                        );
                      })()}
                    </span>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => { chatModels.detectModelsFor(key); if (!isCustom) ttsModels.detectModelsFor(key); }}
                        aria-label={`Refresh models for ${name}`}
                        className="p-1.5 text-on-surface/50 hover:text-on-surface transition-colors"
                        title="Refresh model list"
                      >
                        <RefreshCw size={12} className={chatModels.detectingProvider === key || ttsModels.detectingProvider === key ? 'animate-spin' : ''} />
                      </button>
                      {isCustom && (
                        <>
                          <button onClick={() => setCustomFormState(customProviders.find(p => p.id === key)!)}
                            aria-label={`Edit ${name}`} className="p-1.5 text-on-surface/50 hover:text-on-surface transition-colors">
                            <Pencil size={12} />
                          </button>
                          <button onClick={() => deleteCustomProfile(key)}
                            aria-label={`Delete ${name}`} className="p-1.5 text-on-surface/50 hover:text-error transition-colors">
                            <Trash2 size={12} />
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <span className="font-mono text-[9px] uppercase tracking-widest text-on-surface/50">Chat model</span>
                      <Select
                        label={`Chat model for ${name}`}
                        value={chatModelFor(key)}
                        onChange={(v) => markDirty(() => setChatModelFor(key, v))}
                        options={(chatModels.providerModelsCache[key]?.models || []).map(m => ({ value: m, label: m }))}
                      />
                    </div>
                    {!isCustom && (
                      <div className="space-y-1.5">
                        <span className="font-mono text-[9px] uppercase tracking-widest text-on-surface/50">Voice synthesis model</span>
                        {ttsModels.providerModelsCache[key]?.models?.length ? (
                          <Select
                            label={`Voice synthesis model for ${name}`}
                            value={ttsModelFor(key)}
                            onChange={(v) => markDirty(() => setTtsModelFor(key, v))}
                            options={ttsModels.providerModelsCache[key].models.map(m => ({ value: m, label: m }))}
                          />
                        ) : (
                          <Status tone="muted">No voice models from this provider</Status>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {customFormState === 'closed' ? (
                <Button onClick={() => setCustomFormState('new')}><Plus size={11} className="inline mr-2" />Add custom endpoint</Button>
              ) : (
                <CustomProviderForm
                  editing={customFormState === 'new' ? null : customFormState}
                  onSave={handleCustomSaved}
                  onCancel={() => setCustomFormState('closed')}
                />
              )}
            </div>
          </section>

          {/* Architecture sections */}
          <section className="space-y-4 border-t border-on-surface/5 pt-10">
            <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Cpu size={18} className="text-primary" />
              Sovereign Brain Co-Processing
            </h3>
            <p className="text-sm text-on-surface/60 leading-relaxed font-light">
              Primnox is designed around a dual compute model. Heavy reasoning is co-processed on the Groq hardware-accelerated cloud utilizing high-throughput Llama models. Capturing, local spatial calculations, and security filtering occur entirely on local silicon, minimizing local CPU/RAM overhead while guaranteeing total privacy.
            </p>
          </section>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-6 bg-surface border border-on-surface/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-on-surface/80 uppercase tracking-widest flex items-center gap-2">
                <Terminal size={14} className="text-primary" />
                Active Model Pipeline
              </h4>
              <ul className="space-y-2 text-xs font-mono text-on-surface/50">
                <li className="flex justify-between border-b border-on-surface/5 pb-2">
                  <span>Reasoning Brain:</span>
                  <span className="text-on-surface font-bold">{status?.active_model ?? activeModel}</span>
                </li>
                <li className="flex justify-between border-b border-on-surface/5 pb-2">
                  <span>Vision Analysis:</span>
                  <span className="text-on-surface font-bold">Llama-3.2-11b-vision</span>
                </li>
                <li className="flex justify-between border-b border-on-surface/5 pb-2">
                  <span>Transcription (STT):</span>
                  <span className="text-on-surface font-bold">Whisper-large-v3-turbo</span>
                </li>
                <li className="flex justify-between">
                  <span>Spatial Engine:</span>
                  <span className="text-on-surface font-bold">YOLOv8 nano + EasyOCR</span>
                </li>
              </ul>
            </div>

            <div className="p-6 bg-surface border border-on-surface/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-on-surface/80 uppercase tracking-widest flex items-center gap-2">
                <Shield size={14} className="text-primary" />
                Zero-Trust Firewall
              </h4>
              <p className="text-xs text-on-surface/60 leading-relaxed">
                The local FastAPI server strictly accepts loopback connections from localhost (`127.0.0.1` and `::1`). External network ingress is dropped at the TCP layer. Build pipeline static checks scan source code to block outbound network requests outside of authorized model hosts.
              </p>
            </div>
          </div>

          <section className="space-y-4 border-t border-on-surface/5 pt-10">
            <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Eye size={18} className="text-primary" />
              Local Privacy Mirror
            </h3>
            <p className="text-sm text-on-surface/60 leading-relaxed font-light">
              All transcriptions, foreground text fields, active windows, and clipboard data are passed through a regex-based <strong>PII Scrubbing Engine</strong> locally. Personal identifiers (emails, credit cards, decryption keys, IP addresses) are redacted on local silicon <em>before</em> any text context is synchronized with cloud co-processors.
            </p>
          </section>

          <section className="space-y-4 border-t border-on-surface/5 pt-10">
            <h3 className="text-on-surface text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Zap size={18} className="text-primary" />
              Dynamic Island Shortcuts
            </h3>
            <div className="p-6 bg-surface border border-on-surface/5 rounded-2xl font-mono text-xs text-on-surface/60 space-y-3">
              {[
                ['Copy Response', 'Click "Copy" pill in Dynamic Island'],
                ['Clear Clipboard', 'Click "Clear" button in Dynamic Island'],
                ['Toggle Sidebar', 'Click Terminal Logo (top-left)'],
                ['Audio Wave RMS', 'Fluctuates dynamically to reflect voice amplitude'],
                ['Smart Paste', 'Paste any clipboard — Primnox reformats for target app'],
                ['Navigate to screen', 'Tell Primnox: "Open notes" / "Go to settings"'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-on-surface/5 pb-2 last:border-0 last:pb-0">
                  <span>{k}:</span>
                  <span className="text-on-surface text-right max-w-[55%]">{v}</span>
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>
    </div>
  );
};
