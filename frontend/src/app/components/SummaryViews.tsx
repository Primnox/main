import { useState, useEffect } from 'react';
import { Database, MessageSquare, FileText, CheckCircle, Terminal, Mic, Brain, FileEdit, Video, Monitor, Zap, RefreshCw, AlertTriangle } from 'lucide-react';

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
  | 'archive';

const StatusDot = ({ color = 'bg-primary' }: { color?: string }) => (
  <div className={`w-2 h-2 rounded-full ${color} shadow-[0_0_12px_rgba(79,70,229,0.4)] animate-pulse`} />
);

// ── Stat Card ────────────────────────────────────────────────────────────────
const StatCard = ({ label, value, icon: Icon, sub }: { label: string, value: string | number, icon: any, sub?: string }) => (
  <div className="bg-zinc-900/40 border border-white/5 rounded-2xl p-6 flex flex-col gap-3 hover:border-primary/20 transition-all">
    <div className="flex items-center justify-between">
      <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.4em]">{label}</span>
      <Icon size={14} className="text-white/20" />
    </div>
    <p className="text-3xl font-bold text-white tracking-tight">{value}</p>
    {sub && <p className="text-[10px] text-white/30 font-mono">{sub}</p>}
  </div>
);

// ── Activity Row ─────────────────────────────────────────────────────────────
const FeedRow = ({ event }: { event: string }) => {
  const isAmbient = event.includes('Ambient:');
  const parts = event.split(' - ', 2);
  const time = parts[0] || '';
  const content = parts[1] || event;

  return (
    <div className="flex items-start gap-3 py-2 border-b border-white/[0.03] last:border-0">
      <span className="font-mono text-[9px] text-white/20 mt-0.5 shrink-0 w-14">{time}</span>
      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[8px] font-mono uppercase tracking-wider ${
        isAmbient ? 'bg-primary/10 text-primary' : 'bg-white/5 text-white/30'
      }`}>
        {isAmbient ? 'heard' : 'focus'}
      </span>
      <p className="text-xs text-white/60 leading-relaxed line-clamp-1 font-light">
        {isAmbient ? content.replace('Ambient:', '').trim() : content}
      </p>
    </div>
  );
};

// ── Dashboard (SummariesExpanded) ────────────────────────────────────────────
export const SummariesExpanded = ({ onNavigate, activity: _activity = [] }: { onNavigate: (id: ScreenId) => void, activity?: any[] }) => {
  const [dash, setDash] = useState<any>(null);
  const [briefStatus, setBriefStatus] = useState<'idle' | 'generating' | 'done'>('idle');

  const fetchDash = async () => {
    try {
      const res = await fetch('http://localhost:8000/api/dashboard');
      if (res.ok) setDash(await res.json());
    } catch (_) {}
  };

  useEffect(() => {
    fetchDash();
    const id = setInterval(fetchDash, 30_000);
    return () => clearInterval(id);
  }, []);

  const triggerBrief = async () => {
    setBriefStatus('generating');
    try {
      await fetch('http://localhost:8000/api/daily_brief', { method: 'POST' });
      setBriefStatus('done');
      setTimeout(() => setBriefStatus('idle'), 4000);
    } catch (_) {
      setBriefStatus('idle');
    }
  };

  const feed: string[] = dash?.feed_history ?? [];
  const meetings: any[] = dash?.meetings ?? [];

  return (
    <div className="h-full overflow-y-auto custom-scrollbar">
      <div className="p-8 lg:p-10 space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-700 ease-[cubic-bezier(0.16,1,0.3,1)]">

        {/* ── API Key Banner ── */}
        {dash && !dash.has_api_key && (
          <div className="flex items-center justify-between gap-4 px-5 py-3 bg-amber-500/10 border border-amber-500/20 rounded-xl">
            <div className="flex items-center gap-3">
              <AlertTriangle size={14} className="text-amber-400 shrink-0" />
              <p className="text-sm text-amber-300/90 font-light">
                No API key set — Primnox won't be able to think or transcribe.
              </p>
            </div>
            <button
              onClick={() => onNavigate('island_settings')}
              className="shrink-0 px-4 py-1.5 bg-amber-500/20 border border-amber-500/30 text-amber-300 rounded-lg font-mono text-[10px] uppercase tracking-widest hover:bg-amber-500/30 transition-all"
            >
              Add Key →
            </button>
          </div>
        )}

        {/* ── Header ── */}
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-bold lowercase italic text-white text-xl tracking-tight">
              {new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })}
            </h2>
            <p className="font-mono text-[10px] text-white/30 uppercase tracking-[0.4em] mt-1">Primnox_Dashboard // Live</p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchDash}
              className="p-2 rounded-lg text-white/20 hover:text-primary hover:bg-primary/10 transition-all"
              title="Refresh"
            >
              <RefreshCw size={14} />
            </button>
            <button
              onClick={triggerBrief}
              disabled={briefStatus === 'generating'}
              className="flex items-center gap-2 px-4 py-2 bg-primary/10 border border-primary/20 text-primary rounded-xl font-mono text-[10px] uppercase tracking-widest hover:bg-primary hover:text-black transition-all disabled:opacity-40"
            >
              <Zap size={12} />
              {briefStatus === 'generating' ? 'Generating...' : briefStatus === 'done' ? 'Sent to chat ✓' : 'Daily Brief'}
            </button>
          </div>
        </div>

        {/* ── Stat Cards ── */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard label="Words_Heard" value={dash?.words_heard_today ?? '—'} icon={Mic} sub={`${dash?.ambient_count ?? 0} moments`} />
          <StatCard label="Meetings" value={dash?.meetings?.length ?? '—'} icon={Video} sub="recorded today" />
          <StatCard label="Notes" value={dash?.notes_count ?? '—'} icon={FileEdit} sub="in workspace" />
          <StatCard label="Memories" value={dash?.memories_count ?? '—'} icon={Brain} sub="stored" />
        </div>

        {/* ── Main Grid ── */}
        <div className="grid grid-cols-12 gap-6">

          {/* Activity Feed */}
          <div className="col-span-12 lg:col-span-8 bg-zinc-900/40 border border-white/5 rounded-2xl overflow-hidden">
            <div className="px-6 py-4 border-b border-white/5 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <StatusDot />
                <span className="font-mono text-[10px] text-white/40 uppercase tracking-[0.4em]">Activity_Feed</span>
              </div>
              <span className="font-mono text-[9px] text-white/20">{feed.length} events</span>
            </div>
            <div className="px-6 py-4 max-h-72 overflow-y-auto custom-scrollbar">
              {feed.length === 0 ? (
                <div className="py-8 text-center">
                  <p className="font-mono text-[10px] text-white/20 uppercase tracking-widest">no activity yet — primnox is listening</p>
                </div>
              ) : (
                [...feed].reverse().map((e) => <FeedRow key={e} event={e} />)
              )}
            </div>
          </div>

          {/* Right column */}
          <div className="col-span-12 lg:col-span-4 space-y-4">

            {/* Current Focus */}
            <div className="bg-zinc-900/40 border border-white/5 rounded-2xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Monitor size={12} className="text-white/30" />
                <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.4em]">Current_Focus</span>
              </div>
              {dash ? (
                <>
                  <p className="text-white font-bold text-sm truncate">{dash.active_process || 'Unknown'}</p>
                  <p className="text-white/40 text-xs font-mono truncate mt-1">{dash.active_window || '—'}</p>
                </>
              ) : (
                <p className="text-white/20 text-xs font-mono">connecting...</p>
              )}
            </div>

            {/* Recent Meetings */}
            <div className="bg-zinc-900/40 border border-white/5 rounded-2xl overflow-hidden">
              <div className="px-5 py-4 border-b border-white/5 flex items-center gap-2">
                <Video size={12} className="text-white/30" />
                <span className="font-mono text-[9px] text-white/30 uppercase tracking-[0.4em]">Recent_Meetings</span>
              </div>
              <div className="divide-y divide-white/[0.04]">
                {meetings.length === 0 ? (
                  <p className="px-5 py-4 font-mono text-[10px] text-white/20">no meetings recorded</p>
                ) : (
                  meetings.slice(0, 3).map((m, i) => (
                    <div key={i} className="px-5 py-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-xs text-white/70 font-mono truncate">{m.name}</p>
                        {m.summary_preview && (
                          <p className="text-[10px] text-white/30 mt-1 line-clamp-2 font-light">{m.summary_preview}</p>
                        )}
                      </div>
                      <span className={`shrink-0 text-[8px] font-mono px-2 py-0.5 rounded-full ${
                        m.has_summary ? 'bg-emerald-500/10 text-emerald-400' : 'bg-white/5 text-white/20'
                      }`}>
                        {m.has_summary ? 'summary' : 'raw'}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── Quick Nav ── */}
        <div className="grid grid-cols-3 gap-4">
          {[
            { label: 'Open_Chat', icon: MessageSquare, screen: 'chat_expanded_sidebar' as ScreenId },
            { label: 'View_Notes', icon: FileText, screen: 'notes_icon_sidebar' as ScreenId },
            { label: 'Data_Vault', icon: Database, screen: 'archive' as ScreenId },
          ].map(({ label, icon: Icon, screen }) => (
            <button
              key={screen}
              onClick={() => onNavigate(screen)}
              className="flex items-center justify-center gap-3 p-4 bg-zinc-900/20 border border-white/5 rounded-2xl hover:border-primary/30 hover:bg-primary/5 transition-all group"
            >
              <Icon size={14} className="text-white/30 group-hover:text-primary transition-colors" />
              <span className="font-mono text-[10px] text-white/40 group-hover:text-white uppercase tracking-widest transition-colors">{label}</span>
            </button>
          ))}
        </div>

      </div>
    </div>
  );
};

export const SummariesSidebarHidden = ({ onNavigate }: { onNavigate: (id: ScreenId) => void }) => (
  <div className="h-full flex flex-col p-8 md:p-12 lg:p-20 animate-in fade-in zoom-in-95 duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <div className="mb-16">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-1.5 h-4 bg-primary shadow-[0_0_10px_rgba(79,70,229,0.5)]" />
          <span className="font-mono text-primary lowercase text-xs tracking-[0.4em] font-bold italic opacity-60">session_active // synthesis_buffer</span>
        </div>
        <h1 className="font-bold lowercase italic tracking-wide text-4xl text-white hover:text-primary transition-all duration-700 cursor-default">
          Primary_Interface_X
        </h1>
      </div>

      <div className="glass-panel relative overflow-hidden shadow-[0_64px_256px_rgba(0,0,0,0.8)] border-white/5 group rounded-3xl bg-zinc-900/40 backdrop-blur-3xl">
        <div className="absolute inset-0 bg-gradient-to-br from-primary/[0.03] to-transparent pointer-events-none" />
        <div className="border-b border-white/5 px-12 py-8 flex justify-between items-center bg-white/[0.01]">
          <div className="flex items-center gap-12">
            <div className="flex items-center gap-4">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)] animate-pulse" />
              <span className="font-mono text-[10px] text-white/80 uppercase tracking-[0.3em] font-bold">STATE: STEADY</span>
            </div>
            <div className="h-6 w-px bg-white/10" />
            <div className="flex items-center gap-4">
              <span className="font-mono text-[10px] text-white/20 uppercase tracking-[0.3em]">VERSION: 0.0.4-ALPHA</span>
            </div>
          </div>
        </div>

        <div className="p-12 md:p-20 lg:p-24 max-w-5xl">
          <div className="mb-20">
            <span className="font-mono text-primary lowercase mb-8 block uppercase text-[11px] tracking-[0.5em] font-bold opacity-40">System_Summary</span>
            <p className="text-xl font-bold text-white leading-[1.05] tracking-tight lowercase italic font-light opacity-90 text-left">
              the sovereign neural architecture has achieved full synchronization. all local sub-systems are operating within nominal parameters. privacy filters are active and enforcing local data boundaries.
            </p>
          </div>
          <div className="flex items-center gap-8 pt-20 border-t border-white/5">
            <button onClick={() => onNavigate('summaries_expanded')} className="bg-white text-black font-mono px-12 py-5 uppercase text-[12px] font-bold tracking-[0.2em] hover:bg-primary hover:text-white shadow-2xl flex items-center gap-4 rounded-xl transition-all duration-300 ease-out active:scale-95">
              Apply_Changes
              <CheckCircle size={20} />
            </button>
            <button onClick={() => onNavigate('logs')} className="border border-white/10 text-white/40 font-mono px-12 py-5 uppercase text-[11px] tracking-[0.3em] font-bold hover:bg-white/5 rounded-xl transition-all duration-300 ease-out active:scale-95">
              VIEW_RAW_HEX
            </button>
          </div>
        </div>
      </div>
    </div>
);

export const SummariesEmptyState = ({ onNavigate }: { onNavigate: (id: ScreenId) => void }) => (
  <div className="p-12 lg:p-20 h-full flex flex-col justify-center items-center text-center animate-in fade-in slide-in-from-bottom-8 duration-1000">
      <div className="relative mb-12">
        <div className="w-32 h-32 rounded-full border border-white/5 flex items-center justify-center relative">
          <div className="absolute inset-0 border border-primary/20 rounded-full animate-ping [animation-duration:3s]" />
          <Database size={48} className="text-primary/40" />
        </div>
        <div className="absolute -bottom-2 left-1/2 -translate-x-1/2 bg-black border border-white/10 px-3 py-1 rounded font-mono text-[8px] text-primary uppercase">Idle_State</div>
      </div>
      
      <h1 className="font-bold lowercase italic tracking-wide text-4xl text-white mb-4">No Active Sessions Found</h1>
      <p className="text-on-surface-variant max-w-sm leading-relaxed mb-12 opacity-60 lowercase">The neural nexus is currently in stasis. Initialize a new analysis task to begin data orchestration.</p>
      
      <div className="flex flex-col gap-4">
        <button 
          onClick={() => onNavigate('summaries_expanded')}
          className="bg-primary text-black font-mono px-12 py-4 uppercase text-[11px] font-bold tracking-[0.2em] hover:brightness-110 transition-all shadow-[0_0_30px_rgba(79,70,229,0.2)]"
        >
          Initialize_Analysis
        </button>
        <a 
          href="#" 
          onClick={(e) => { e.preventDefault(); onNavigate('notes_icon_sidebar'); }}
          className="text-[10px] text-white/30 hover:text-primary transition-colors font-mono uppercase tracking-widest"
        >
          historical_archive
        </a>
      </div>
    </div>
);

export const SummariesIconSidebar = ({ onNavigate, notes = [] }: { onNavigate: (id: ScreenId) => void, notes?: any[] }) => (
  <div className="flex flex-col lg:flex-row h-full">
      <aside className="w-full lg:w-80 border-r border-white/5 p-8 space-y-10 bg-surface-container-lowest overflow-y-auto custom-scrollbar">
        <div>
          <h4 className="font-mono text-white/30 uppercase mb-5 text-[9px] tracking-[0.3em]">Core_Insights</h4>
          <ul className="space-y-6">
            {notes.length === 0 ? (
              <li className="text-[11px] text-white/20 italic font-mono uppercase tracking-widest">No nodes synced...</li>
            ) : (
              notes.slice(0, 5).map((note, idx) => (
                <li key={idx} className="flex gap-4 group">
                  <span className="font-mono text-primary text-[10px] mt-1 tabular-nums">0{idx+1}</span>
                  <p className="text-[13px] text-on-surface-variant leading-relaxed opacity-80 group-hover:opacity-100 transition-opacity line-clamp-2 italic lowercase">
                    {typeof note === 'string' ? note : note.text}
                  </p>
                </li>
              ))
            )}
          </ul>
        </div>
        
        <div className="pt-10 border-t border-white/5">
           <h4 className="font-mono text-white/30 uppercase mb-5 text-[9px] tracking-[0.3em]">System_State</h4>
           <div className="space-y-4">
             <div className="flex justify-between items-center bg-black/40 p-3 border border-white/5 group hover:border-primary/30 transition-all">
                <span className="font-mono text-[10px] text-white/40">MEMORY</span>
                <span className="font-mono text-[10px] text-emerald-400 tracking-tighter uppercase">{notes.length > 0 ? 'OPTIMAL' : 'IDLE'}</span>
             </div>
           </div>
        </div>
      </aside>

      <div className="flex-1 overflow-y-auto custom-scrollbar max-w-5xl mx-auto p-10 lg:p-20 space-y-14 pb-40 animate-in fade-in slide-in-from-right-8 duration-700">
        <header className="space-y-6 text-left">
          <div className="w-fit">
            <span className="bg-primary/10 text-primary px-3 py-1 border border-primary/20 font-mono text-[10px] uppercase tracking-[0.2em] shadow-[0_0_15px_rgba(79,70,229,0.1)]">Neural Nexus Core</span>
          </div>
          <h1 className="font-bold lowercase italic tracking-wide text-3xl lg:text-4xl leading-[0.95] text-white max-w-4xl">
            {notes[0] ? (typeof notes[0] === 'string' ? notes[0] : notes[0].text) : 'Technical architecture of the decentralized neural nexus'}
          </h1>
          <div className="flex items-center gap-4 pt-4">
             <div className="flex -space-x-2">
                {[1,2,3].map(i => <div key={i} className="w-8 h-8 rounded-full border-2 border-zinc-950 bg-zinc-900 flex items-center justify-center"><Terminal size={12} className="text-primary/20" /></div>)}
             </div>
             <span className="font-mono text-[10px] text-white/20 uppercase tracking-widest italic lowercase">Authored by Primnox_Agent</span>
          </div>
        </header>

        <div className="glass-panel p-10 border-l-2 border-l-primary relative overflow-hidden group">
           <div className="absolute top-0 right-0 p-4 opacity-[0.03] pointer-events-none group-hover:opacity-[0.05] transition-opacity">
              <Database size={100} />
           </div>
           <p className="text-base text-on-surface leading-loose italic opacity-90 relative z-10 font-medium text-left lowercase">
            "{notes[1] ? (typeof notes[1] === 'string' ? notes[1] : notes[1].text) : 'the proposed framework leverages a sharded graph topology to ensure linear scalability across heterogenous nodes.'}"
          </p>
        </div>
        
        <div className="grid grid-cols-2 lg:grid-cols-3 gap-8">
           <div className="p-6 bg-surface-container-lowest border border-white/5">
              <span className="block font-mono text-[9px] text-white/30 uppercase mb-4 tracking-widest text-center">Node_Count</span>
              <p className="text-2xl font-bold text-white tracking-tighter text-center italic">{notes.length}</p>
           </div>
           <div className="p-6 bg-surface-container-lowest border border-white/5">
              <span className="block font-mono text-[9px] text-white/30 uppercase mb-4 tracking-widest text-center">Sync_Frequency</span>
              <p className="text-2xl font-bold text-white tracking-tighter text-center italic">0.05ms</p>
           </div>
        </div>

        <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-50">
          <div className="flex gap-2 p-2 bg-black/70 backdrop-blur-3xl rounded-full border border-white/10 shadow-[0_20px_50px_rgba(0,0,0,0.5)]">
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('chat_expanded_sidebar')}><MessageSquare size={20} /></button>
            <button className="p-4 rounded-full border border-primary text-primary bg-primary/10 shadow-[0_0_20px_rgba(79,70,229,0.2)] transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('notes_icon_sidebar')}><Database size={20} /></button>
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-all duration-300 ease-out active:scale-95" onClick={() => onNavigate('summaries_expanded')}><FileText size={20} /></button>
          </div>
        </div>
      </div>
    </div>
);
