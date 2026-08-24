import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Check, Download, Loader2, Pin, RefreshCw, StickyNote, Trash2, Upload, Zap,
} from 'lucide-react';
import { API, api, type ModelHealth } from '../lib/crs';
import { Button, EmptyState, SectionHeader } from './ui';
import { GuideInline } from './GuideInline';

/* The providers you actually configured.
 *
 * This used to be the whole Providers tab: four seeded rows, three of which
 * had no key and could not answer anything. The catalogue below took over
 * "what exists"; this answers "what have I got, and does it work" — which is
 * a different question and was the one with no answer at all.
 *
 * WHAT CHANGED, AND WHY. Every row could previously be activated and nothing
 * else. You could not tell whether a profile's key still worked without
 * sending a message and watching the turn fail, which is the most expensive
 * possible place to discover a revoked credential. So each row now carries:
 *
 *   a status dot fed by the routing circuits, so a provider the chain has
 *   benched looks benched here rather than looking fine;
 *   Test, which probes the endpoint with the stored key and says what came
 *   back — reachable, rejected, or unreachable, in the provider's own terms;
 *   a note, because "which account does this bill to" is a real question that
 *   the vendor's own hint text cannot answer.
 *
 * Keys are never read back to this screen. `has_key` is a boolean and that is
 * the entire surface: a settings screen that can show you your own key is one
 * that can show it to whoever is behind you.
 */

type TestResult = {
  ok: boolean;
  reason: string;
  error: string;
  latency_ms: number;
  models: string[];
  status: number | null;
};

/* Status is derived from two sources that can disagree, and the disagreement
   is the interesting part: a probe says whether the endpoint answers RIGHT
   NOW, and the circuit says what the chain has learned from real turns. A
   provider that probes fine but keeps failing mid-conversation is exactly the
   case a single indicator would hide. */
function statusOf(open: boolean, tested: TestResult | undefined, hasKey: boolean,
                  needsKey: boolean) {
  if (open) return { tone: 'bg-warn', label: 'benched by routing' };
  if (tested) {
    return tested.ok
      ? { tone: 'bg-success', label: `reachable · ${tested.latency_ms}ms` }
      : { tone: 'bg-error', label: tested.reason.replace(/_/g, ' ') };
  }
  if (needsKey && !hasKey) return { tone: 'bg-warn', label: 'no key' };
  return { tone: 'bg-on-surface/25', label: 'not tested' };
}

function RowSkeleton() {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-on-surface/[0.07] px-4 py-3">
      <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-on-surface/15" />
      <span className="min-w-0 flex-1 space-y-1.5">
        <span className="block h-3 w-32 rounded bg-on-surface/[0.07]" />
        <span className="block h-2.5 w-52 rounded bg-on-surface/[0.05]" />
      </span>
    </div>
  );
}

