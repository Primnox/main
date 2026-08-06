import { useState, useEffect } from 'react';
import { motion } from 'motion/react';
import { Download, Package, CheckCircle } from 'lucide-react';
import { APP_VERSION } from './TitleBar';

export const LogsPage = ({ activity = [], fetchLogs }: { activity: any[]; fetchLogs?: () => void }) => {
  const [copied, setCopied] = useState(false);

  // Poll for new log entries only while this screen is mounted/visible —
  // previously this ran globally every 5s regardless of which screen the
  // user was on.
  useEffect(() => {
    if (!fetchLogs) return;
    const timer = setInterval(fetchLogs, 5000);
    return () => clearInterval(timer);
  }, [fetchLogs]);

  const exportLogs = () => {
    const lines: string[] = [
      `PRIMNOX Diagnostic Log — ${new Date().toLocaleString()}`,
      `Version: ${APP_VERSION}`,
      `Entries: ${activity.length}`,
      '─'.repeat(60),
      '',
    ];
    for (const entry of activity) {
      const ts = new Date(entry.ts * 1000).toISOString();
      lines.push(`[${ts}] [${entry.level ?? 'INFO'}] ${entry.module ?? 'system'} » ${entry.msg ?? JSON.stringify(entry)}`);
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `Primnox_Diagnostics_${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyDiagnostics = async () => {
    const lines: string[] = [
      `Primnox ${APP_VERSION} — Diagnostic Snapshot — ${new Date().toLocaleString()}`,
      '',
      `Total log entries: ${activity.length}`,
      `Errors: ${activity.filter(e => e.level === 'ERROR').length}`,
      '',
      'Recent entries:',
    ];
    for (const entry of activity.slice(-20)) {
      lines.push(`  [${entry.level ?? 'INFO'}] ${entry.module ?? ''}: ${entry.msg ?? ''}`);
    }
    try {
      await navigator.clipboard.writeText(lines.join('\n'));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // clipboard permission denied — fall back to download
      exportLogs();
    }
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-surface animate-in fade-in slide-in-from-right-8 duration-1000 overflow-hidden">
      <div className="p-8 lg:p-12 border-b border-on-surface/5 bg-surface flex items-center justify-between">
        <div className="flex flex-col">
          <span className="font-mono text-primary text-[10px] uppercase tracking-[0.4em] mb-2 block font-bold">Root@Primnox_Shell_{APP_VERSION}</span>
          <h2 className="text-on-surface text-xl font-bold tracking-tighter italic">system_terminal.exe</h2>
        </div>
        <div className="flex gap-4">
          <button
            onClick={exportLogs}
            className="px-4 py-2 bg-on-surface/5 hover:bg-on-surface/10 border border-on-surface/10 rounded-lg flex items-center gap-2 text-on-surface/70 hover:text-on-surface transition-colors"
          >
            <Download size={14} />
            <span className="font-mono text-[9px] uppercase tracking-widest font-bold">Export Logs</span>
          </button>
          <button
            onClick={copyDiagnostics}
            className="px-4 py-2 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg flex items-center gap-2 text-primary hover:text-primary-light transition-colors"
          >
            {copied ? <CheckCircle size={14} /> : <Package size={14} />}
            <span className="font-mono text-[9px] uppercase tracking-widest font-bold">{copied ? 'Copied!' : 'Copy Diagnostics'}</span>
          </button>
        </div>
      </div>
      
      {/* Was bg-[rgba(5,5,5,1)] — a hardcoded near-black that ignored the theme,
          so on the four light palettes this rendered near-black text on black
          and the log was completely unreadable. */}
      <div className="flex-1 overflow-y-auto p-8 lg:p-12 custom-scrollbar bg-surface">
        <div className="max-w-5xl space-y-8">
          <div className="font-mono text-[10px] text-on-surface/60 mb-10 border-l-2 border-primary/20 pl-6 leading-relaxed">
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
                <span className={`${entry.level === 'ERROR' ? 'text-error/80' : 'text-primary'} font-bold`}>[{new Date(entry.ts * 1000).toLocaleTimeString()}]</span>
                <span className="text-on-surface/48 uppercase tracking-widest">{entry.module}</span>
                <span className="text-on-surface/38">»</span>
              </div>
              <div className="font-mono text-[10px] text-on-surface/60 whitespace-pre-wrap pl-6 leading-loose border-l border-on-surface/5 mb-6">
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
