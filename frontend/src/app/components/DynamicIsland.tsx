import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle, Mic, MicOff, Terminal } from 'lucide-react';

type AppMode = 'chat' | 'notes' | 'research';
type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy';

export const DynamicIsland = ({ 
  mode, 
  setMode, 
  status, 
  setStatus,
  onProfileClick,
  vadLevel = 0,
  transcript = "",
  attachedFile = null,
  micMuted = false,
  onMicClick
}: { 
  mode: AppMode, 
  setMode: (m: AppMode) => void, 
  status: AiStatus,
  setStatus: (s: AiStatus) => void,
  onProfileClick: () => void,
  vadLevel?: number,
  transcript?: string,
  attachedFile?: any,
  micMuted?: boolean,
  onMicClick?: () => void
}) => {
  return (
    <div className="fixed top-12 left-0 right-0 z-[100] pointer-events-auto flex justify-center items-start">
      <motion.div 
        layout
        initial={{ y: -50, scale: 0.9, opacity: 0, filter: 'blur(10px)' }}
        animate={{ 
          y: 0, 
          scale: status === 'listening' ? 1.05 : 1,
          opacity: 1,
          filter: 'blur(0px)',
        }}
        transition={{ 
          type: "spring", 
          stiffness: 500, 
          damping: 30, 
          mass: 1,
          layout: { 
            type: "spring",
            stiffness: 500,
            damping: 30,
          }
        }}
        style={{ borderRadius: 32 }}
        className={`bg-black/90 backdrop-blur-2xl border border-white/10 flex items-center shadow-[0_10px_40px_rgba(0,0,0,0.8)] overflow-hidden min-h-[52px] ${status === 'listening' ? 'border-primary/50 shadow-[0_0_50px_rgba(79,70,229,0.3)]' : ''}`}
      >
        <AnimatePresence mode="wait">
          {status === 'copy' ? (
            <motion.div 
              key="copy"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[340px] p-4 space-y-3"
            >
               <div className="flex justify-between items-center">
                  <span className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Clipboard_Buffer</span>
                  <button 
                    onClick={() => setStatus('idle')}
                    className="bg-white text-black p-1 rounded-full hover:bg-primary transition-colors"
                  >
                    <CheckCircle size={12} />
                  </button>
               </div>
               <div className="flex items-center justify-between gap-4">
                  <p className="text-[11px] text-white font-mono truncate max-w-[200px]">{attachedFile || 'SOVEREIGN_V2_ENCRYPTED.BIN'}</p>
                  <button 
                    onClick={() => setStatus('idle')}
                    className="bg-primary/20 text-primary border border-primary/30 px-4 py-1 rounded-full font-mono text-[9px] uppercase hover:bg-primary hover:text-white transition-all"
                  >
                    Flush_Buffer
                  </button>
               </div>
            </motion.div>
          ) : status === 'transcript' ? (
            <motion.div 
              key="transcript"
              initial={{ opacity: 0, width: 0 }}
              animate={{ opacity: 1, width: 380 }}
              exit={{ opacity: 0, width: 0 }}
              className="flex items-center gap-4 h-full px-5 py-3"
            >
              <div 
                className="w-8 h-8 rounded-full border border-primary/50 bg-primary/20 flex items-center justify-center shrink-0 shadow-[0_0_20px_rgba(79,70,229,0.5)] cursor-pointer"
                onClick={onProfileClick}
              >
                <Terminal size={14} className="text-primary" />
              </div>
              <div className="flex-1 overflow-hidden">
                <p className="text-[12px] text-white font-mono whitespace-nowrap overflow-hidden text-ellipsis italic">
                  "{transcript}"
                </p>
              </div>
            </motion.div>
          ) : (
            <motion.div 
              key="default"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="flex items-center gap-4 h-full px-5 py-2"
            >
              {/* Profile/Logo */}
              <div 
                className={`w-8 h-8 rounded-full border flex items-center justify-center transition-all ${status === 'listening' ? 'border-primary/50 bg-primary/20 shadow-[0_0_20px_rgba(79,70,229,0.5)]' : 'border-white/10 bg-white/5'} cursor-pointer`}
                onClick={onProfileClick}
              >
                <Terminal size={14} className={status === 'listening' ? 'text-primary' : 'text-white/70'} />
              </div>

              <div className="w-px h-5 bg-white/10 shrink-0" />

              {/* Tab Switcher */}
              <div className="flex items-center gap-1 bg-white/[0.05] p-1 rounded-full shrink-0">
                <button 
                  onClick={() => setMode('notes')}
                  className={`px-4 py-1.5 rounded-full font-mono text-[9px] uppercase tracking-widest transition-all ${mode === 'notes' ? 'bg-white text-black font-bold shadow-xl' : 'text-white/40 hover:text-white'}`}
                >
                  Notes
                </button>
                <button 
                  onClick={() => setMode('chat')}
                  className={`px-4 py-1.5 rounded-full font-mono text-[9px] uppercase tracking-widest transition-all ${mode === 'chat' ? 'bg-white text-black font-bold shadow-xl' : 'text-white/40 hover:text-white'}`}
                >
                  Chat
                </button>
                <button 
                  onClick={() => setMode('research')}
                  className={`px-4 py-1.5 rounded-full font-mono text-[9px] uppercase tracking-widest transition-all ${mode === 'research' ? 'bg-white text-black font-bold shadow-xl' : 'text-white/40 hover:text-white'}`}
                >
                  Research
                </button>
              </div>

              <div className="w-px h-5 bg-white/10 shrink-0" />

              {/* Mic Toggle Button */}
              <button 
                onClick={onMicClick}
                className={`p-2 rounded-full hover:bg-white/10 transition-all flex items-center justify-center shrink-0 cursor-pointer ${micMuted ? 'text-red-500' : 'text-primary'}`}
                title={micMuted ? "Unmute Mic" : "Mute Mic"}
              >
                {micMuted ? <MicOff size={16} /> : <Mic size={16} />}
              </button>

              <div className="w-px h-5 bg-white/10 shrink-0" />

              {/* Settings Button */}
              <button onClick={onProfileClick} className="p-2 rounded-full hover:bg-white/10 transition-colors text-white/50 hover:text-white" title="Settings">
                <div className="w-4 h-4 rounded-full border-2 border-current" />
              </button>
              
              {/* Status Indicator */}
              <div className="flex items-center gap-3 pr-2 group/status">
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <span className={`block w-2 h-2 rounded-full transition-all duration-500 ${status === 'listening' ? 'bg-red-500 scale-125' : status === 'thinking' ? 'bg-primary' : 'bg-white/20'}`} />
                    {status === 'listening' && (
                      <span className="absolute inset-0 bg-red-500 rounded-full animate-ping opacity-50" />
                    )}
                  </div>
                  <span className="font-mono text-[8px] text-white/30 uppercase tracking-[0.2em] group-hover/status:text-white/60 transition-colors">
                    {status === 'listening' ? 'Listening' : status === 'thinking' ? 'Syncing' : 'Deep_Idle'}
                  </span>
                </div>
              </div>

              {/* Wave Visualization (Only when listening) */}
              <AnimatePresence mode="popLayout">
                {status === 'listening' && (
                  <motion.div 
                    initial={{ width: 0, opacity: 0 }}
                    animate={{ width: 'auto', opacity: 1 }}
                    exit={{ width: 0, opacity: 0 }}
                    className="flex items-center gap-1 px-2"
                  >
                    {[0.5, 1, 0.7, 1.2, 0.4, 0.9, 0.6].map((mult, i) => (
                      <motion.div
                        key={i}
                        animate={{ height: status === 'listening' ? [4, Math.max(4, 32 * vadLevel * mult), 4] : [4, 16 * mult, 4] }}
                        transition={{ repeat: Infinity, duration: 0.3, delay: i * 0.05 }}
                        className="w-1 bg-primary rounded-full shadow-[0_0_10px_rgba(79,70,229,0.6)]"
                      />
                    ))}
                  </motion.div>
                )}
              </AnimatePresence>

            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
};
