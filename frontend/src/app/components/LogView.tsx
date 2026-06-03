import { motion } from 'motion/react';
import { Download, Package } from 'lucide-react';
import { APP_VERSION } from './TitleBar';

export const LogsPage = ({ activity = [] }: { activity: any[] }) => {
  return (
    <div className="flex-1 flex flex-col h-full bg-black animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden">
      <div className="p-8 lg:p-12 border-b border-white/5 bg-zinc-950 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Root@Primnox_Shell_{APP_VERSION}</span>
          <h2 className="text-white text-xl font-bold tracking-tighter italic">system_terminal.exe</h2>
        </div>
        <div className="flex gap-4">
          <button 
            onClick={() => alert("Logs exported to Primnox_Diagnostics.txt")}
            className="px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/10 rounded-lg flex items-center gap-2 text-white/70 hover:text-white transition-colors"
          >
            <Download size={14} />
            <span className="font-mono text-[9px] uppercase tracking-widest font-bold">Export Logs</span>
          </button>
          <button 
            onClick={() => alert("Diagnostic package sent to Neural Orchestration Labs securely.")}
            className="px-4 py-2 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg flex items-center gap-2 text-primary hover:text-primary-light transition-colors"
          >
            <Package size={14} />
            <span className="font-mono text-[9px] uppercase tracking-widest font-bold">Send Diagnostics</span>
          </button>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar bg-[rgba(5,5,5,1)]">
        <div className="max-w-5xl space-y-8">
          <div className="font-mono text-[10px] text-white/40 mb-10 border-l-2 border-primary/20 pl-6 leading-relaxed">
            PRIMNOX(tm) Kernel {APP_VERSION} (x64_86)<br/>
            (c) 2026 Neural Orchestration Labs. All rights reserved.<br/>
            Last login: {new Date().toLocaleString()}
          </div>

          {activity.map((entry, i) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, y: 5 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-3"
            >
              <div className="flex gap-3 font-mono text-[10px] items-center">
                <span className={`${entry.level === 'ERROR' ? 'text-red-500' : 'text-primary'} font-bold`}>[{new Date(entry.ts * 1000).toLocaleTimeString()}]</span>
                <span className="text-white/20 uppercase tracking-widest">{entry.module}</span>
                <span className="text-white/10">»</span>
              </div>
              <div className="font-mono text-[10px] text-white/40 whitespace-pre-wrap pl-6 leading-loose border-l border-white/5 mb-6">
                {entry.msg || JSON.stringify(entry)}
              </div>
            </motion.div>
          ))}
          
          <div className="flex gap-3 font-mono text-[11px] items-center">
            <span className="text-primary font-bold">system@primnox:~$</span>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ repeat: Infinity, duration: 0.8 }}
              className="w-2 h-4 bg-primary" 
            />
          </div>
        </div>
      </div>
    </div>
  );
};
