import { motion, AnimatePresence } from 'motion/react';
import { CheckCircle, Terminal, Copy, X, Music, Maximize2, SkipBack, Play, Pause, SkipForward, Calendar } from 'lucide-react';
import { useState, useEffect, useCallback } from 'react';

type AppMode = 'chat' | 'notes' | 'research';
type AiStatus = 'idle' | 'listening' | 'thinking' | 'transcript' | 'copy' | 'error';

export interface IslandErrorPayload {
  summary: string;
  fix: string;
  hover_text: string;
}

// ── Chord hint definitions ─────────────────────────────────────────────────
const CHORD_HINTS: Record<string, { key: string; label: string }[]> = {
  Control: [
    { key: 'Ctrl+Z', label: 'Undo' },
    { key: 'Ctrl+Shift+P', label: 'Smart Paste' },
    { key: 'Ctrl+Shift+Z', label: 'Zenith Mode' },
    { key: 'Ctrl+Space', label: 'Command Palette' },
    { key: 'Ctrl+`', label: 'Terminal' },
  ],
  Alt: [
    { key: 'Alt+D', label: 'Deadline Bomb' },
    { key: 'Alt+Tab', label: 'Switch App' },
    { key: 'Alt+F4', label: 'Close Window' },
  ],
};

export const DynamicIsland = ({
  mode,
  setMode,
  status,
  setStatus,
  onProfileClick,
  vadLevel = 0,
  transcript = "",
  attachedFile = null,
  errorPayload = null,
  onClearError,
  flowState = null,
  errorStreak = null,
  nowPlaying = null,
  productivityScore = 100,
  parallelTasks = [],
  onSmartPaste,
  onMediaControl,
  proactiveAlert = null,
  onDismissProactive,
  onSuggestionClick,
  isWindowIsland = false,
  onRestoreWindow,
  islandSkills = {},
}: {
  mode: AppMode;
  setMode: (m: AppMode) => void;
  status: AiStatus;
  setStatus: (s: AiStatus) => void;
  onProfileClick: () => void;
  vadLevel?: number;
  transcript?: string;
  attachedFile?: any;
  errorPayload?: IslandErrorPayload | null;
  onClearError?: () => void;
  flowState?: { duration_minutes: number; started_at: number; app: string } | null;
  errorStreak?: { error: string; duration_minutes: number } | null;
  nowPlaying?: { title: string; artist: string; album?: string; source: string; is_playing?: boolean; position_ms?: number; duration_ms?: number; sampled_at?: number } | null;
  productivityScore?: number;
  parallelTasks?: { id: string; label: string; color: string }[];
  onSmartPaste?: () => void;
  onMediaControl?: (action: 'play_pause' | 'next' | 'prev' | 'stop') => void;
  proactiveAlert?: { message: string; suggestions: string[] } | null;
  islandSkills?: Record<string, any>;
  onDismissProactive?: () => void;
  onSuggestionClick?: (s: string) => void;
  /** True when the main window has been shrunk to island-pill mode by Electron */
  isWindowIsland?: boolean;
  /** Called when the user clicks to restore the full window from island-pill mode */
  onRestoreWindow?: () => void;
}) => {

  // ── Error fix copy ─────────────────────────────────────────────────────
  const [fixCopied, setFixCopied] = useState(false);

  // ── Zenith mode ────────────────────────────────────────────────────────
  const [isZenith, setIsZenith] = useState(false);
  const [zenithTask, setZenithTask] = useState('');
  const [zenithStartTime, setZenithStartTime] = useState<number | null>(null);
  const [zenithElapsed, setZenithElapsed] = useState('0:00');

  // ── Deadline bomb ──────────────────────────────────────────────────────
  const [deadlineInput, setDeadlineInput] = useState(false);
  const [deadline, setDeadline] = useState<{ label: string; expiresAt: number } | null>(null);
  const [deadlineText, setDeadlineText] = useState('');
  const [deadlineMinutes, setDeadlineMinutes] = useState('25');
  const [deadlineRemaining, setDeadlineRemaining] = useState('');
  const [deadlinePct, setDeadlinePct] = useState(100);

  // ── Flow elapsed (live counter) ────────────────────────────────────────
  const [flowElapsed, setFlowElapsed] = useState('');

  // ── Now Playing progress (0-100) ──────────────────────────────────────
  const [npProgress, setNpProgress] = useState(0);

  // ── Chord hints ────────────────────────────────────────────────────────
  const [showChordHints, setShowChordHints] = useState(false);
  const [chordModifier, setChordModifier] = useState<string | null>(null);

  // ── Zenith helpers ─────────────────────────────────────────────────────
  const activateZenith = useCallback(() => {
    setIsZenith(true);
    setZenithStartTime(Date.now());
  }, []);

  const deactivateZenith = useCallback(() => {
    setIsZenith(false);
    setZenithTask('');
    setZenithStartTime(null);
    setZenithElapsed('0:00');
  }, []);

  // ── Deadline helper ────────────────────────────────────────────────────
  const armDeadline = useCallback(() => {
    const mins = Math.max(1, parseInt(deadlineMinutes) || 25);
    setDeadline({
      label: deadlineText.trim() || `${mins}m focus`,
      expiresAt: Date.now() + mins * 60 * 1000,
    });
    setDeadlineInput(false);
    setDeadlineText('');
  }, [deadlineMinutes, deadlineText]);

  // ── Error fix copy ─────────────────────────────────────────────────────
  const copyFix = useCallback(async () => {
    if (!errorPayload?.fix) return;
    try {
      await navigator.clipboard.writeText(errorPayload.fix);
      setFixCopied(true);
      setTimeout(() => setFixCopied(false), 2000);
    } catch (_) { /* clipboard blocked */ }
  }, [errorPayload?.fix]);

  // ── Zenith timer effect ────────────────────────────────────────────────
  useEffect(() => {
    if (!isZenith || !zenithStartTime) return;
    const tick = () => {
      const elapsed = Math.floor((Date.now() - zenithStartTime) / 1000);
      const h = Math.floor(elapsed / 3600);
      const m = Math.floor((elapsed % 3600) / 60);
      const s = elapsed % 60;
      setZenithElapsed(
        h > 0
          ? `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
          : `${m}:${s.toString().padStart(2, '0')}`
      );
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [isZenith, zenithStartTime]);

  // ── Deadline countdown effect ──────────────────────────────────────────
  useEffect(() => {
    if (!deadline) { setDeadlineRemaining(''); setDeadlinePct(100); return; }
    const totalMs = deadline.expiresAt - Date.now();
    const tick = () => {
      const rem = Math.max(0, deadline.expiresAt - Date.now());
      const m = Math.floor(rem / 60000);
      const s = Math.floor((rem % 60000) / 1000);
      setDeadlineRemaining(`${m}:${s.toString().padStart(2, '0')}`);
      setDeadlinePct(Math.max(0, Math.round((rem / Math.max(totalMs, 1)) * 100)));
      if (rem <= 0) setDeadline(null);
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [deadline]);

  // ── Flow elapsed counter (30 s updates) ───────────────────────────────
  useEffect(() => {
    if (!flowState) { setFlowElapsed(''); return; }
    const tick = () => {
      const elapsedSec = Math.floor(Date.now() / 1000 - flowState.started_at);
      const m = Math.floor(elapsedSec / 60);
      const h = Math.floor(m / 60);
      setFlowElapsed(h > 0 ? `${h}h${m % 60}m` : `${m}m`);
    };
    tick();
    const iv = setInterval(tick, 30000);
    return () => clearInterval(iv);
  }, [flowState]);

  // ── Now Playing progress tick (1 s) ───────────────────────────────────
  useEffect(() => {
    if (!nowPlaying?.duration_ms || nowPlaying.duration_ms === 0) {
      setNpProgress(0);
      return;
    }
    const tick = () => {
      if (!nowPlaying?.duration_ms) return;
      const elapsed = nowPlaying.is_playing !== false
        ? (Date.now() / 1000 - (nowPlaying.sampled_at ?? 0)) * 1000
        : 0;
      const pos = (nowPlaying.position_ms ?? 0) + elapsed;
      setNpProgress(Math.min(100, Math.max(0, (pos / nowPlaying.duration_ms) * 100)));
    };
    tick();
    const iv = setInterval(tick, 1000);
    return () => clearInterval(iv);
  }, [nowPlaying]);

  // ── Global keyboard shortcuts ──────────────────────────────────────────
  useEffect(() => {
    const MODIFIERS = new Set(['Control', 'Alt', 'Meta']);
    let holdTimer: ReturnType<typeof setTimeout> | null = null;

    const onKeyDown = (e: KeyboardEvent) => {
      if (MODIFIERS.has(e.key) && !showChordHints) {
        holdTimer = setTimeout(() => {
          setChordModifier(e.key);
          setShowChordHints(true);
        }, 400);
      }
      if (e.ctrlKey && e.shiftKey && e.key.toUpperCase() === 'Z') {
        e.preventDefault();
        if (isZenith) deactivateZenith(); else activateZenith();
      }
      if (e.altKey && e.key.toUpperCase() === 'D') {
        e.preventDefault();
        setDeadlineInput(d => !d);
      }
      if (e.ctrlKey && e.shiftKey && e.key.toUpperCase() === 'P') {
        e.preventDefault();
        onSmartPaste?.();
      }
      if (e.key === 'Escape') {
        if (isZenith) deactivateZenith();
        if (deadlineInput) setDeadlineInput(false);
      }
    };

    const onKeyUp = (e: KeyboardEvent) => {
      if (MODIFIERS.has(e.key)) {
        if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
        setShowChordHints(false);
        setChordModifier(null);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    window.addEventListener('keyup', onKeyUp);
    return () => {
      window.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('keyup', onKeyUp);
      if (holdTimer) clearTimeout(holdTimer);
    };
  }, [isZenith, deadlineInput, showChordHints, activateZenith, deactivateZenith, onSmartPaste]);

  // ── Computed values ────────────────────────────────────────────────────
  const hasAmbientData = !!(flowState || errorStreak);

  const isDeadlineCritical = deadline ? (deadline.expiresAt - Date.now()) < 60000 : false;
  const isDeadlineWarning = deadline ? (deadline.expiresAt - Date.now()) < 300000 : false;

  const islandBorderClass =
    isZenith
      ? 'border-indigo-500/30 shadow-[0_0_50px_rgba(99,102,241,0.2)]'
      : deadline && isDeadlineCritical
      ? 'border-red-500/60 shadow-[0_0_60px_rgba(239,68,68,0.4)]'
      : deadline && isDeadlineWarning
      ? 'border-amber-500/40 shadow-[0_0_40px_rgba(245,158,11,0.2)]'
      : status === 'listening'
      ? 'border-primary/50 shadow-[0_0_50px_rgba(79,70,229,0.3)]'
      : status === 'error'
      ? 'border-red-500/50 shadow-[0_0_50px_rgba(239,68,68,0.25)]'
      : productivityScore < 50
      ? 'border-amber-500/15 shadow-[0_10px_40px_rgba(0,0,0,0.8)]'
      : 'border-white/10';

  return (
    <div className="fixed top-0 left-0 right-0 z-[100] pointer-events-none flex flex-col justify-center items-center gap-2">
      {/* pointer-events-none on root so transparent space around the pill doesn't
          swallow clicks on TitleBar buttons or elements below; pill opts back in
          with pointer-events-auto + WebkitAppRegion no-drag on the motion.div */}

      {/* ── Main island container ────────────────────────────────────── */}
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
          type: 'spring',
          stiffness: 500,
          damping: 30,
          mass: 1,
          layout: { type: 'spring', stiffness: 500, damping: 30 },
        }}
        style={{ borderRadius: '0 0 28px 28px', WebkitAppRegion: 'no-drag' } as any}
        className={`pointer-events-auto bg-black/90 backdrop-blur-2xl border-b border-l border-r flex flex-col shadow-[0_10px_40px_rgba(0,0,0,0.8)] overflow-hidden min-h-[52px] ${islandBorderClass}`}
        onMouseEnter={() => {
          if (isWindowIsland && (window as any).electron) {
            (window as any).electron.ipcRenderer.send('island:set-ignore-mouse', false);
          }
        }}
        onMouseLeave={() => {
          if (isWindowIsland && (window as any).electron) {
            (window as any).electron.ipcRenderer.send('island:set-ignore-mouse', true);
          }
        }}
      >
        <AnimatePresence mode="wait">

          {/* ── Zenith Mode ──────────────────────────────────────────── */}
          {isZenith ? (
            <motion.div
              key="zenith"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[520px] p-4 space-y-2"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-[9px] text-indigo-400/60 uppercase tracking-widest">⬡ Zenith_Mode</span>
                <div className="flex items-center gap-3">
                  <span className="font-mono text-[9px] text-white/25 tabular-nums">{zenithElapsed}</span>
                  <button onClick={deactivateZenith} className="text-white/30 hover:text-white transition-colors"><X size={13} /></button>
                </div>
              </div>
              <input
                value={zenithTask}
                onChange={e => setZenithTask(e.target.value)}
                placeholder="what are you locked in on..."
                className="bg-transparent text-[12px] text-white font-mono outline-none placeholder-white/20 border-b border-white/10 pb-1 w-full"
                autoFocus
              />
              <div className="flex items-center text-[8px] font-mono text-white/15 uppercase tracking-widest gap-3">
                <span>⬡ notifications suppressed</span>
                <span className="ml-auto">Esc · Ctrl+Shift+Z to exit</span>
              </div>
            </motion.div>

          ) : deadlineInput ? (
            /* ── Deadline Setup ────────────────────────────────────── */
            <motion.div
              key="deadline-input"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[360px] p-4 space-y-2"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-[9px] text-amber-400/60 uppercase tracking-widest">Deadline_Bomb</span>
                <button onClick={() => setDeadlineInput(false)} className="text-white/30 hover:text-white transition-colors"><X size={13} /></button>
              </div>
              <input
                value={deadlineText}
                onChange={e => setDeadlineText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && armDeadline()}
                placeholder="what's the deadline for?"
                className="bg-transparent text-[11px] text-white font-mono outline-none placeholder-white/20 border-b border-white/10 pb-1 w-full"
                autoFocus
              />
              <div className="flex items-center gap-2">
                <input
                  value={deadlineMinutes}
                  onChange={e => setDeadlineMinutes(e.target.value.replace(/[^0-9]/g, ''))}
                  className="w-14 bg-white/5 border border-white/10 rounded px-2 py-0.5 text-[10px] font-mono text-center text-white outline-none"
                  placeholder="25"
                />
                <span className="text-white/30 text-[9px] font-mono">minutes</span>
                <button
                  onClick={armDeadline}
                  className="ml-auto bg-amber-500/20 text-amber-300 border border-amber-500/30 px-4 py-1 rounded-full font-mono text-[9px] uppercase hover:bg-amber-500 hover:text-black transition-all"
                >
                  ARM
                </button>
              </div>
            </motion.div>

          ) : deadline ? (
            /* ── Deadline Active Countdown ─────────────────────────── */
            <motion.div
              key="deadline-active"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className={`flex items-center gap-4 w-[400px] px-5 py-3 ${isDeadlineCritical ? 'bg-red-500/5' : ''}`}
            >
              <div className="flex-1 overflow-hidden min-w-0">
                <p className="font-mono text-[9px] text-amber-400/50 uppercase tracking-widest truncate">{deadline.label}</p>
                <div className="mt-1.5 h-0.5 w-full bg-white/5 rounded-full overflow-hidden">
                  <motion.div
                    className={`h-full rounded-full transition-colors ${isDeadlineCritical ? 'bg-red-500' : isDeadlineWarning ? 'bg-amber-400' : 'bg-amber-500/60'}`}
                    animate={{ width: `${deadlinePct}%` }}
                    transition={{ duration: 0.5 }}
                  />
                </div>
              </div>
              <span className={`font-mono text-xl font-bold tabular-nums shrink-0 ${isDeadlineCritical ? 'text-red-400' : 'text-amber-300'}`}>
                {deadlineRemaining}
              </span>
              <button onClick={() => setDeadline(null)} className="text-white/30 hover:text-white transition-colors shrink-0"><X size={13} /></button>
            </motion.div>

          ) : status === 'error' && errorPayload ? (
            /* ── Error Panel ───────────────────────────────────────── */
            <motion.div
              key="error"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[420px] p-4 space-y-2"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-[9px] text-red-400/70 uppercase tracking-widest">System_Error</span>
                <button onClick={() => { onClearError?.(); setStatus('idle'); }} className="text-white/40 hover:text-white transition-colors"><X size={13} /></button>
              </div>
              <p className="text-[11px] text-white/90 font-mono leading-relaxed">{errorPayload.summary}</p>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-[10px] text-red-300 bg-red-500/10 border border-red-500/20 px-2 py-1 rounded font-mono truncate">
                  {errorPayload.fix}
                </code>
                <button
                  onClick={copyFix}
                  title={errorPayload.hover_text}
                  className="shrink-0 flex items-center gap-1 bg-red-500/20 text-red-300 border border-red-500/30 px-3 py-1 rounded-full font-mono text-[9px] uppercase hover:bg-red-500 hover:text-white transition-all"
                >
                  {fixCopied ? <CheckCircle size={10} /> : <Copy size={10} />}
                  {fixCopied ? 'Copied' : 'Copy'}
                </button>
              </div>
            </motion.div>

          ) : proactiveAlert ? (
            /* ── Proactive Alert ────────────────────────────────────── */
            <motion.div
              key="proactive"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[440px] p-4 space-y-3"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-[9px] text-primary/50 uppercase tracking-widest">⬡ Primnox</span>
                <button onClick={onDismissProactive} className="text-white/30 hover:text-white transition-colors">
                  <X size={13} />
                </button>
              </div>
              <p className="text-[12px] text-white/80 leading-relaxed font-light">{proactiveAlert.message}</p>
              {proactiveAlert.suggestions.length > 0 && (
                <div className="flex flex-wrap gap-1.5">
                  {proactiveAlert.suggestions.map(s => (
                    <button
                      key={s}
                      onClick={() => { onSuggestionClick?.(s); onDismissProactive?.(); }}
                      className="px-3 py-1 rounded-full bg-white/5 border border-white/10 text-[10px] font-mono text-white/50 hover:bg-primary/20 hover:text-primary hover:border-primary/30 transition-all"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              )}
            </motion.div>

          ) : status === 'copy' ? (
            /* ── Clipboard Buffer ──────────────────────────────────── */
            <motion.div
              key="copy"
              initial={{ opacity: 0, filter: 'blur(5px)' }}
              animate={{ opacity: 1, filter: 'blur(0px)' }}
              exit={{ opacity: 0, filter: 'blur(5px)' }}
              className="flex flex-col w-[340px] p-4 space-y-3"
            >
              <div className="flex justify-between items-center">
                <span className="font-mono text-[9px] text-white/30 uppercase tracking-widest">Clipboard_Buffer</span>
                <button onClick={() => setStatus('idle')} className="bg-white text-black p-1 rounded-full hover:bg-primary transition-colors">
                  <CheckCircle size={12} />
                </button>
              </div>
              <div className="flex items-center justify-between gap-4">
                <p className="text-[11px] text-white font-mono truncate max-w-[200px]">{attachedFile || 'SOVEREIGN_V2_ENCRYPTED.BIN'}</p>
                <button onClick={() => setStatus('idle')} className="bg-primary/20 text-primary border border-primary/30 px-4 py-1 rounded-full font-mono text-[9px] uppercase hover:bg-primary hover:text-white transition-all">
                  Flush_Buffer
                </button>
              </div>
            </motion.div>

          ) : status === 'transcript' ? (
            /* ── Transcript ────────────────────────────────────────── */
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
            /* ── Default View + Ambient Indicators ─────────────────── */
            <motion.div
              key="default"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="flex flex-col"
            >
              {/* Main row */}
              <div className="flex items-center gap-4 h-full px-5 py-2">

                {/* Mode switcher — full app only, hidden in the island overlay window */}
                {!isWindowIsland && (
                  <>
                    <div className="flex items-center gap-1 bg-white/[0.05] p-1 rounded-full shrink-0">
                      {(['notes', 'chat', 'research'] as AppMode[]).map(m => (
                        <button
                          key={m}
                          onClick={() => setMode(m)}
                          className={`px-4 py-1.5 rounded-full font-mono text-[9px] uppercase tracking-widest transition-all
                            ${mode === m ? 'bg-white text-black font-bold shadow-xl' : 'text-white/40 hover:text-white'}`}
                        >
                          {m}
                        </button>
                      ))}
                    </div>
                    <div className="w-px h-5 bg-white/10 shrink-0" />
                  </>
                )}

                {/* Settings + deadline toggle */}
                <div className="flex items-center gap-0.5">
                  <button
                    onClick={onProfileClick}
                    className="p-2 rounded-full hover:bg-white/10 transition-colors text-white/50 hover:text-white"
                    title="Settings"
                  >
                    <div className="w-4 h-4 rounded-full border-2 border-current" />
                  </button>
                  <button
                    onClick={() => setDeadlineInput(d => !d)}
                    className={`p-1.5 rounded-full hover:bg-white/10 transition-colors text-[11px] font-mono
                      ${deadline ? 'text-amber-400/70' : 'text-white/20 hover:text-white/50'}`}
                    title="Alt+D — Deadline bomb"
                  >
                    ◈
                  </button>
                </div>

                {/* Status indicator */}
                <div className="flex items-center gap-3 pr-1 group/status">
                  <div className="flex items-center gap-2">
                    <div className="relative">
                      <span className={`block w-2 h-2 rounded-full transition-all duration-500
                        ${status === 'listening' ? 'bg-red-500 scale-125' :
                          status === 'thinking' ? 'bg-primary' :
                          flowState ? 'bg-indigo-500/60' :
                          'bg-white/20'}`}
                      />
                      {status === 'listening' && (
                        <span className="absolute inset-0 bg-red-500 rounded-full animate-ping opacity-50" />
                      )}
                    </div>
                    <span className="font-mono text-[8px] text-white/30 uppercase tracking-[0.2em] group-hover/status:text-white/60 transition-colors">
                      {status === 'listening' ? 'Listening' :
                       status === 'thinking' ? 'Syncing' :
                       flowState ? 'Flow' :
                       'Deep_Idle'}
                    </span>
                  </div>
                </div>

                {/* Parallel task pills */}
                <AnimatePresence mode="popLayout">
                  {parallelTasks.slice(0, 3).map(task => (
                    <motion.div
                      key={task.id}
                      initial={{ opacity: 0, scale: 0.6, width: 0 }}
                      animate={{ opacity: 1, scale: 1, width: 'auto' }}
                      exit={{ opacity: 0, scale: 0.6, width: 0 }}
                      className="overflow-hidden shrink-0"
                    >
                      <div
                        className="px-2 py-0.5 rounded-full text-[7px] font-mono uppercase tracking-widest whitespace-nowrap"
                        style={{
                          backgroundColor: `${task.color}20`,
                          color: task.color,
                          border: `1px solid ${task.color}30`,
                        }}
                        title={task.label}
                      >
                        {task.label.slice(0, 8)}
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>

                {/* VAD wave (listening only) */}
                <AnimatePresence mode="popLayout">
                  {status === 'listening' && (
                    <motion.div
                      initial={{ width: 0, opacity: 0 }}
                      animate={{ width: 'auto', opacity: 1 }}
                      exit={{ width: 0, opacity: 0 }}
                      className="flex items-center gap-1 px-2 overflow-hidden"
                    >
                      {[0.5, 1, 0.7, 1.2, 0.4, 0.9, 0.6].map((mult, i) => (
                        <motion.div
                          key={i}
                          animate={{ height: [4, Math.max(4, 32 * vadLevel * mult), 4] }}
                          transition={{ repeat: Infinity, duration: 0.3, delay: i * 0.05 }}
                          className="w-1 bg-primary rounded-full shadow-[0_0_10px_rgba(79,70,229,0.6)]"
                        />
                      ))}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* Restore button — only in island-pill mode */}
                {isWindowIsland && (
                  <button
                    onClick={onRestoreWindow}
                    className="ml-auto p-1.5 rounded-full text-white/20 hover:text-white/70 hover:bg-white/10 transition-colors shrink-0"
                    title="Open Primnox"
                  >
                    <Maximize2 size={11} />
                  </button>
                )}
              </div>

              {/* Ambient indicators row (flow / error streak / git) */}
              <AnimatePresence>
                {hasAmbientData && (
                  <motion.div
                    key="ambient"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="flex items-center gap-4 px-5 pb-2 border-t border-white/[0.04] pt-1.5">
                      {flowState && (
                        <span className="text-[8px] font-mono text-indigo-400/50 uppercase tracking-widest whitespace-nowrap">
                          ⬡ FLOW:{flowElapsed || `${flowState.duration_minutes}m`}
                        </span>
                      )}
                      {errorStreak && (
                        <span className="text-[8px] font-mono text-red-400/50 uppercase tracking-widest whitespace-nowrap">
                          ⚡ ERR:{errorStreak.duration_minutes}m
                        </span>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Now playing strip */}
              <AnimatePresence>
                {nowPlaying?.title && (
                  <motion.div
                    key="now-playing"
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="flex flex-col px-5 pb-2 border-t border-white/[0.04] pt-1.5 gap-1">
                      {/* Track row: icon · title · source · controls */}
                      <div className="flex items-center gap-2">
                        <Music size={10} className="text-white/20 shrink-0" />
                        <span className="text-[9px] font-mono text-white/35 truncate flex-1 min-w-0">
                          {nowPlaying.artist ? `${nowPlaying.artist} — ${nowPlaying.title}` : nowPlaying.title}
                        </span>
                        <span className="text-[7px] font-mono text-white/15 uppercase shrink-0">
                          {nowPlaying.source}
                        </span>
                        {onMediaControl && (
                          <div className="flex items-center shrink-0 ml-0.5">
                            <button
                              onClick={() => onMediaControl('prev')}
                              className="p-1 rounded-full text-white/20 hover:text-white/60 hover:bg-white/10 transition-colors"
                              title="Previous"
                            >
                              <SkipBack size={9} />
                            </button>
                            <button
                              onClick={() => onMediaControl('play_pause')}
                              className="p-1 rounded-full text-white/20 hover:text-white/60 hover:bg-white/10 transition-colors"
                              title={nowPlaying.is_playing !== false ? 'Pause' : 'Play'}
                            >
                              {nowPlaying.is_playing !== false ? <Pause size={9} /> : <Play size={9} />}
                            </button>
                            <button
                              onClick={() => onMediaControl('next')}
                              className="p-1 rounded-full text-white/20 hover:text-white/60 hover:bg-white/10 transition-colors"
                              title="Next"
                            >
                              <SkipForward size={9} />
                            </button>
                          </div>
                        )}
                      </div>
                      {/* Progress bar — only shown when SMTC reports a duration */}
                      {(nowPlaying.duration_ms ?? 0) > 0 && (
                        <div className="h-0.5 w-full bg-white/5 rounded-full overflow-hidden">
                          <motion.div
                            className="h-full bg-white/25 rounded-full"
                            style={{ width: `${npProgress}%` }}
                          />
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
              {/* Island skill strips (pluggable — e.g. calendar) */}
              {Object.entries(islandSkills).map(([skillName, data]) => {
                if (!data) return null;
                const urgent  = data.urgent as boolean | undefined;
                const color   = (data.color as string | undefined) || '#6366f1';
                const borderColor = urgent ? 'rgba(245,158,11,0.15)' : 'rgba(255,255,255,0.04)';
                return (
                  <AnimatePresence key={skillName}>
                    <motion.div
                      key={`skill-${skillName}`}
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: 'auto' }}
                      exit={{ opacity: 0, height: 0 }}
                      className="overflow-hidden"
                    >
                      <div
                        className="flex items-center gap-2 px-5 pb-2 pt-1.5 border-t"
                        style={{ borderColor }}
                      >
                        <Calendar size={10} className="shrink-0" style={{ color: `${color}99` }} />
                        <span
                          className="font-mono text-[8px] uppercase tracking-widest shrink-0"
                          style={{ color: urgent ? '#fbbf24' : `${color}80` }}
                        >
                          {data.label}
                        </span>
                        <span
                          className="text-[9px] font-medium truncate flex-1 min-w-0"
                          style={{ color: urgent ? '#fde68a' : 'rgba(255,255,255,0.65)' }}
                        >
                          {data.title}
                        </span>
                        {data.subtitle && (
                          <span className="text-[8px] font-mono text-white/20 shrink-0 truncate max-w-[180px]">
                            {data.subtitle}
                          </span>
                        )}
                        {data.badge && (
                          <span
                            className="font-mono text-[8px] px-1.5 py-0.5 rounded shrink-0"
                            style={{
                              background: urgent ? 'rgba(245,158,11,0.12)' : `${color}18`,
                              color: urgent ? '#fbbf24' : color,
                            }}
                          >
                            {data.badge}
                          </span>
                        )}
                      </div>
                    </motion.div>
                  </AnimatePresence>
                );
              })}
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* ── Chord hints panel (below island) ─────────────────────────── */}
      <AnimatePresence>
        {showChordHints && chordModifier && CHORD_HINTS[chordModifier] && (
          <motion.div
            key="chord-hints"
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-center gap-2 flex-wrap justify-center pointer-events-none"
          >
            {CHORD_HINTS[chordModifier].map(hint => (
              <div
                key={hint.key}
                className="px-3 py-1.5 rounded-xl bg-black/80 border border-white/10 backdrop-blur-xl"
              >
                <span className="font-mono text-[8px] text-white/50">{hint.key}</span>
                <span className="font-mono text-[8px] text-white/25 ml-2">{hint.label}</span>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
