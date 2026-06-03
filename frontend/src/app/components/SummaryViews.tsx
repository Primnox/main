import { motion } from 'motion/react';
import { Maximize2, Activity, Info, ExternalLink, Database, MessageSquare, FileText, CheckCircle, Terminal } from 'lucide-react';

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

export const SummariesExpanded = ({ onNavigate, activity = [] }: { onNavigate: (id: ScreenId) => void, activity?: any[] }) => {
  const latestActivity = activity.slice(0, 3);
  
  return (
    <div className="p-8 lg:p-12 space-y-16 animate-in fade-in slide-in-from-bottom-8 duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)]">
      <div className="grid grid-cols-12 gap-10">
        <div 
          onClick={() => onNavigate('summaries_sidebar_hidden')}
          className="col-span-12 lg:col-span-8 bg-zinc-900/40 backdrop-blur-md border border-white/5 group hover:border-primary/40 transition-all duration-700 overflow-hidden relative cursor-pointer shadow-[0_32px_128px_rgba(0,0,0,0.6)] rounded-2xl"
        >
          <div className="h-1.5 bg-gradient-to-r from-primary/30 via-primary/10 to-transparent w-full" />
          <div className="p-12">
            <div className="flex justify-between items-start mb-12">
              <div className="flex gap-8 items-center">
                <div className="w-16 h-16 bg-white/5 border border-white/10 flex items-center justify-center rotate-6 group-hover:rotate-0 transition-transform duration-700 rounded-xl relative">
                  <div className="absolute inset-0 bg-primary/10 blur-xl opacity-0 group-hover:opacity-100 transition-opacity" />
                  <Maximize2 size={32} className="text-white relative z-10" />
                </div>
                <div>
                  <h3 className="text-white text-xl font-bold tracking-tighter mb-2 italic text-left lowercase">
                    {activity[0]?.module || 'system_core_active'}
                  </h3>
                  <p className="font-mono text-white/30 text-[9px] uppercase tracking-[0.4em] font-medium text-left">
                    INDEX: 0x{activity[0]?.ts ? Math.floor(activity[0].ts).toString(16).toUpperCase() : 'NULL'} // REAL_TIME_STREAM
                  </p>
                </div>
              </div>
              <span className="bg-primary/10 text-primary font-mono text-[8px] px-4 py-1.5 border border-primary/20 tracking-[0.3em] font-bold rounded-full lowercase">
                STATUS_{activity[0]?.level || 'STABLE'}
              </span>
            </div>
            <p className="text-white/60 mb-12 leading-relaxed max-w-2xl text-sm font-light text-left line-clamp-2">
              {activity[0]?.msg || 'The Primnox kernel is monitoring all neural pathways. No anomalies detected in the current orchestration cycle.'}
            </p>
            <div className="grid grid-cols-3 gap-12 pt-12 border-t border-white/5">
              <div>
                <span className="font-mono text-[9px] text-white/20 block mb-4 uppercase tracking-[0.4em] font-bold text-left">Active_Clusters</span>
                <div className="flex -space-x-4">
                  {[1,2,3].map(i => (
                    <div key={i} className="w-10 h-10 rounded-full border-4 border-zinc-950 bg-zinc-900 flex items-center justify-center shadow-2xl transition-transform hover:scale-110 hover:z-10 cursor-default">
                       <Terminal size={14} className="text-primary/40" />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <span className="font-mono text-[9px] text-white/20 block mb-4 uppercase tracking-[0.4em] font-bold text-left">Process_Buffer</span>
                <p className="text-white font-mono text-sm font-bold tracking-tighter text-left uppercase">{activity.length}_nodes</p>
              </div>
              <div>
                <span className="font-mono text-[9px] text-white/20 block mb-4 uppercase tracking-[0.4em] font-bold text-left">Health_Index</span>
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_15px_rgba(16,185,129,0.5)] animate-pulse" />
                  <p className="text-white font-mono text-sm font-bold tracking-tighter uppercase">99.9_NOMINAL</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-10">
          <div className="bg-zinc-900/40 backdrop-blur-md border border-white/5 p-10 relative overflow-hidden shadow-[0_32px_128px_rgba(0,0,0,0.6)] rounded-2xl">
            <Activity size={120} className="absolute -top-8 -right-8 text-white/[0.02] rotate-12" />
            <h4 className="font-mono text-[10px] text-white/40 uppercase mb-10 tracking-[0.5em] font-bold text-left">System_Telemetry</h4>
            <div className="space-y-10 relative z-10">
              <div>
                <div className="flex justify-between mb-4 uppercase font-mono text-[10px] tracking-widest leading-none">
                  <span className="text-white/40">Data_Throughput</span>
                  <span className="text-primary font-bold">124.3 GB/s</span>
                </div>
                <div className="w-full bg-white/5 h-[3px] rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: '75%' }}
                    transition={{ duration: 1.5, ease: "easeOut" }}
                    className="bg-primary h-full shadow-[0_0_20px_rgba(79,70,229,0.8)]" 
                  />
                </div>
              </div>
              <div>
                <div className="flex justify-between mb-4 uppercase font-mono text-[10px] tracking-widest leading-none">
                  <span className="text-white/40">Neural_Latency</span>
                  <span className="text-primary font-bold">0.42ms</span>
                </div>
                <div className="w-full bg-white/5 h-[3px] rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: '94%' }}
                    transition={{ duration: 1.5, delay: 0.2, ease: "easeOut" }}
                    className="bg-primary h-full shadow-[0_0_20px_rgba(79,70,229,0.8)]" 
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-primary/5 border border-primary/10 p-8 rounded-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 p-4 opacity-[0.03]">
              <Info size={48} className="text-primary" />
            </div>
            <div className="flex items-center gap-3 mb-4">
              <StatusDot />
              <p className="text-[10px] text-primary font-mono uppercase tracking-[0.4em] font-bold">Observer_Feed</p>
            </div>
            <p className="text-sm text-white/70 leading-relaxed italic font-light text-left lowercase">
              "{activity[1]?.msg || 'Awaiting further instructions from the operator. Kernel remains in high-availability state.'}"
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 text-left">
        {latestActivity.length === 0 ? (
          <div className="col-span-full py-10 text-center text-white/10 font-mono text-xs uppercase tracking-widest">No broadcast nodes available</div>
        ) : (
          latestActivity.map((item, id) => (
            <div 
              key={id}
              onClick={() => onNavigate('summaries_icon_sidebar')} 
              className="bg-zinc-900/20 backdrop-blur-sm border border-white/5 p-10 hover:border-primary/40 transition-all group cursor-pointer shadow-2xl relative overflow-hidden rounded-2xl"
            >
               <div className="absolute top-0 right-0 p-6 opacity-0 group-hover:opacity-100 transition-opacity translate-x-4 group-hover:translate-x-0 duration-500">
              <ExternalLink size={16} className="text-primary" />
            </div>
            <div className="flex justify-between mb-8 uppercase font-mono text-[9px] tracking-[0.4em] font-medium">
              <span className="text-white/20">{new Date(item.ts * 1000).toLocaleTimeString()}</span>
            </div>
            <h3 className="text-white font-bold text-base mb-4 group-hover:text-primary transition-colors leading-tight italic tracking-tighter truncate lowercase">{item.module}</h3>
            <p className="text-white/30 text-xs line-clamp-2 mb-10 leading-relaxed font-light">{item.msg}</p>
            <div className="flex gap-3">
              <span className="px-3 py-1 bg-white/[0.03] border border-white/10 text-white/30 font-mono text-[9px] uppercase tracking-widest rounded-sm">{item.level}</span>
            </div>
          </div>
          ))
        )}
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
        <h1 className="text-4xl font-bold text-white tracking-tighter hover:text-primary transition-all duration-700 cursor-default italic lowercase">
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
              <span className="font-mono text-[10px] text-white/20 uppercase tracking-[0.3em]">VERSION: 2.0.0-HARDENED</span>
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
            <button onClick={() => onNavigate('summaries_expanded')} className="bg-white text-black font-mono px-12 py-5 uppercase text-[12px] font-bold tracking-[0.2em] hover:bg-primary hover:text-white transition-all shadow-2xl active:scale-95 flex items-center gap-4 rounded-xl">
              Apply_Changes
              <CheckCircle size={20} />
            </button>
            <button onClick={() => onNavigate('logs')} className="border border-white/10 text-white/40 font-mono px-12 py-5 uppercase text-[11px] tracking-[0.3em] font-bold hover:bg-white/5 transition-all rounded-xl">
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
      
      <h1 className="text-4xl font-bold text-white tracking-tighter mb-4 lowercase">No Active Sessions Found</h1>
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
          <h1 className="text-3xl lg:text-4xl font-bold tracking-tighter lowercase leading-[0.95] text-white max-w-4xl italic">
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
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-colors" onClick={() => onNavigate('chat_expanded_sidebar')}><MessageSquare size={20} /></button>
            <button className="p-4 rounded-full border border-primary text-primary bg-primary/10 transition-all shadow-[0_0_20px_rgba(79,70,229,0.2)]" onClick={() => onNavigate('notes_icon_sidebar')}><Database size={20} /></button>
            <button className="p-4 rounded-full text-white/40 hover:text-white transition-colors" onClick={() => onNavigate('summaries_expanded')}><FileText size={20} /></button>
          </div>
        </div>
      </div>
    </div>
);
