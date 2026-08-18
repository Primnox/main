import { useCallback, useEffect, useMemo, useState } from 'react';
import { RotateCw } from 'lucide-react';
import { api, type Tunable } from '../lib/crs';
import { Button, Chip, SectionHeader, Slider } from './ui';

/* The 27 declared tunables, as controls.
 *
 * Every one of them has been settable by environment variable and by API since
 * the registry was written, and settable from the UI never — so the numbers that
 * decide how much of the model's window goes to memory, to the graph, and to
 * history were reachable only by someone willing to read the source.
 *
 * Nothing here restates the registry. The label is the backend's `summary`, the
 * helper text is its `cost`, the bounds are its `min`/`max`, and the step comes
 * from its `type`. Those were written to explain each knob at the point of
 * changing it; paraphrasing them in the UI would create a second description to
 * keep in sync, and the two would disagree within a release.
 */

/* Group headings. Derived from the key prefix, which already groups them — the
 * registry is written in these blocks and the keys carry the block name. */
const GROUPS: Record<string, string> = {
  context: 'Context window',
  knowledge: 'Knowledge graph',
  live: 'Conversation graph',
  memory: 'Memory',
  facts: 'Facts graph',
  assets: 'Documents',
  scheduler: 'Streaming',
  skills: 'Skills',
  tools: 'Tools',
  models: 'Providers',
};

const ORDER = Object.keys(GROUPS);

export function Tunables() {
  const [rows, setRows] = useState<Tunable[]>([]);
  const [draft, setDraft] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const load = useCallback(() => {
    api.tunables()
      .then(d => { setRows(d.tunables ?? []); setDraft({}); })
      .catch(() => setRows([]));
  }, []);
  useEffect(load, [load]);

  const dirty = Object.keys(draft).length > 0;

  const save = useCallback(async () => {
    setBusy(true); setNote(null);
    try {
      const result: any = await api.setTunables(draft);
      setRows(result.tunables ?? []);
      setDraft({});
      // Out-of-range values are clamped and reported rather than refused, so a
      // silent success would hide that what landed is not what was typed.
      const rejected = Object.entries(result.rejected ?? {});
      setNote(rejected.length
        ? rejected.map(([k, why]) => `${k}: ${why}`).join(' · ')
        : 'Saved. Applies from the next turn.');
    } finally { setBusy(false); }
  }, [draft]);

  const resetOne = useCallback(async (key: string) => {
    setBusy(true);
    try {
      const result: any = await api.resetTunable(key);
      setRows(result.tunables ?? []);
      setDraft(d => { const { [key]: _drop, ...rest } = d; return rest; });
    } finally { setBusy(false); }
  }, []);

  const grouped = useMemo(() => {
    const out = new Map<string, Tunable[]>();
    for (const row of rows) {
      const prefix = row.key.split('.')[0];
      if (!out.has(prefix)) out.set(prefix, []);
      out.get(prefix)!.push(row);
    }
    return [...out.entries()].sort(
      ([a], [b]) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99),
    );
  }, [rows]);

  if (rows.length === 0) return null;

  return (
    <section className="space-y-5">
      <SectionHeader title="Tuning" level={3}
        note="Every number the runtime reads, with what moving it costs. Changes apply on the next turn — nothing here needs a restart."
        right={dirty
          ? <Button onClick={save} disabled={busy} variant="quiet" size="sm">Save</Button>
          : undefined} />

      {note && <p className="text-[12px] text-on-surface/70">{note}</p>}

      {grouped.map(([prefix, group]) => (
        <div key={prefix} className="space-y-4">
          <h4 className="px-label border-b border-on-surface/[0.07] pb-1.5">
            {GROUPS[prefix] ?? prefix}
          </h4>

          {group.map(t => {
            const fromEnv = t.source === 'environment';
            const value = draft[t.key] ?? t.value;
            return (
              <Slider key={t.key}
                label={t.summary}
                hint={fromEnv
                  // Environment beats a stored value in tunables.get, so a
                  // control that appeared to work here would be a control whose
                  // change is silently discarded. Say where the value comes from
                  // instead, and name the variable to change.
                  ? `Set by ${t.env} in the environment, which outranks anything saved here. ${t.cost}`
                  : t.cost}
                value={value}
                min={t.min}
                max={t.max}
                step={t.type === 'float' ? 0.05 : 1}
                disabled={fromEnv || busy}
                onChange={v => setDraft(d => ({ ...d, [t.key]: v }))}
                right={
                  <span className="flex items-center gap-2">
                    <Chip tone={fromEnv ? 'warn' : t.source === 'saved' ? 'primary' : 'neutral'}>
                      {t.source}
                    </Chip>
                    {!fromEnv && t.source === 'saved' && (
                      <button type="button" onClick={() => resetOne(t.key)}
                        aria-label={`Reset ${t.summary} to its default of ${t.default}`}
                        title={`Back to the default, ${t.default}`}
                        className="px-interactive p-1 rounded text-on-surface/40 hover:text-on-surface">
                        <RotateCw size={12} aria-hidden="true" />
                      </button>
                    )}
                  </span>
                } />
            );
          })}
        </div>
      ))}
    </section>
  );
}
