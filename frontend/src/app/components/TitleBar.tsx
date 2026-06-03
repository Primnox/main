import { Minus, Square, X, MessageSquare } from 'lucide-react';

export const APP_VERSION = "0.0.2-alpha";

export const TitleBar = () => {
  const handleMinimize = () => {
    if ((window as any).electron) {
      (window as any).electron.ipcRenderer.send('minimize-app');
    }
  };

  const handleMaximize = () => {
    if ((window as any).electron) {
      (window as any).electron.ipcRenderer.send('maximize-app');
    }
  };

  const handleClose = () => {
    if ((window as any).electron) {
      (window as any).electron.ipcRenderer.send('close-app');
    }
  };

  return (
    <div 
      className="h-8 w-full shrink-0 flex items-center justify-between z-50 pointer-events-auto pl-4"
      style={{ WebkitAppRegion: 'drag' } as any}
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9px] text-white/30 tracking-widest font-bold">PRIMNOX {APP_VERSION}</span>
      </div>
      
      <div className="flex h-full" style={{ WebkitAppRegion: 'no-drag' } as any}>
        <button 
          onClick={() => alert("Feedback system will be initialized in the next patch.")}
          className="h-full px-4 text-emerald-500/40 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors flex items-center gap-2"
          title="Send Feedback"
        >
          <MessageSquare size={12} />
          <span className="font-mono text-[9px] uppercase tracking-widest">Feedback</span>
        </button>
        <button 
          onClick={handleMinimize}
          className="h-full px-4 text-white/40 hover:text-white hover:bg-white/10 transition-colors"
          title="Minimize"
        >
          <Minus size={14} />
        </button>
        <button 
          onClick={handleMaximize}
          className="h-full px-4 text-white/40 hover:text-white hover:bg-white/10 transition-colors"
          title="Maximize"
        >
          <Square size={12} />
        </button>
        <button 
          onClick={handleClose}
          className="h-full px-4 text-white/40 hover:text-white hover:bg-red-500 transition-colors"
          title="Close"
        >
          <X size={14} />
        </button>
      </div>
    </div>
  );
};
