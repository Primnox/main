import { useCallback, useEffect, useState } from 'react';
import { Loader2, Maximize2, RefreshCw, Share2, X } from 'lucide-react';
import { API } from '../lib/crs';

/* ── Knowledge graph ────────────────────────────────────────────────────────
   The viewer is Graphify's own `to_html` export, served whole by the backend
   and shown in an iframe. Rebuilding it as a React component would mean
   reimplementing community colouring, node sizing and search against a graph
   library this project does not maintain, to land behind where upstream
   already is. V1 hand-rolled a react-force-graph view and it only ever showed
   notes; this shows the actual indexed corpus. */
export function GraphPanel({ onClose, initialScope, title, embedded }: {
  onClose?: () => void; initialScope?: string | null; title?: string;
  /** Rendered as a section beside the rail rather than over the whole app.
   *  A section has no close button — the rail is how you leave it. */
  embedded?: boolean;
}) {
  const [scopes, setScopes] = useState<any[]>([]);
  const [scope, setScope] = useState<string | null>(initialScope ?? null);
  const [all, setAll] = useState(false);
  const [indexing, setIndexing] = useState(false);
  const [target, setTarget] = useState('');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`${API}/knowledge/scopes`).then(r => r.json())
      .then(d => {
        const rows = d.scopes ?? [];
        setScopes(rows);
        setScope(s => s ?? (rows[0]?.scope ?? null));
      })
      .catch(() => setScopes([]));
  }, []);
  useEffect(load, [load]);

  const index = useCallback(async () => {
    if (!target.trim()) return;
    setIndexing(true); setError(null);
    try {
      const r = await fetch(`${API}/knowledge/index`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: target.trim() }),
      });
      if (!r.ok) throw new Error((await r.json()).detail ?? 'indexing failed');
      // Indexing is a background job, so the scope appears when it finishes
      // rather than when the request returns.
      const poll = setInterval(() => load(), 2000);
      setTimeout(() => { clearInterval(poll); setIndexing(false); load(); }, 30000);
    } catch (e: any) {
      setError(String(e.message ?? e)); setIndexing(false);
    }
  }, [target, load]);

  // Only frame a scope that actually has nodes. A conversation that has not
  // established anything yet has no scope row, and pointing the iframe at it
  // renders the backend's 404 body inside the panel — which looks like the
  // feature is broken rather than like there is nothing to show.
  const known = scope != null && scopes.some(s => s.scope === scope);
  const src = known
    ? `${API}/knowledge/view?scope=${encodeURIComponent(scope!)}${all ? '&limit=0' : ''}`
    : null;

  return (
    <div className={embedded
      ? 'h-full w-full min-w-0 bg-surface flex flex-col'
      : 'fixed inset-0 z-50 bg-surface flex flex-col'}>
      <header className="h-14 shrink-0 flex items-center gap-3 px-6 border-b border-on-surface/[0.07]">
        <Share2 size={15} className="text-on-surface/60" />
        <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">
          {title ?? 'Knowledge graph'}
        </span>
        <select value={scope ?? ''} onChange={e => setScope(e.target.value)}
          aria-label="Indexed scope"
          className="ml-3 bg-transparent border border-on-surface/[0.12] rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus-visible:border-on-surface/40">
          {scopes.length === 0 && <option value="">nothing yet</option>}
          {/* Grouped, because these are three different kinds of thing and a
              flat list implied they were comparable. An indexed repository is a
              developer's view of a codebase — 2,693 nodes of Primnox's own
              source sitting between two chats, under a heading that says "what
              Primnox knows", describes the application rather than the person
              using it. The groups say which is which without reading counts. */}
          {([
            ['facts', 'About you'],
            ['conversation', 'Conversations'],
            ['corpus', 'Indexed folders'],
          ] as const).map(([kind, heading]) => {
            const rows = scopes.filter(s => (s.kind ?? 'corpus') === kind);
            if (rows.length === 0) return null;
            return (
              <optgroup key={kind} label={heading}>
                {rows.map(s => (
                  <option key={s.scope} value={s.scope} className="bg-surface">
                    {s.label ?? s.scope} · {s.nodes} nodes
                  </option>
                ))}
              </optgroup>
            );
          })}
        </select>

        {scope === 'facts' && (
          <span className="px-label text-on-surface/45">
            memories · decisions · documents
          </span>
        )}

        <button onClick={() => setAll(a => !a)} title="Show every node instead of the community overview"
          className={`px-2.5 py-1.5 rounded-lg border text-[11px] transition-all duration-200
            ${all ? 'border-on-surface/35 text-on-surface' : 'border-on-surface/[0.12] text-on-surface/55 hover:text-on-surface/85'}`}>
          <Maximize2 size={12} className="inline mr-1.5 -mt-px" />
          {all ? 'All nodes' : 'Overview'}
        </button>

        <div className="ml-auto flex items-center gap-2">
          <label htmlFor="index-target" className="sr-only">Folder to index</label>
          <input id="index-target" value={target} onChange={e => setTarget(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') index(); }}
            placeholder="Folder to index…"
            className="w-56 bg-transparent border border-on-surface/[0.12] rounded-lg px-3 py-1.5 text-[12px] outline-none focus-visible:border-on-surface/40 placeholder:text-on-surface/30" />
          <button onClick={index} disabled={indexing || !target.trim()}
            className="px-3 py-1.5 rounded-lg border border-on-surface/[0.12] hover:border-on-surface/25 text-[11px] uppercase tracking-[0.1em] disabled:opacity-40 transition-all duration-200">
            {indexing ? <Loader2 size={12} className="px-spin" /> : 'Index'}
          </button>
          <button onClick={load} aria-label="Refresh scopes"
            className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition-all duration-200">
            <RefreshCw size={14} />
          </button>
          {onClose && (
            <button onClick={onClose} aria-label="Close knowledge graph"
              className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition-all duration-200">
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      {error && (
        <p className="px-6 py-2 text-[12px] text-warn border-b border-on-surface/[0.07]">{error}</p>
      )}

      {src ? (
        <iframe key={src} src={src} title="Knowledge graph" className="flex-1 w-full border-0" />
      ) : (
        <div className="flex-1 flex flex-col items-center justify-center gap-3 text-center px-8">
          <Share2 size={28} className="text-on-surface/25" />
          <p className="text-sm text-on-surface/60 max-w-sm">
            {initialScope
              ? 'This conversation has not established anything yet. Entities, files and decisions appear here as you discuss them.'
              : scope === 'facts'
                ? 'Nothing saved yet. Memories you keep, decisions made in chats, and documents you share appear here — this is what Primnox knows about you, not what is inside it.'
                : 'Nothing indexed under this scope. Point it at a folder of code or documents and it is extracted locally, with no model calls.'}
          </p>
        </div>
      )}
    </div>
  );
}

