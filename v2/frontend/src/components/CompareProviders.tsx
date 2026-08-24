import { useCallback, useEffect, useState } from 'react';
import { Check, Minus } from 'lucide-react';
import { api, type Capability } from '../lib/crs';
import { EmptyState, SectionHeader } from './ui';

/* Which of my providers should I use for this?
 *
 * WHAT THIS IS NOT. The design asked for star ratings across Speed, Coding and
 * Vision. Primnox has never run a benchmark, and a five-star "coding" column
 * invented to fill a table is a published benchmark whether or not anybody
 * calls it one — someone would pick a provider because of it. OmniRoute can
 * show that column honestly because it syncs Arena ELO into a table; until
 * Primnox does the same, the column would be decoration wearing the costume
 * of data.
 *
 * WHAT IT IS. Facts from the capability registry the gateway already consults
 * before deciding whether to send a `tools` array, plus the one number that IS
 * measured here: observed time to first token, with the call count beside it
 * so a single lucky request does not read as a track record.
 *
 * A table rather than cards. This is a comparison, comparison means scanning
 * one attribute down a column, and cards make that the one thing you cannot do.
 */

function Tri({ value }: { value: 'native' | 'emulated' | 'none' }) {
  if (value === 'native') {
    return <Check size={13} className="text-success" aria-label="yes" />;
  }
  if (value === 'emulated') {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-on-surface/60">
        emulated
      </span>
    );
  }
  return <Minus size={13} className="text-on-surface/50" aria-label="no" />;
}

const fmtWindow = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(n % 1_000_000 ? 1 : 0)}M`
    : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n);

export function CompareProviders() {
  const [rows, setRows] = useState<Capability[] | null>(null);

  const load = useCallback(() => {
    api.capabilities().then(r => setRows(r.providers)).catch(() => setRows([]));
  }, []);

  useEffect(() => {
    load();
    // A connection test run in Mission Control measures the same endpoints
    // this table reports on, and a row that still reads "not measured" a
    // second after the measurement is the kind of small lie that makes a
    // whole dashboard untrustworthy.
    window.addEventListener('primnox:providers-measured', load);
    return () => window.removeEventListener('primnox:providers-measured', load);
  }, [load]);

  if (rows && rows.length === 0) {
    return (
      <section className="space-y-3">
        <SectionHeader title="Compare" level={3} />
        <EmptyState title="Nothing to compare">
          Add a second provider and this fills in — it is most useful when
          deciding which of two configured models to send a given job to.
        </EmptyState>
      </section>
    );
  }

  return (
    <section className="space-y-3">
      <SectionHeader title="Compare" level={3}
        note="Capabilities the gateway reads before every call, and the one number actually measured here — observed time to first token. No quality ratings: Primnox has not run a benchmark, so it does not publish one." />

      <div className="overflow-x-auto custom-scrollbar rounded-xl border border-on-surface/[0.07]">
        <table className="w-full border-collapse text-[12px]">
          <thead>
            <tr>
              {['Provider', 'Model', 'Context', 'Tools', 'Vision', 'JSON', 'Local', 'First token']
                .map(h => (
                  <th key={h}
                    className="whitespace-nowrap border-b border-on-surface/[0.12] px-3 py-2 text-left
                               font-mono text-[10px] uppercase tracking-[0.12em] text-on-surface/50">
                    {h}
                  </th>
                ))}
            </tr>
          </thead>
          <tbody>
            {!rows && [0, 1].map(i => (
              <tr key={i} aria-busy="true">
                <td colSpan={8} className="px-3 py-2.5">
                  <span className="block h-3 rounded bg-on-surface/[0.06]" />
                </td>
              </tr>
            ))}
            {rows?.map(r => (
              <tr key={r.name} className="border-b border-on-surface/[0.05] last:border-0">
                <td className="whitespace-nowrap px-3 py-2 text-on-surface/85">{r.name}</td>
                <td className="max-w-[13rem] truncate px-3 py-2 text-on-surface/60">{r.model}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-on-surface/70">
                  {fmtWindow(r.context_window)}
                </td>
                <td className="px-3 py-2"><Tri value={r.tool_calling} /></td>
                <td className="px-3 py-2"><Tri value={r.vision} /></td>
                <td className="px-3 py-2">
                  {r.json_mode
                    ? <Check size={13} className="text-success" aria-label="yes" />
                    : <Minus size={13} className="text-on-surface/50" aria-label="no" />}
                </td>
                <td className="px-3 py-2">
                  {r.local
                    ? <Check size={13} className="text-success" aria-label="on this machine" />
                    : <Minus size={13} className="text-on-surface/50" aria-label="cloud" />}
                </td>
                {/* The call count travels with the latency on purpose: one
                    lucky request is not a track record, and a bare "180 ms"
                    with no denominator invites reading it as one. */}
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-on-surface/70">
                  {r.latency_ms == null
                    ? <span className="text-on-surface/50">not measured</span>
                    : <>{Math.round(r.latency_ms)} ms
                      <span className="text-on-surface/50"> · {r.calls} call{r.calls === 1 ? '' : 's'}</span></>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
