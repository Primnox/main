import { useState, useEffect } from 'react';
import { Minus, Square, X, MessageSquare, DownloadCloud } from 'lucide-react';
import { FeedbackModal } from './FeedbackModal';

// Version is injected by Vite at build time from package.json (see vite.config.ts define)
declare const __APP_VERSION__: string;
export const APP_VERSION: string = (typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.1.1');


export const TitleBar = () => {
  const [isFeedbackOpen, setIsFeedbackOpen] = useState(false);
  const [updateStatus, setUpdateStatus] = useState<'none' | 'available' | 'downloaded'>('none');

  useEffect(() => {
    if ((window as any).electron) {
      const unsubAvailable = (window as any).electron.ipcRenderer.on('update-available', () => {
        setUpdateStatus('available');
      });
      const unsubDownloaded = (window as any).electron.ipcRenderer.on('update-downloaded', () => {
        setUpdateStatus('downloaded');
      });
      return () => {
        if (unsubAvailable) unsubAvailable();
        if (unsubDownloaded) unsubDownloaded();
      };
    }
  }, []);

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

  const handleRestartUpdate = () => {
    if ((window as any).electron) {
      (window as any).electron.ipcRenderer.send('restart-app');
    }
  };

  return (
    <>
      <div 
        className="h-8 w-full shrink-0 flex items-center justify-between z-50 pointer-events-auto pl-4"
        style={{ WebkitAppRegion: 'drag' } as any}
      >
        <div className="flex items-center gap-2">
          <span className="font-mono text-[9px] text-white/30 tracking-widest font-bold">PRIMNOX {APP_VERSION}</span>
        </div>
        
        <div className="flex h-full" style={{ WebkitAppRegion: 'no-drag' } as any}>
          {updateStatus !== 'none' && (
            <button 
              onClick={updateStatus === 'downloaded' ? handleRestartUpdate : undefined}
              className={`h-full px-4 transition-colors flex items-center gap-2 ${
                updateStatus === 'downloaded' 
                  ? 'text-cyan-400 hover:bg-cyan-500/10 cursor-pointer animate-pulse' 
                  : 'text-cyan-500/50 cursor-default'
              }`}
              title={updateStatus === 'downloaded' ? "Click to restart and install update" : "Downloading update..."}
            >
              <DownloadCloud size={12} />
              <span className="font-mono text-[9px] uppercase tracking-widest">
                {updateStatus === 'downloaded' ? 'Install Update' : 'Downloading'}
              </span>
            </button>
          )}

          <button 
            onClick={() => setIsFeedbackOpen(true)}
            className="h-full px-4 text-emerald-500/40 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors flex items-center gap-2"
            title="Send Feedback"
          >
            <MessageSquare size={12} />
            <span className="font-mono text-[9px] uppercase tracking-widest">Feedback</span>
          </button>
          <button
            onClick={handleMinimize}
            className="h-full px-4 text-white/40 hover:text-white hover:bg-white/10 transition-colors"
            title="Island mode  ·  click tray icon to restore"
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
            className="h-full px-4 text-white/40 hover:text-white hover:bg-red-500/80 transition-colors"
            title="Minimize to tray  ·  Right-click tray → Quit to exit"
          >
            <X size={14} />
          </button>
        </div>
      </div>
      <FeedbackModal isOpen={isFeedbackOpen} onClose={() => setIsFeedbackOpen(false)} />
    </>
  );
};
