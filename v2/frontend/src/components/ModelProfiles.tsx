import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { API } from '../lib/crs';

/* ── Settings ───────────────────────────────────────────────────────────────
   The thing whose absence meant configuring V2 was "find v2/.env, edit it,
   restart". Provider and model apply on the next turn because the gateway
   resolves from the environment on every call; the key is written to .env and
   is never read back. */
/* Saved model profiles. Switching endpoints used to mean retyping four fields
   and a key, so nobody switched — they edited .env and restarted. Keys live in
   the OS keyring, one entry per profile, and are never read back to the UI. */
export function ModelProfiles({ onChanged }: { onChanged: () => void }) {
  const [data, setData] = useState<any>(null);
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ name: '', base_url: '', api_type: 'openai', model: '', api_key: '' });
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    fetch(`${API}/models`).then(r => r.json()).then(setData).catch(() => setData(null));
  }, []);
  useEffect(load, [load]);

  const activate = useCallback(async (name: string) => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/models/${encodeURIComponent(name)}/activate`, { method: 'POST' });
      setData(await r.json());
      onChanged();
    } finally { setBusy(false); }
  }, [onChanged]);

  const save = useCallback(async () => {
    if (!draft.name.trim()) return;
    setBusy(true);
    try {
      const r = await fetch(`${API}/models`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...draft, activate: true }),
      });
      setData(await r.json());
      setDraft({ name: '', base_url: '', api_type: 'openai', model: '', api_key: '' });
      setAdding(false);
      onChanged();
    } finally { setBusy(false); }
  }, [draft, onChanged]);

  const remove = useCallback(async (name: string) => {
    await fetch(`${API}/models/${encodeURIComponent(name)}`, { method: 'DELETE' });
    load(); onChanged();
  }, [load, onChanged]);

  const chooseModel = useCallback(async (name: string, model: string) => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/models/${encodeURIComponent(name)}/model`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model }),
      });
      setData(await r.json());
      onChanged();
    } finally { setBusy(false); }
  }, [onChanged]);

  const discover = useCallback(async (name: string) => {
    setBusy(true);
    try {
      const r = await fetch(`${API}/models/${encodeURIComponent(name)}/discover`, { method: 'POST' });
      setData(await r.json());
    } finally { setBusy(false); }
  }, []);

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <p className="px-eyebrow">Models</p>
        <button onClick={() => setAdding(a => !a)}
          className="ml-auto text-[11px] uppercase tracking-[0.1em] text-on-surface/50 hover:text-on-surface transition-colors duration-200">
          {adding ? 'Cancel' : '+ Add'}
        </button>
      </div>

      {data && !data.keyring && (
        <p className="text-[11px] text-warn">
          No OS keyring on this machine — profiles save, but keys cannot.
        </p>
      )}

      {/* The engine, not just the endpoint. "Is Ollama even running" was
          previously a question you had to leave the app to answer. */}
      {data?.ollama && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg border border-on-surface/[0.07] text-[11px]">
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${data.ollama.running ? 'bg-success' : 'bg-warn'}`} />
          <span className="text-on-surface/60">
            Ollama {data.ollama.running
              ? `running · ${data.ollama.models.length} model${data.ollama.models.length === 1 ? '' : 's'} installed`
              : `not reachable at ${data.ollama.host}`}
          </span>
          {data.ollama.running && data.ollama.models.length > 0 && (
            <span className="ml-auto text-on-surface/35 truncate">
              {data.ollama.models.map((m: any) => `${m.name} (${m.size_gb}GB)`).join(' · ')}
            </span>
          )}
        </div>
      )}

      {(data?.profiles ?? []).map((p: any) => (
        <div key={p.name}
          className={`group flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-200
            ${p.active ? 'border-on-surface/35 bg-on-surface/[0.03]' : 'border-on-surface/[0.07] hover:border-on-surface/[0.18]'}`}>
          <button onClick={() => activate(p.name)} disabled={busy || p.active}
            className="min-w-0 flex-1 text-left">
            <span className="text-sm block truncate">
              {p.name}
              {p.active && <span className="px-label ml-2">active</span>}
            </span>
            <span className="px-label block mt-0.5 truncate normal-case tracking-normal">
              {p.api_type} · {p.base_url}
              {p.has_key ? ' · key saved' : ''}
            </span>
          </button>
          {/* One provider, many models. Switching Opus to Sonnet must not mean
              re-entering an endpoint and a key. */}
          <select value={p.model} disabled={busy} aria-label={`Model for ${p.name}`}
            onChange={e => chooseModel(p.name, e.target.value)}
            onClick={e => e.stopPropagation()}
            className="bg-transparent border border-on-surface/[0.12] rounded-lg px-2 py-1 text-[11px] outline-none focus-visible:border-on-surface/40 max-w-[150px]">
            {(p.models?.length ? p.models : [p.model]).map((m: string) => (
              <option key={m} value={m} className="bg-surface">{m}</option>
            ))}
          </select>
          <button onClick={() => discover(p.name)} disabled={busy}
            aria-label={`Refresh models for ${p.name}`} title="Ask the provider what it offers"
            className="p-1.5 rounded-lg text-on-surface/40 hover:text-on-surface hover:bg-on-surface/[0.05] transition-all duration-200">
            <RefreshCw size={12} />
          </button>
          <button onClick={() => remove(p.name)} aria-label={`Delete profile ${p.name}`}
            className="opacity-0 group-hover:opacity-100 focus-visible:opacity-100 p-1.5 rounded-lg text-on-surface/40 hover:text-warn hover:bg-warn/10 transition-all duration-200">
            <Trash2 size={13} />
          </button>
        </div>
      ))}

      {adding && (
        <div className="space-y-2 p-4 rounded-xl border border-on-surface/[0.12]">
          {([['name', 'Name'], ['model', 'Model'], ['base_url', 'Base URL']] as const).map(([k, label]) => (
            <input key={k} value={(draft as any)[k]} placeholder={label}
              onChange={e => setDraft(d => ({ ...d, [k]: e.target.value }))}
              className="w-full bg-transparent border border-on-surface/[0.12] rounded-lg px-3 py-2 text-[13px] outline-none focus-visible:border-on-surface/40 placeholder:text-on-surface/25" />
          ))}
          <input type="password" value={draft.api_key} placeholder="API key (optional)"
            onChange={e => setDraft(d => ({ ...d, api_key: e.target.value }))}
            className="w-full bg-transparent border border-on-surface/[0.12] rounded-lg px-3 py-2 text-[13px] outline-none focus-visible:border-on-surface/40 placeholder:text-on-surface/25" />
          <div className="flex gap-2">
            {['openai', 'anthropic'].map(t => (
              <button key={t} onClick={() => setDraft(d => ({ ...d, api_type: t }))}
                className={`px-3 py-1.5 rounded-lg border text-[12px] transition-all duration-200
                  ${draft.api_type === t ? 'border-on-surface/40 text-on-surface' : 'border-on-surface/[0.12] text-on-surface/55'}`}>
                {t}
              </button>
            ))}
            <button onClick={save} disabled={busy || !draft.name.trim()}
              className="ml-auto px-3.5 py-1.5 rounded-lg border border-on-surface/[0.12] hover:border-on-surface/25 text-[11px] uppercase tracking-[0.1em] disabled:opacity-40 transition-all duration-200">
              Save and use
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