export function ModelProfiles({ onChanged }: { onChanged: () => void }) {
  const [data, setData] = useState<any>(null);
  const [health, setHealth] = useState<ModelHealth | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [tested, setTested] = useState<Record<string, TestResult>>({});
  const [noting, setNoting] = useState<string | null>(null);
  const [noteDraft, setNoteDraft] = useState('');
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [favourites, setFavourites] = useState<string[]>([]);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    fetch(`${API}/models`).then(r => r.json()).then(d => {
      setData(d);
      // Both arrive with the profile list now. They used to ride along on the
      // catalogue payload, which no longer exists — and a second round trip
      // for two dictionaries read on the same screen was never worth it.
      setNotes(d.notes ?? {});
      setFavourites(d.favourites ?? []);
    }).catch(() => setData(null));
    api.modelHealth().then(setHealth).catch(() => setHealth(null));
  }, []);
  useEffect(load, [load]);

  /* Circuits are keyed by endpoint + model, which is right for routing and
     wrong for a list keyed by profile name. Matching on the endpoint prefix is
     what lets a row show the state of whichever model it currently has
     selected without the backend having to duplicate the record per profile. */
  const openEndpoints = useMemo(() => new Set(
    (health?.circuits ?? []).filter(c => c.open).map(c => c.key.split('|')[0])
  ), [health]);

  const act = useCallback(async (name: string, run: () => Promise<any>) => {
    setBusy(name);
    try { const next = await run(); if (next?.profiles) setData(next); }
    finally { setBusy(null); }
  }, []);

  const activate = (name: string) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/activate`, { method: 'POST' });
    const next = await r.json();
    onChanged();
    return next;
  });

  const test = (name: string) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/test`, { method: 'POST' });
    const result: TestResult = await r.json();
    setTested(t => ({ ...t, [name]: result }));
    api.modelHealth().then(setHealth).catch(() => undefined);
    return null;
  });

  const testAll = () => act('__all__', async () => {
    const r = await fetch(`${API}/models/test-all`, { method: 'POST' });
    const { results } = await r.json();
    setTested(Object.fromEntries(results.map((x: any) => [x.profile, x])));
    api.modelHealth().then(setHealth).catch(() => undefined);
    return null;
  });

  const discover = (name: string) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/discover`, { method: 'POST' });
    return r.json();
  });

  const chooseModel = (name: string, model: string) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/model`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model }),
    });
    onChanged();
    return r.json();
  });

  const remove = (name: string) => act(name, async () => {
    await fetch(`${API}/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
    load(); onChanged();
    return null;
  });

  const pin = (name: string, pinned: boolean) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/favourite`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pinned }),
    });
    setFavourites((await r.json()).favourites);
    return null;
  });

  const saveNote = (name: string) => act(name, async () => {
    const r = await fetch(`${API}/models/${encodeURIComponent(name)}/note`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note: noteDraft }),
    });
    setNotes((await r.json()).notes);
    setNoting(null);
    return null;
  });

  const exportProfiles = useCallback(async () => {
    const payload = await fetch(`${API}/models/export`).then(r => r.json());
    // A data: URL rather than a blob download — the app runs in a Tauri shell
    // where a synthesised download is not guaranteed to reach a save dialog,
    // and the clipboard always works.
    await navigator.clipboard?.writeText(JSON.stringify(payload, null, 2));
    setImportError(null);
    setNoting('__exported__');
    window.setTimeout(() => setNoting(n => (n === '__exported__' ? null : n)), 2200);
  }, []);

  const importProfiles = useCallback(async (file: File) => {
    setImportError(null);
    try {
      const parsed = JSON.parse(await file.text());
      const r = await fetch(`${API}/models/import`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed),
      });
      if (!r.ok) throw new Error((await r.json()).detail ?? 'Import failed.');
      setData(await r.json());
      load(); onChanged();
    } catch (e: any) {
      setImportError(String(e?.message ?? e));
    }
  }, [load, onChanged]);

  const profiles = (data?.profiles ?? []) as any[];
  const sorted = useMemo(() => [...profiles].sort((a, b) =>
    Number(favourites.includes(b.name)) - Number(favourites.includes(a.name))
    || Number(b.active) - Number(a.active)
    || a.name.localeCompare(b.name)), [profiles, favourites]);

  return (
    <section className="space-y-3">
      <SectionHeader title="Your providers" level={3}
        note="What you configured, and whether it still works. Keys live in the OS keyring and are never read back to this screen."
        right={
          <span className="flex items-center gap-1">
            <Button size="sm" variant="quiet" onClick={testAll}
              disabled={busy !== null || profiles.length === 0}>
              {busy === '__all__' ? <Loader2 size={11} className="px-spin" /> : 'Test all'}
            </Button>
            <Button size="sm" variant="quiet" onClick={exportProfiles}
              disabled={profiles.length === 0} aria-label="Copy an export to the clipboard">
              <Download size={11} />
            </Button>
            <Button size="sm" variant="quiet" onClick={() => fileInput.current?.click()}
              aria-label="Import profiles from a file">
              <Upload size={11} />
            </Button>
          </span>
        } />

      <input ref={fileInput} type="file" accept="application/json" className="sr-only"
        onChange={e => { const f = e.target.files?.[0]; if (f) importProfiles(f); e.target.value = ''; }} />

      {noting === '__exported__' && (
        <p className="text-[11px] text-success">
          Copied to the clipboard, without any keys — an export is a file that gets
          mailed and committed by accident, so it never carries a credential.
        </p>
      )}
      {importError && <p className="text-[11px] text-error">{importError}</p>}

      {data && !data.keyring && (
        <p className="text-[11px] text-warn">
          No OS keyring on this machine — profiles save, but keys cannot.
        </p>
      )}

      {data?.ollama && (
        <div className="flex items-center gap-2 rounded-lg border border-on-surface/[0.07] px-3 py-2 text-[11px]">
          <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${data.ollama.running ? 'bg-success' : 'bg-warn'}`} />
          <span className="text-on-surface/60">
            Ollama {data.ollama.running
              ? `running · ${data.ollama.models.length} model${data.ollama.models.length === 1 ? '' : 's'} installed`
              : `not reachable at ${data.ollama.host}`}
          </span>
        </div>
      )}

      {!data && <div className="space-y-1.5" aria-busy="true"><RowSkeleton /><RowSkeleton /></div>}

      {data && sorted.length === 0 && (
        <EmptyState title="Nothing configured">
          Every provider below is one click and a key away. Ollama needs neither —
          if it is running on this machine, add it and Primnox works with no
          account at all.
        </EmptyState>
      )}

      {/* Attached to the list whose rows fail, not filed in a tab. The moment
          someone needs this is the moment a Test just came back red, and they
          are already looking at this section. */}
      {sorted.length > 0 && (
        <GuideInline slug="when-a-provider-breaks" label="Something stopped working" />
      )}

      {sorted.map((p: any) => {
        const result = tested[p.name];
        const isOpen = openEndpoints.has((p.base_url ?? '').replace(/\/$/, ''));
        const status = statusOf(isOpen, result, p.has_key, p.kind !== 'ollama' && p.kind !== 'local');
        const pinned = favourites.includes(p.name);
        return (
          <div key={p.name}
            className={`group rounded-xl border transition duration-150
              ${p.active
                ? 'border-on-surface/35 bg-on-surface/[0.03]'
                : 'border-on-surface/[0.07] hover:border-on-surface/[0.18]'}`}>
            {/* Wraps rather than compresses. Six controls and a model picker
                do not fit beside a name at 375px, and the failure mode of
                `shrink-0` in a nowrap row is that the last two buttons sit
                past the right edge where nothing can reach them. */}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-3">
              <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${status.tone}`}
                aria-hidden="true" />
              <button onClick={() => activate(p.name)} disabled={busy !== null || p.active}
                className="min-w-0 flex-1 basis-[12rem] text-left disabled:cursor-default">
                <span className="block truncate text-sm">
                  {p.name}
                  {p.active && <span className="px-label ml-2">active</span>}
                </span>
                <span className="px-label mt-0.5 block truncate normal-case tracking-normal">
                  {status.label} · {p.base_url}
                </span>
              </button>

              {/* The picker and the six actions travel together, so they wrap
                  to their own line as a unit instead of breaking up mid-row. */}
              <span className="ml-auto flex flex-wrap items-center justify-end gap-1">
              <select value={p.model} disabled={busy !== null} aria-label={`Model for ${p.name}`}
                onChange={e => chooseModel(p.name, e.target.value)}
                className="mr-2 min-w-0 max-w-[150px] shrink rounded-lg border border-on-surface/[0.12] bg-transparent px-2 py-1 text-[11px] outline-none focus-visible:border-on-surface/40">
                {(p.models?.length ? p.models : [p.model]).map((m: string) => (
                  <option key={m} value={m} className="bg-surface">{m}</option>
                ))}
              </select>

              <button onClick={() => test(p.name)} disabled={busy !== null}
                title="Probe this endpoint with its stored key"
                aria-label={`Test ${p.name}`}
                className="px-interactive shrink-0 rounded-lg p-1.5 text-on-surface/50 hover:bg-on-surface/[0.05] hover:text-on-surface">
                {busy === p.name ? <Loader2 size={12} className="px-spin" /> : <Zap size={12} />}
              </button>
              <button onClick={() => discover(p.name)} disabled={busy !== null}
                title="Ask the provider what models it offers"
                aria-label={`Refresh models for ${p.name}`}
                className="px-interactive shrink-0 rounded-lg p-1.5 text-on-surface/50 hover:bg-on-surface/[0.05] hover:text-on-surface">
                <RefreshCw size={12} />
              </button>
              <button onClick={() => pin(p.name, !pinned)} disabled={busy !== null}
                aria-pressed={pinned} aria-label={`${pinned ? 'Unpin' : 'Pin'} ${p.name}`}
                className={`px-interactive shrink-0 rounded-lg p-1.5 hover:bg-on-surface/[0.05]
                  ${pinned ? 'text-primary' : 'text-on-surface/50 hover:text-on-surface'}`}>
                <Pin size={12} />
              </button>
              <button onClick={() => { setNoting(noting === p.name ? null : p.name); setNoteDraft(notes[p.name] ?? ''); }}
                aria-label={`Note for ${p.name}`} aria-expanded={noting === p.name}
                className={`px-interactive shrink-0 rounded-lg p-1.5 hover:bg-on-surface/[0.05]
                  ${notes[p.name] ? 'text-on-surface/70' : 'text-on-surface/50 hover:text-on-surface'}`}>
                <StickyNote size={12} />
              </button>
              <button onClick={() => remove(p.name)} disabled={busy !== null}
                aria-label={`Delete profile ${p.name}`}
                className="px-interactive shrink-0 rounded-lg p-1.5 text-on-surface/50 opacity-0 hover:bg-warn/10 hover:text-warn focus-visible:opacity-100 group-hover:opacity-100">
                <Trash2 size={13} />
              </button>
              </span>
            </div>

            {/* The probe's own words, not a re-worded summary. A provider that
                says "insufficient balance" is telling the user something a
                generic "connection failed" would throw away. */}
            {result && !result.ok && (
              <p className="border-t border-on-surface/[0.07] px-4 py-2 text-[11px] leading-relaxed text-error">
                {result.error}
              </p>
            )}
            {result?.ok && result.models.length > 0 && (
              <p className="border-t border-on-surface/[0.07] px-4 py-2 text-[11px] text-on-surface/50">
                {result.models.length} model{result.models.length === 1 ? '' : 's'} offered ·
                first token path not tested — some endpoints serve a model list and
                still refuse completions.
              </p>
            )}
            {notes[p.name] && noting !== p.name && (
              <p className="border-t border-on-surface/[0.07] px-4 py-2 text-[11px] text-on-surface/50">
                {notes[p.name]}
              </p>
            )}
            {noting === p.name && (
              <div className="flex items-center gap-2 border-t border-on-surface/[0.07] px-4 py-2">
                <input value={noteDraft} onChange={e => setNoteDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveNote(p.name); }}
                  placeholder="Which account does this bill to?"
                  aria-label={`Note for ${p.name}`}
                  className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-on-surface/50" />
                <Button size="sm" variant="quiet" onClick={() => saveNote(p.name)}>
                  <Check size={11} />
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </section>
  );
}
