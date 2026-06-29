import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Shield, Cpu, Terminal, Eye, Zap, Database, FileText, Bell, Layers, HardDrive, RefreshCw, Puzzle } from 'lucide-react';

const API_BASE_URL = 'http://localhost:4009';

export const KnowledgePage = ({ activeModel = "llama-3.3-70b-versatile" }: { activeModel?: string }) => {
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

  const statCards = status ? [
    { icon: Database, label: 'Memories', value: status.memories_count ?? '—', sub: `${(status.db_sizes_kb?.['memory.db'] ?? 0)} KB on disk` },
    { icon: FileText, label: 'Notes', value: status.notes_count ?? '—', sub: `${(status.db_sizes_kb?.['chat.db'] ?? 0)} KB chat DB` },
    { icon: Bell, label: 'Reminders', value: status.reminders_count ?? '—', sub: 'pending triggers' },
    { icon: Layers, label: 'Feed Events', value: status.feed_events ?? '—', sub: 'ambient context' },
    { icon: HardDrive, label: 'Last Backup', value: status.last_backup ? '✓' : 'None', sub: status.last_backup ?? 'run a backup' },
    { icon: Cpu, label: 'Active Model', value: (status.active_model ?? activeModel).replace(/_/g, ' '), sub: status.has_api_key ? 'API key ✓' : 'no key set' },
  ] : [];

  return (
    <div className="flex-1 flex flex-col h-full bg-black animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden text-left">
      <div className="p-8 lg:p-12 border-b border-white/5 bg-zinc-950 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Information_Nexus</span>
          <h2 className="text-white text-xl font-bold tracking-tighter italic">system_knowledge.md</h2>
        </div>
        <div className="flex items-center gap-4">
          <button
            onClick={() => fetchStatus(true)}
            className="p-2 text-white/30 hover:text-white transition-colors"
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
              <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
                <Cpu size={18} className="text-primary" />
                Live System Snapshot
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                {statCards.map(({ icon: Icon, label, value, sub }) => (
                  <motion.div
                    key={label}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="p-5 bg-zinc-950 border border-white/5 rounded-2xl flex flex-col gap-2"
                  >
                    <div className="flex items-center gap-2 text-primary">
                      <Icon size={13} />
                      <span className="font-mono text-[9px] uppercase tracking-widest text-white/40">{label}</span>
                    </div>
                    <span className="text-white text-2xl font-bold tracking-tight">{value}</span>
                    <span className="text-white/30 text-[10px] font-mono">{sub}</span>
                  </motion.div>
                ))}
              </div>
              {status?.active_window && (
                <div className="px-4 py-2 bg-white/3 border border-white/5 rounded-xl font-mono text-[10px] text-white/30">
                  active window: <span className="text-white/60">{status.active_window}</span>
                </div>
              )}
            </section>
          )}

          {loading && (
            <div className="flex items-center gap-3 text-white/30 font-mono text-sm">
              <RefreshCw size={14} className="animate-spin" />
              fetching system status…
            </div>
          )}

          {/* Skills section */}
          {skills.length > 0 && (
            <section className="space-y-4 border-t border-white/5 pt-10">
              <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
                <Puzzle size={18} className="text-primary" />
                Loaded Skills ({skills.length})
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {skills.map((s: any) => (
                  <div key={s.name} className="p-4 bg-zinc-950 border border-white/5 rounded-xl flex flex-col gap-2 hover:border-primary/20 transition-all">
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-white">{s.name}</span>
                      <span className="font-mono text-[8px] bg-primary/10 text-primary px-2 py-0.5 rounded-full uppercase tracking-wider">skill</span>
                    </div>
                    {s.description && (
                      <p className="text-xs text-white/40 leading-relaxed">{s.description}</p>
                    )}
                    {s.trigger_words && s.trigger_words.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {s.trigger_words.slice(0, 4).map((tw: string) => (
                          <span key={tw} className="font-mono text-[8px] bg-white/5 text-white/30 px-1.5 py-0.5 rounded">
                            {tw}
                          </span>
                        ))}
                        {s.trigger_words.length > 4 && (
                          <span className="font-mono text-[8px] text-white/20">+{s.trigger_words.length - 4} more</span>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Architecture sections */}
          <section className="space-y-4 border-t border-white/5 pt-10">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Cpu size={18} className="text-primary" />
              Sovereign Brain Co-Processing
            </h3>
            <p className="text-sm text-white/60 leading-relaxed font-light">
              Primnox is designed around a dual compute model. Heavy reasoning is co-processed on the Groq hardware-accelerated cloud utilizing high-throughput Llama models. Capturing, local spatial calculations, and security filtering occur entirely on local silicon, minimizing local CPU/RAM overhead while guaranteeing total privacy.
            </p>
          </section>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-white/80 uppercase tracking-widest flex items-center gap-2">
                <Terminal size={14} className="text-primary" />
                Active Model Pipeline
              </h4>
              <ul className="space-y-2 text-xs font-mono text-white/50">
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Reasoning Brain:</span>
                  <span className="text-white font-bold">{status?.active_model ?? activeModel}</span>
                </li>
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Vision Analysis:</span>
                  <span className="text-white font-bold">Llama-3.2-11b-vision</span>
                </li>
                <li className="flex justify-between border-b border-white/5 pb-2">
                  <span>Voice Synthesis:</span>
                  <span className="text-white font-bold">Whisper-large-v3-turbo</span>
                </li>
                <li className="flex justify-between">
                  <span>Spatial Engine:</span>
                  <span className="text-white font-bold">YOLOv8 nano + EasyOCR</span>
                </li>
              </ul>
            </div>

            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl space-y-4">
              <h4 className="font-mono text-xs text-white/80 uppercase tracking-widest flex items-center gap-2">
                <Shield size={14} className="text-primary" />
                Zero-Trust Firewall
              </h4>
              <p className="text-xs text-white/40 leading-relaxed">
                The local FastAPI server strictly accepts loopback connections from localhost (`127.0.0.1` and `::1`). External network ingress is dropped at the TCP layer. Build pipeline static checks scan source code to block outbound network requests outside of authorized model hosts.
              </p>
            </div>
          </div>

          <section className="space-y-4 border-t border-white/5 pt-10">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Eye size={18} className="text-primary" />
              Local Privacy Mirror
            </h3>
            <p className="text-sm text-white/60 leading-relaxed font-light">
              All transcriptions, foreground text fields, active windows, and clipboard data are passed through a regex-based <strong>PII Scrubbing Engine</strong> locally. Personal identifiers (emails, credit cards, decryption keys, IP addresses) are redacted on local silicon <em>before</em> any text context is synchronized with cloud co-processors.
            </p>
          </section>

          <section className="space-y-4 border-t border-white/5 pt-10">
            <h3 className="text-white text-lg font-bold tracking-tight italic flex items-center gap-3">
              <Zap size={18} className="text-primary" />
              Dynamic Island Shortcuts
            </h3>
            <div className="p-6 bg-zinc-950 border border-white/5 rounded-2xl font-mono text-xs text-white/60 space-y-3">
              {[
                ['Copy Response', 'Click "Copy" pill in Dynamic Island'],
                ['Clear Clipboard', 'Click "Clear" button in Dynamic Island'],
                ['Toggle Sidebar', 'Click Terminal Logo (top-left)'],
                ['Audio Wave RMS', 'Fluctuates dynamically to reflect voice amplitude'],
                ['Smart Paste', 'Paste any clipboard — Primnox reformats for target app'],
                ['Navigate to screen', 'Tell Primnox: "Open notes" / "Go to settings"'],
              ].map(([k, v]) => (
                <div key={k} className="flex justify-between border-b border-white/5 pb-2 last:border-0 last:pb-0">
                  <span>{k}:</span>
                  <span className="text-white text-right max-w-[55%]">{v}</span>
                </div>
              ))}
            </div>
          </section>

        </div>
      </div>
    </div>
  );
};
