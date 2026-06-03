import { motion } from 'motion/react';
import { Database, CheckCircle } from 'lucide-react';

export const DataVaultPage = ({ onAccess, memory = [] }: { onAccess?: () => void, memory?: any[] }) => {
  return (
    <div className="flex-1 flex flex-col h-full bg-black animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden text-left">
      <div className="p-8 lg:p-12 border-b border-white/5 bg-zinc-950 flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Cold_Storage_Interface</span>
          <h2 className="text-white text-xl font-bold tracking-tighter italic">Data_Vault.sh</h2>
        </div>
        <div className="flex items-center gap-6">
          <div className="px-4 py-2 bg-primary/10 border border-primary/20 rounded-lg">
            <span className="font-mono text-[10px] text-primary font-bold animate-pulse">ENCRYPTION: ACTIVE</span>
          </div>
          {/* Real-time wave visualization in header */}
          <div className="flex items-center gap-1 opacity-20">
            {[1,2,3,4,5].map(i => (
              <div key={i} className="w-0.5 h-4 bg-primary rounded-full" />
            ))}
          </div>
        </div>
      </div>
      
      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar">
        <div className="max-w-6xl w-full grid grid-cols-1 md:grid-cols-2 gap-6">
          {memory.length === 0 ? (
             <div className="col-span-full p-20 text-center text-white/10 font-mono text-xs uppercase tracking-[0.4em]">Neural Vault Empty</div>
          ) : (
            memory.map((item: any, i: number) => (
            <motion.div 
              key={i}
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: i * 0.1 }}
              className="p-8 bg-zinc-900/20 border border-white/5 rounded-2xl group hover:border-primary/30 transition-all relative overflow-hidden"
            >
              <div className="absolute top-0 right-0 p-4 opacity-5 group-hover:opacity-10 transition-opacity">
                <Database size={80} />
              </div>
              <div className="flex justify-between items-start mb-6">
                <div>
                  <span className="font-mono text-[9px] text-white/20 block mb-2 tracking-widest">VOL_{i.toString().padStart(3, '0')} // {item.category || 'GENERAL'}</span>
                  <h3 className="text-white font-bold text-lg italic tracking-tight truncate max-w-[200px]">{item.text || item}</h3>
                </div>
                <div className={`p-2 rounded-lg border border-emerald-500/20 text-emerald-500 bg-emerald-500/5`}>
                   <CheckCircle size={16} />
                </div>
              </div>
              <div className="space-y-4">
                <div className="flex justify-between font-mono text-[10px]">
                  <span className="text-white/40">Integrity_Check</span>
                  <span className="text-emerald-500">100.0%</span>
                </div>
                <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                  <motion.div 
                    initial={{ width: 0 }}
                    animate={{ width: '100%' }}
                    transition={{ duration: 1.5, delay: i * 0.2 }}
                    className="h-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]"
                  />
                </div>
                <div className="flex justify-between items-center pt-4">
                  <span className="font-mono text-xs text-white/60">NODE_SAVED</span>
                  <button 
                    onClick={onAccess}
                    className="px-4 py-2 bg-white/5 hover:bg-primary text-white font-mono text-[10px] uppercase tracking-widest rounded-lg transition-all opacity-0 group-hover:opacity-100"
                  >
                    Access_Node
                  </button>
                </div>
              </div>
            </motion.div>
          )))}
        </div>
      </div>
    </div>
  );
};
