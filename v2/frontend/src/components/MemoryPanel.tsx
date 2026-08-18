import { useCallback, useEffect, useState } from 'react';
import { Brain, Search, Trash2, X } from 'lucide-react';
import { API } from '../lib/crs';
import { Chip, Field } from './ui';

/* ── Permanent memory ───────────────────────────────────────────────────────
   What Primnox knows about you, as opposed to what it knows about your files.
   Separate surface because the two have different lifetimes: the graph is
   rebuilt from source whenever source changes, and this is only ever changed
   by you. */
export function MemoryPanel({ onClose, embedded }: {
  onClose?: () => void;
  /** A section beside the rail, not an overlay over the app. */
  embedded?: boolean;
}) {
  const [rows, setRows] = useState<any[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [query, setQuery] = useState('');
  const [draft, setDraft] = useState('');
  const [category, setCategory] = useState('personal');
  const [busy, setBusy] = useState(false);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback((q = '') => {
    const url = q.trim() ? `${API}/memories?q=${encodeURIComponent(q)}` : `${API}/memories`;
    fetch(url).then(r => r.json()).then(d => {
      setRows(d.memories ?? []);
      setStats(d.stats ?? null);
      setCategories(d.categories ?? []);
    }).catch(() => setRows([]));
  }, []);
  useEffect(() => { load(); }, [load]);

  const add = useCallback(async () => {
    if (!draft.trim()) return;
    setBusy(true); setNote(null);
    try {
      const r = await fetch(`${API}/memories`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: draft.trim(), category }),
      });
      const d = await r.json();
      // Saying so matters: a silent no-op on a near-duplicate looks like the
      // save failed, and the user writes it again.
      setNote(d.stored ? 'Saved.' : 'Already known — nothing added.');
      setDraft('');
      load(query);
    } finally { setBusy(false); }
  }, [draft, category, load, query]);

  const forget = useCallback(async (id: string) => {
    await fetch(`${API}/memories/${id}`, { method: 'DELETE' });
    load(query);
  }, [load, query]);

  const wipe = useCallback(async () => {
    await fetch(`${API}/memories`, { method: 'DELETE' });
    setConfirmWipe(false); setNote('Everything forgotten.');
    load();
  }, [load]);

  return (
    <div className={embedded
      ? 'h-full w-full min-w-0 bg-surface flex flex-col'
      : 'fixed inset-0 z-50 bg-surface flex flex-col'}>
      <header className="h-14 shrink-0 flex items-center gap-3 px-6 border-b border-on-surface/[0.07]">
        <Brain size={15} className="text-on-surface/60" />
        <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">
          Memory
        </span>
        {stats && (
          <span className="px-label ml-1">
            {stats.total} kept{stats.forgotten ? ` · ${stats.forgotten} forgotten` : ''}
          </span>
        )}
        <div className="ml-auto flex items-center gap-2">
          <div className="flex items-center gap-2 border border-on-surface/[0.12] rounded-lg px-2.5 py-1.5 w-56">
            <Search size={12} className="text-on-surface/40 shrink-0" aria-hidden="true" />
            {/* Named, not just hinted. The magnifier says "search" to someone
                who can see it; the label says it to everyone else, and it
                survives the placeholder disappearing on the first keystroke. */}
            <label htmlFor="memory-search" className="sr-only">Search memories</label>
            <input id="memory-search" type="search" value={query}
              onChange={e => { setQuery(e.target.value); load(e.target.value); }}
              placeholder="Search memories…"
              className="flex-1 bg-transparent text-[12px] outline-none placeholder:text-on-surface/30" />
          </div>
          {onClose && (
            <button onClick={onClose} aria-label="Close memory"
              className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition-all duration-200">
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-2xl mx-auto px-8 py-8 space-y-8">

          <section className="space-y-3">
            <p className="px-eyebrow">Add one by hand</p>
            <p className="text-[12px] text-on-surface/45 -mt-1">
              Usually you will not need this. Say “remember that…” in any chat
              and it is saved from there, with the conversation it came from
              attached. This screen is for reviewing and forgetting.
            </p>
            <Field as="textarea" label="What to remember" hideLabel
              value={draft} onChange={(e: any) => setDraft(e.target.value)}
              onKeyDown={(e: any) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) add(); }}
              rows={2} placeholder="I prefer concise answers and dark themes."
              className="resize-none" />
            <div className="flex items-center gap-2">
              <select value={category} onChange={e => setCategory(e.target.value)}
                aria-label="Category"
                className="bg-transparent border border-on-surface/[0.12] rounded-lg px-2.5 py-1.5 text-[12px] outline-none focus-visible:border-on-surface/40">
                {categories.map(c => (
                  <option key={c} value={c} className="bg-surface">{c}</option>
                ))}
              </select>
              <button onClick={add} disabled={busy || !draft.trim()}
                className="px-3.5 py-1.5 rounded-lg border border-on-surface/[0.12] hover:border-on-surface/25 text-[11px] uppercase tracking-[0.1em] disabled:opacity-40 transition-all duration-200">
                Remember
              </button>
              {note && <span className="text-[12px] text-on-surface/55">{note}</span>}
            </div>
          </section>

          <section className="space-y-2">
            <p className="px-eyebrow">
              {query ? `Matching “${query}”` : 'Everything it knows'}
            </p>
            {rows.length === 0 && (
              <p className="text-sm text-on-surface/45 py-6">
                {query
                  ? 'Nothing matches.'
                  : 'Nothing remembered yet. Tell Primnox something worth keeping in a chat — “remember that I prefer short answers” — and it appears here.'}
              </p>
            )}
            {rows.map(m => (
              <div key={m.id}
                className="group flex items-start gap-3 px-4 py-3 rounded-xl border border-on-surface/[0.07] hover:border-on-surface/[0.16] transition-all duration-200">
                <div className="min-w-0 flex-1">
                  <p className="text-sm leading-relaxed">{m.text}</p>
                  {/* Where a fact came from is the difference between a fact, a
                      guess, and someone else's data. Three values, not a
                      boolean: an `imported` memory falling through to "you said"
                      tells the user they stated something they never did, which
                      is the one mistake a memory list must not make.

                      As Chips rather than <span title=…>: the explanation used
                      to live in a tooltip, which is unreachable by keyboard,
                      unreachable on touch, and unreliably announced. Chip turns
                      it into a real disclosure anyone can open. */}
                  <div className="mt-2 flex flex-wrap items-start gap-2">
                    <Chip>{m.category ?? 'personal'}</Chip>
                    {m.provenance === 'inferred_chat'
                      ? <Chip tone="primary" detail="Primnox decided this was worth keeping while you were talking — you did not ask for it.">inferred</Chip>
                      : m.provenance === 'imported'
                        ? <Chip tone="warn" detail="Loaded from an imported dataset. You never said it in a chat.">imported</Chip>
                        : <Chip tone="success" detail="You asked for this to be kept.">you said</Chip>}
                  </div>
                </div>
                <button onClick={() => forget(m.id)} aria-label={`Forget: ${m.text.slice(0, 40)}`}
                  className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1.5 rounded-lg text-on-surface/40 hover:text-warn hover:bg-warn/10 transition-all duration-200">
                  <Trash2 size={13} />
                </button>
              </div>
            ))}
          </section>

          {rows.length > 0 && (
            <section className="pt-4 border-t border-on-surface/[0.07]">
              {confirmWipe ? (
                <div className="flex items-center gap-2">
                  <span className="text-[13px] text-on-surface/70">Forget everything?</span>
                  <button onClick={wipe}
                    className="px-3 py-1.5 rounded-lg border border-warn/40 text-warn text-[11px] uppercase tracking-[0.1em] hover:bg-warn/10 transition-all duration-200">
                    Yes, forget all
                  </button>
                  <button onClick={() => setConfirmWipe(false)}
                    className="px-3 py-1.5 rounded-lg border border-on-surface/[0.12] text-[11px] uppercase tracking-[0.1em] hover:border-on-surface/25 transition-all duration-200">
                    Cancel
                  </button>
                </div>
              ) : (
                <button onClick={() => setConfirmWipe(true)}
                  className="text-[12px] text-on-surface/40 hover:text-warn transition-colors duration-200">
                  Forget everything
                </button>
              )}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

