import { useState, useRef, useCallback, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import {
  Search, Globe, ArrowRight, Loader2, BookOpen,
  ExternalLink, Sparkles, Radio,
  AlertCircle, CheckCircle2,
  RefreshCw, ChevronDown, ChevronUp,
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

// ── Types ──────────────────────────────────────────────────────────────────────

type Depth = 1 | 2 | 3;

interface LogEntry {
  id:    number;
  type:  'status' | 'query' | 'source' | 'reading' | 'insight' | 'error';
  text:  string;
  round?: number;
  url?:  string;
}

interface Source {
  index:   number;
  title:   string;
  url:     string;
  snippet: string;
}

// ── Simple markdown renderer ───────────────────────────────────────────────────

function renderInline(text: string, sources: Source[]): React.ReactNode[] {
  // Handle **bold**, [n] citations
  const parts = text.split(/(\*\*[^*]+\*\*|\[\d+\])/g);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i} className="text-white font-semibold">{part.slice(2, -2)}</strong>;
    }
    const citeMatch = part.match(/^\[(\d+)\]$/);
    if (citeMatch) {
      const idx = parseInt(citeMatch[1]);
      const src = sources.find(s => s.index === idx);
      return (
        <a key={i} href={src?.url} target="_blank" rel="noreferrer"
          className="inline-flex items-center justify-center w-4 h-4 rounded text-[9px] font-bold font-mono bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 hover:bg-indigo-500/40 transition-colors mx-0.5 align-super"
          title={src?.title}
        >
          {idx}
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function MarkdownReport({ content, sources }: { content: string; sources: Source[] }) {
  const lines  = content.split('\n');
  const nodes: React.ReactNode[] = [];
  let   listBuf: string[] = [];
  let   key = 0;

  const flush = () => {
    if (!listBuf.length) return;
    nodes.push(
      <ul key={key++} className="space-y-1 my-3 pl-4">
        {listBuf.map((item, i) => (
          <li key={i} className="flex items-start gap-2 text-sm text-white/70 leading-relaxed">
            <span className="mt-1.5 w-1 h-1 rounded-full bg-indigo-400/60 shrink-0" />
            <span>{renderInline(item, sources)}</span>
          </li>
        ))}
      </ul>
    );
    listBuf = [];
  };

  for (const line of lines) {
    if (line.startsWith('## ')) {
      flush();
      const title = line.slice(3).trim();
      if (title.toLowerCase() === 'sources') continue; // we render our own
      nodes.push(
        <h2 key={key++} className="text-lg font-bold text-white mt-7 mb-3 pb-2 border-b border-white/[0.07]">
          {title}
        </h2>
      );
    } else if (line.startsWith('### ')) {
      flush();
      nodes.push(
        <h3 key={key++} className="text-sm font-semibold text-white/80 mt-5 mb-2 uppercase tracking-wider">
          {line.slice(4).trim()}
        </h3>
      );
    } else if (line.match(/^[-*] /)) {
      listBuf.push(line.slice(2).trim());
    } else if (line.match(/^\d+\. /)) {
      listBuf.push(line.replace(/^\d+\. /, '').trim());
    } else if (line.trim() === '') {
      flush();
    } else {
      flush();
      nodes.push(
        <p key={key++} className="text-sm text-white/70 leading-relaxed my-2">
          {renderInline(line.trim(), sources)}
        </p>
      );
    }
  }
  flush();

  return <div className="space-y-0.5">{nodes}</div>;
}

// ── Log entry row ──────────────────────────────────────────────────────────────

function LogRow({ entry }: { entry: LogEntry }) {
  const icons: Record<LogEntry['type'], React.ReactNode> = {
    status:  <Radio      size={10} className="text-indigo-400/70 animate-pulse" />,
    query:   <Search     size={10} className="text-white/40" />,
    source:  <Globe      size={10} className="text-emerald-400/60" />,
    reading: <BookOpen   size={10} className="text-blue-400/60" />,
    insight: <Sparkles   size={10} className="text-amber-400/60" />,
    error:   <AlertCircle size={10} className="text-red-400" />,
  };

  const colors: Record<LogEntry['type'], string> = {
    status:  'text-indigo-300/80',
    query:   'text-white/55',
    source:  'text-emerald-300/70',
    reading: 'text-blue-300/70',
    insight: 'text-amber-300/80',
    error:   'text-red-300',
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: -6 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-start gap-2 py-1.5"
    >
      <div className="mt-0.5 shrink-0">{icons[entry.type]}</div>
      <p className={`text-[11px] leading-snug ${colors[entry.type]} break-all`}>
        {entry.type === 'query' && (
          <span className="font-mono text-[9px] text-white/20 mr-1.5 uppercase">
            r{entry.round}
          </span>
        )}
        {entry.text}
      </p>
    </motion.div>
  );
}

// ── Depth badge ────────────────────────────────────────────────────────────────

function DepthPicker({ value, onChange }: { value: Depth; onChange: (d: Depth) => void }) {
  const opts: { d: Depth; label: string; time: string }[] = [
    { d: 1, label: 'Fast',     time: '~15s' },
    { d: 2, label: 'Standard', time: '~35s' },
    { d: 3, label: 'Deep',     time: '~60s' },
  ];
  return (
    <div className="flex gap-1">
      {opts.map(({ d, label, time }) => (
        <button key={d} onClick={() => onChange(d)}
          className={`px-3 py-1.5 rounded-lg font-mono text-[10px] uppercase tracking-widest transition-all
            ${value === d
              ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
              : 'text-white/25 hover:text-white/50 border border-white/[0.06] hover:border-white/20'}`}
        >
          {label}
          <span className="ml-1 opacity-50">{time}</span>
        </button>
      ))}
    </div>
  );
}

// ── Main view ──────────────────────────────────────────────────────────────────

export const ResearchView = () => {
  const [query,      setQuery]      = useState('');
  const [depth,      setDepth]      = useState<Depth>(2);
  const [running,    setRunning]    = useState(false);
  const [done,       setDone]       = useState(false);
  const [log,        setLog]        = useState<LogEntry[]>([]);
  const [report,     setReport]     = useState('');
  const [sources,    setSources]    = useState<Source[]>([]);
  const [logOpen,    setLogOpen]    = useState(true);
  const [sourcesOpen,setSourcesOpen]= useState(true);
  const [error,      setError]      = useState<string | null>(null);
  const logRef    = useRef<HTMLDivElement>(null);
  const abortRef  = useRef<AbortController | null>(null);
  const idRef     = useRef(0);

  // Auto-scroll log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [log]);

  const addLog = useCallback((entry: Omit<LogEntry, 'id'>) => {
    setLog(prev => [...prev, { ...entry, id: ++idRef.current }]);
  }, []);

  const startResearch = useCallback(async () => {
    const q = query.trim();
    if (!q || running) return;

    // reset
    setRunning(true);
    setDone(false);
    setLog([]);
    setReport('');
    setSources([]);
    setError(null);
    setLogOpen(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const resp = await fetch(`${API_BASE}/api/research/deep`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ query: q, depth }),
        signal:  ctrl.signal,
      });

      if (!resp.ok) throw new Error(`Server error ${resp.status}`);
      if (!resp.body) throw new Error('No response body');

      const reader  = resp.body.getReader();
      const decoder = new TextDecoder();
      let   buf     = '';

      while (true) {
        const { done: rd, value } = await reader.read();
        if (rd) break;

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() ?? '';   // keep incomplete line

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith('data:')) continue;
          const raw = trimmed.slice(5).trim();
          if (raw === '[DONE]') { setDone(true); break; }

          let ev: any;
          try { ev = JSON.parse(raw); } catch { continue; }

          switch (ev.type) {
            case 'status':
              addLog({ type: 'status', text: ev.text });
              break;
            case 'query':
              addLog({ type: 'query', text: ev.text, round: ev.round });
              break;
            case 'source':
              addLog({ type: 'source', text: `${ev.title}`, url: ev.url });
              break;
            case 'reading':
              addLog({ type: 'reading', text: ev.title, url: ev.url });
              break;
            case 'insight':
              addLog({ type: 'insight', text: ev.text });
              break;
            case 'report':
              setReport(ev.content);
              break;
            case 'done':
              setSources(ev.sources ?? []);
              setDone(true);
              break;
            case 'error':
              setError(ev.text);
              addLog({ type: 'error', text: ev.text });
              break;
          }
        }
      }
    } catch (e: any) {
      if (e.name !== 'AbortError') {
        setError(e.message || 'Research failed');
      }
    } finally {
      setRunning(false);
    }
  }, [query, depth, addLog]);

  const stopResearch = () => {
    abortRef.current?.abort();
    setRunning(false);
  };

  const reset = () => {
    stopResearch();
    setDone(false);
    setLog([]);
    setReport('');
    setSources([]);
    setError(null);
    setQuery('');
  };

  const QUICK = [
    'Latest breakthroughs in AI agents 2025',
    'How does CRISPR gene editing work',
    'Quantum computing current state',
    'Best practices for microservices architecture',
  ];

  const showResults = report || running;

  return (
    <div className="h-full flex flex-col bg-black text-white overflow-hidden">

      {/* ── Search bar ──────────────────────────────────────────────────── */}
      <div className="shrink-0 px-6 pt-5 pb-4 border-b border-white/[0.05]">
        <div className="max-w-3xl mx-auto space-y-3">

          {/* Input row */}
          <div className="relative group">
            <div className="absolute -inset-px bg-gradient-to-r from-indigo-500/30 to-purple-500/30 rounded-2xl blur opacity-0 group-focus-within:opacity-100 transition duration-500" />
            <div className="relative flex items-center bg-zinc-950 border border-white/10 rounded-2xl overflow-hidden">
              <Search size={16} className="text-white/25 ml-5 shrink-0" />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && startResearch()}
                placeholder="What do you want to research?"
                disabled={running}
                className="flex-1 bg-transparent px-4 py-4 text-sm text-white placeholder:text-white/20 outline-none disabled:opacity-60"
              />
              {running ? (
                <button onClick={stopResearch}
                  className="mx-2 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 font-mono text-[10px] uppercase tracking-widest hover:bg-red-500/20 transition-all flex items-center gap-2">
                  <span className="w-2 h-2 rounded-sm bg-red-400" /> Stop
                </button>
              ) : (
                <button onClick={startResearch} disabled={!query.trim()}
                  className="mx-2 px-4 py-2.5 rounded-xl bg-indigo-500 hover:bg-indigo-400 disabled:bg-white/5 disabled:text-white/20 text-white font-semibold transition-all flex items-center gap-2 shrink-0">
                  <ArrowRight size={15} />
                </button>
              )}
            </div>
          </div>

          {/* Depth + reset */}
          <div className="flex items-center justify-between">
            <DepthPicker value={depth} onChange={setDepth} />
            {(showResults || done) && (
              <button onClick={reset}
                className="flex items-center gap-1.5 font-mono text-[10px] text-white/25 hover:text-white/60 uppercase tracking-widest transition-colors">
                <RefreshCw size={11} /> New Research
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Empty / quick prompts ────────────────────────────────────────── */}
      <AnimatePresence>
        {!showResults && !done && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex-1 flex flex-col items-center justify-center gap-6 p-8"
          >
            <div className="flex flex-col items-center gap-3">
              <div className="p-4 rounded-full bg-indigo-500/10 border border-indigo-500/20">
                <Globe size={28} className="text-indigo-400" />
              </div>
              <p className="font-mono text-[11px] text-white/25 uppercase tracking-widest">
                Multi-round · Full page reading · Gap analysis · Cited report
              </p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-xl">
              {QUICK.map(q => (
                <button key={q} onClick={() => setQuery(q)}
                  className="px-3 py-2 rounded-xl border border-white/[0.07] bg-white/[0.02] text-white/40 text-xs hover:text-white/70 hover:bg-white/[0.05] hover:border-white/15 transition-all">
                  {q}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Results layout ───────────────────────────────────────────────── */}
      {showResults && (
        <div className="flex-1 flex overflow-hidden">

          {/* Left: research log */}
          <div className="w-[260px] shrink-0 border-r border-white/[0.05] flex flex-col overflow-hidden">
            <button
              onClick={() => setLogOpen(o => !o)}
              className="flex items-center justify-between px-4 py-3 border-b border-white/[0.05] hover:bg-white/[0.02] transition-colors shrink-0"
            >
              <div className="flex items-center gap-2">
                {running
                  ? <Radio size={11} className="text-indigo-400 animate-pulse" />
                  : <CheckCircle2 size={11} className="text-emerald-400/70" />
                }
                <span className="font-mono text-[10px] text-white/40 uppercase tracking-widest">
                  Research Log
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className="font-mono text-[9px] text-white/20">{log.length}</span>
                {logOpen ? <ChevronUp size={11} className="text-white/20" /> : <ChevronDown size={11} className="text-white/20" />}
              </div>
            </button>

            {logOpen && (
              <div ref={logRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-0.5 custom-scrollbar">
                <AnimatePresence initial={false}>
                  {log.map(entry => <LogRow key={entry.id} entry={entry} />)}
                </AnimatePresence>
                {running && (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex items-center gap-2 py-2"
                  >
                    <Loader2 size={10} className="text-indigo-400/60 animate-spin" />
                    <span className="font-mono text-[10px] text-white/20">researching…</span>
                  </motion.div>
                )}
              </div>
            )}
          </div>

          {/* Right: report */}
          <div className="flex-1 overflow-y-auto custom-scrollbar">
            <div className="max-w-2xl mx-auto px-8 py-6">

              {/* Query heading */}
              <div className="mb-6">
                <div className="flex items-center gap-2 mb-2">
                  <Sparkles size={13} className="text-indigo-400/70" />
                  <span className="font-mono text-[10px] text-white/25 uppercase tracking-widest">Research Report</span>
                </div>
                <h1 className="text-xl font-bold text-white leading-snug">{query}</h1>
              </div>

              {/* Error */}
              {error && (
                <div className="p-4 rounded-xl bg-red-500/10 border border-red-500/20 text-red-300 text-sm mb-4 flex items-start gap-3">
                  <AlertCircle size={14} className="mt-0.5 shrink-0" />
                  {error}
                </div>
              )}

              {/* Report skeleton while loading */}
              {running && !report && (
                <div className="space-y-3 animate-pulse">
                  {[80, 60, 90, 50, 75, 65].map((w, i) => (
                    <div key={i} className="h-3 rounded bg-white/[0.05]" style={{ width: `${w}%` }} />
                  ))}
                </div>
              )}

              {/* Report content */}
              <AnimatePresence>
                {report && (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.4 }}
                  >
                    <MarkdownReport content={report} sources={sources} />
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Sources */}
              {sources.length > 0 && (
                <div className="mt-8 pt-6 border-t border-white/[0.06]">
                  <button
                    onClick={() => setSourcesOpen(o => !o)}
                    className="flex items-center gap-2 mb-4 group"
                  >
                    <BookOpen size={13} className="text-white/30" />
                    <span className="font-mono text-[10px] text-white/35 uppercase tracking-widest group-hover:text-white/60 transition-colors">
                      {sources.length} Sources
                    </span>
                    {sourcesOpen
                      ? <ChevronUp size={11} className="text-white/20" />
                      : <ChevronDown size={11} className="text-white/20" />
                    }
                  </button>

                  {sourcesOpen && (
                    <div className="space-y-2">
                      {sources.map(src => (
                        <a key={src.index} href={src.url} target="_blank" rel="noreferrer"
                          className="flex items-start gap-3 p-3 rounded-xl border border-white/[0.05] bg-white/[0.02] hover:bg-white/[0.05] hover:border-white/10 transition-all group"
                        >
                          <span className="shrink-0 font-mono text-[10px] text-indigo-400/70 bg-indigo-500/10 border border-indigo-500/20 rounded px-1.5 py-0.5 mt-0.5">
                            {src.index}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <p className="text-xs font-medium text-white/70 group-hover:text-white truncate transition-colors">
                                {src.title}
                              </p>
                              <ExternalLink size={10} className="text-white/20 shrink-0" />
                            </div>
                            {src.snippet && (
                              <p className="text-[10px] text-white/30 mt-0.5 line-clamp-2 leading-relaxed">
                                {src.snippet}
                              </p>
                            )}
                            <p className="font-mono text-[9px] text-indigo-400/40 mt-1 truncate">
                              {src.url}
                            </p>
                          </div>
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Done badge */}
              {done && report && (
                <motion.div
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-8 flex items-center gap-2 text-emerald-400/60"
                >
                  <CheckCircle2 size={13} />
                  <span className="font-mono text-[10px] uppercase tracking-widest">
                    Research complete · {sources.length} sources · depth {depth}
                  </span>
                </motion.div>
              )}

            </div>
          </div>
        </div>
      )}
    </div>
  );
};
