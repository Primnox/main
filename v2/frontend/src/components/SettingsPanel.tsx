import { useCallback, useEffect, useState } from 'react';
import { Loader2, SlidersHorizontal, X } from 'lucide-react';
import { API } from '../lib/crs';
import { ModelProfiles } from './ModelProfiles';
import { ThemePicker } from './ThemePicker';
import { Tunables } from './Tunables';
import { Button, Choice, Field, SectionHeader } from './ui';

export function SettingsPanel({ onClose, embedded }: {
  onClose?: () => void;
  /** A section beside the rail, not an overlay over the app. */
  embedded?: boolean;
}) {
  const [data, setData] = useState<any>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [key, setKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch(`${API}/settings`).then(r => r.json()).then(d => {
      setData(d);
      setDraft({ ...d.effective });
    }).catch(() => setData(null));
  }, []);
  useEffect(load, [load]);

  const save = useCallback(async () => {
    setSaving(true); setNote(null);
    try {
      const body: any = { settings: draft };
      // Only sent when typed. An empty field must not be read as "clear the
      // key" — that would wipe a working config every time the panel is saved.
      if (key.trim()) body.api_key = key.trim();
      const r = await fetch(`${API}/settings`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      setData(d); setDraft({ ...d.effective }); setKey('');
      const bad = Object.entries(d.rejected ?? {});
      setNote(bad.length
        ? bad.map(([k, v]) => `${k}: ${v}`).join(' · ')
        : 'Saved. Applies from the next message.');
    } finally { setSaving(false); }
  }, [draft, key]);

  /* Thin wrappers over the shared primitives rather than a private control set.
     The old local versions used a <span> as the label — visually right, but not
     bound to the input, so clicking the caption did nothing and a screen reader
     read the field as unnamed. Field/Choice use a real <label htmlFor>, and the
     segmented control announces itself as a radiogroup. */
  const field = (label: string, k: string, placeholder = '', hint?: string) => (
    <Field label={label} placeholder={placeholder} hint={hint}
      value={draft[k] ?? ''}
      onChange={(e: any) => setDraft(d => ({ ...d, [k]: e.target.value }))} />
  );

  const choice = (label: string, k: string, options: string[], hint?: string) => (
    <Choice label={label} hint={hint} value={draft[k] ?? ''}
      options={options.map(o => ({ value: o, label: o || 'off' }))}
      onChange={v => setDraft(d => ({ ...d, [k]: v }))} />
  );

  return (
    <div className={embedded
      ? 'h-full w-full min-w-0 bg-surface flex flex-col'
      : 'fixed inset-0 z-50 bg-surface flex flex-col'}>
      <header className="h-14 shrink-0 flex items-center gap-3 px-6 border-b border-on-surface/[0.07]">
        <SlidersHorizontal size={15} className="text-on-surface/60" />
        <span className="font-display font-bold text-[13px] uppercase tracking-[0.18em]">Settings</span>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={save} disabled={saving} variant="quiet" size="sm">
            {saving ? <Loader2 size={12} className="px-spin" /> : 'Save'}
          </Button>
          {onClose && (
            <button onClick={onClose} aria-label="Close settings"
              className="p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition-all duration-200">
              <X size={16} />
            </button>
          )}
        </div>
      </header>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <div className="max-w-xl mx-auto px-8 py-8 space-y-8">
          {note && <p className="text-[12px] text-on-surface/70">{note}</p>}

          {/* First, because it is the one setting whose effect is visible the
              instant it changes — and because it needs no Save, unlike
              everything below it. */}
          <ThemePicker />

          <Tunables />

          <ModelProfiles onChanged={load} />

          <section className="space-y-4">
            <SectionHeader title="Provider (advanced)" level={3}
              note="Edited directly. Activating a profile above overwrites these." />
            {field('Base URL', 'provider.base_url', 'https://api.anthropic.com')}
            {field('Model', 'provider.model', 'claude-opus-4-8')}
            {choice('API type', 'provider.api_type', ['anthropic', 'openai'])}

            <label className="block space-y-1.5">
              <span className="px-label block">API key</span>
              <input type="password" value={key} onChange={e => setKey(e.target.value)}
                placeholder={data?.api_key_present ? '•••••••• stored' : 'not set'}
                className="w-full bg-transparent border border-on-surface/[0.12] rounded-xl px-4 py-2.5 text-sm outline-none focus-visible:border-on-surface/40 placeholder:text-on-surface/25" />
              <span className="block text-[11px] text-on-surface/40">
                Written to {data?.env_file ?? 'v2/.env'}, never to the database and
                never shown back. Leave blank to keep the current one.
              </span>
            </label>
          </section>

          <section className="space-y-4">
            <SectionHeader title="Sandbox" level={3} />
            {choice('Permission prompts', 'sandbox.auto_approve', ['all', 'safe', 'off'],
              'all = never ask · safe = ask for shell only · off = always ask')}
          </section>

          <section className="space-y-4">
            <SectionHeader title="Diagnostics" level={3} />
            {choice('Record a trace per turn', 'diagnostics.trace', ['', '1'],
              'Blank is off. Traces let a turn be replayed exactly.')}
            {choice('Force the echo provider', 'provider.force_echo', ['', 'echo'],
              'No network, no key. Tells a runtime bug apart from a provider problem.')}
          </section>

          {data?.status && (
            <section className="space-y-2 pt-4 border-t border-on-surface/[0.07]">
              <SectionHeader title="Status" level={3} />
              {Object.entries(data.status).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 text-[12px]">
                  <span className="text-on-surface/45">{k}</span>
                  <span className="text-on-surface/80 truncate">{String(v)}</span>
                </div>
              ))}
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

