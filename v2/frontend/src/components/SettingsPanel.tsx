import { useCallback, useEffect, useState } from 'react';
import { Loader2, SlidersHorizontal, X } from 'lucide-react';
import { Tabs } from '@base-ui-components/react/tabs';
import { API } from '../lib/crs';
import { ModelProfiles } from './ModelProfiles';
import { PrivacySettings } from './PrivacySettings';
import { ThemePicker } from './ThemePicker';
import { Tunables } from './Tunables';
import { VaultSettings } from './VaultSettings';
import { Button, Choice, Field, SectionHeader } from './ui';

/* Sub-navigated rather than one long scroll.
 *
 * It used to be seven sections stacked in a single column, which read fine
 * with three of them and stopped reading as anything once Privacy and Vault
 * joined Appearance, Tuning, Provider, Sandbox and Diagnostics — a settings
 * screen with seven independent concerns in one scroll is a screen where
 * finding the one you want means scanning past the other six every time.
 *
 * Base UI's Tabs rather than hand-rolled buttons + conditional rendering:
 * the same reason Choice sits on RadioGroup — roving tabindex and arrow-key
 * movement between tabs are required of a tablist, and neither falls out of
 * a row of buttons with an active className.
 *
 * The draft/Save mechanism stays in THIS component and is untouched by
 * which tab is showing — every field across every tab writes into the same
 * `draft` object, and Save sends all of it in one PATCH regardless of which
 * section is currently visible. Switching tabs must never look like undoing
 * an edit on a tab you're not looking at.
 */
type SettingsTab = 'appearance' | 'tuning' | 'provider' | 'privacy' | 'vault' | 'sandbox' | 'diagnostics';

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
  const [tab, setTab] = useState<SettingsTab>('appearance');

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

  const setDraftKey = useCallback((k: string, v: string) => setDraft(d => ({ ...d, [k]: v })), []);

  /* Thin wrappers over the shared primitives rather than a private control set.
     The old local versions used a <span> as the label — visually right, but not
     bound to the input, so clicking the caption did nothing and a screen reader
     read the field as unnamed. Field/Choice use a real <label htmlFor>, and the
     segmented control announces itself as a radiogroup. */
  const field = (label: string, k: string, placeholder = '', hint?: string) => (
    <Field label={label} placeholder={placeholder} hint={hint}
      value={draft[k] ?? ''}
      onChange={(e: any) => setDraftKey(k, e.target.value)} />
  );

  const choice = (label: string, k: string, options: string[], hint?: string) => (
    <Choice label={label} hint={hint} value={draft[k] ?? ''}
      options={options.map(o => ({ value: o, label: o || 'off' }))}
      onChange={v => setDraftKey(k, v)} />
  );

  const TABS: { id: SettingsTab; label: string }[] = [
    { id: 'appearance', label: 'Appearance' },
    { id: 'tuning', label: 'Tuning' },
    { id: 'provider', label: 'Provider' },
    { id: 'privacy', label: 'Privacy' },
    { id: 'vault', label: 'Vault' },
    { id: 'sandbox', label: 'Sandbox' },
    { id: 'diagnostics', label: 'Diagnostics' },
  ];

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

      <Tabs.Root value={tab} onValueChange={v => setTab(v as SettingsTab)}
        className="flex-1 min-h-0 flex flex-col">
        <Tabs.List
          className="shrink-0 flex gap-1 px-8 pt-4 overflow-x-auto border-b border-on-surface/[0.07]">
          {TABS.map(t => (
            <Tabs.Tab key={t.id} value={t.id}
              className="px-interactive shrink-0 px-3 py-2 text-[11px] uppercase tracking-[0.1em]
                         text-on-surface/50 border-b-2 border-transparent whitespace-nowrap
                         hover:text-on-surface/80
                         data-[active]:text-on-surface data-[active]:border-on-surface/60">
              {t.label}
            </Tabs.Tab>
          ))}
        </Tabs.List>

        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="max-w-xl mx-auto px-8 py-8 space-y-8">
            {note && <p className="text-[12px] text-on-surface/70">{note}</p>}

            <Tabs.Panel value="appearance">
              <ThemePicker />
            </Tabs.Panel>

            <Tabs.Panel value="tuning">
              <Tunables />
            </Tabs.Panel>

            <Tabs.Panel value="provider" className="space-y-8">
              <ModelProfiles onChanged={load} />
              <section className="space-y-4">
                <SectionHeader title="Advanced" level={3}
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

                {choice('Extended thinking', 'model.thinking_enabled', ['off', 'on'],
                  'Anthropic only, and only if the model you’ve activated actually ' +
                  'supports it — a model that doesn’t answers with an error rather ' +
                  'than ignoring this. Off by default because of that: unlike the toggles ' +
                  'above, turning this on changes what the request itself asks for, not ' +
                  'just what happens to the reply. When a provider streams reasoning back ' +
                  '(this, or an OpenAI-compatible reasoning model that sends it unprompted) ' +
                  'it shows above the reply in its own collapsed block.')}
              </section>
            </Tabs.Panel>

            <Tabs.Panel value="privacy">
              <PrivacySettings draft={draft} onChange={setDraftKey}
                modelStatus={data?.status?.privacy_model} />
            </Tabs.Panel>

            <Tabs.Panel value="vault">
              <VaultSettings />
            </Tabs.Panel>

            <Tabs.Panel value="sandbox">
              <section className="space-y-4">
                <SectionHeader title="Sandbox" level={3} />
                {choice('Permission prompts', 'sandbox.auto_approve', ['all', 'safe', 'off'],
                  'all = never ask · safe = ask for shell only · off = always ask')}
              </section>
            </Tabs.Panel>

            <Tabs.Panel value="diagnostics" className="space-y-8">
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
            </Tabs.Panel>
          </div>
        </div>
      </Tabs.Root>
    </div>
  );
}
