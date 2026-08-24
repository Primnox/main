import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, RotateCw } from 'lucide-react';
import { api, type ModelHealth, type Telemetry } from '../lib/crs';

/* Mission Control — the header of the Providers surface.
 *
 * Four numbers, a live routing map, and the session's telemetry. It exists
 * because the question people actually arrive with is "is this working", and
 * the honest answer was previously spread across a profile list, a routing
 * table, and a log file.
 *
 * EVERY NUMBER HERE IS MEASURED. That rules out two tiles the design called
 * for. There is no tokens-per-second, because nothing in Primnox times the
 * gap between tokens and a figure derived from totals over wall-clock counts
 * the user's reading time as slow inference. There are no quality stars,
 * because Primnox has never run a benchmark and a five-star "coding" column
 * invented to fill a table is a published benchmark whether or not it is
 * labelled as one. What replaced them is true and, once you have looked at
 * it twice, more useful: how many turns ran today and how many finished.
 *
 * MOTION IS STATE, NOT DECORATION. The graph's nodes breathe only while a
 * turn is live; the latency counts up on change rather than snapping, because
 * a number that animates tells you it just moved and a number that replaces
 * itself does not. Everything here is off under `prefers-reduced-motion`.
 */

function useCountUp(target: number | null, ms = 420) {
  const [shown, setShown] = useState(target ?? 0);
  const from = useRef(target ?? 0);
  const raf = useRef<number | null>(null);

  useEffect(() => {
    if (target == null) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setShown(target);
      from.current = target;
      return;
    }
    const start = performance.now();
    const a = from.current;
    const step = (t: number) => {
      const p = Math.min(1, (t - start) / ms);
      // Exponential ease-out: fast to most of the value, settles at the end.
      const eased = 1 - Math.pow(1 - p, 3);
      setShown(Math.round(a + (target - a) * eased));
      if (p < 1) raf.current = requestAnimationFrame(step);
      else from.current = target;
    };
    raf.current = requestAnimationFrame(step);
    return () => { if (raf.current) cancelAnimationFrame(raf.current); };
  }, [target, ms]);

  return target == null ? null : shown;
}

function Stat({ value, label, tone = 'neutral' }: {
  value: string | number | null; label: string; tone?: 'neutral' | 'good' | 'warn';
}) {
  const colour = tone === 'good' ? 'text-success' : tone === 'warn' ? 'text-warn' : 'text-on-surface';
  return (
    <div className="min-w-0 flex-1 rounded-xl border border-on-surface/[0.07] px-4 py-3">
      <p className={`truncate text-[18px] font-semibold tabular-nums leading-none ${colour}`}>
        {value ?? '—'}
      </p>
      <p className="px-label mt-2 truncate">{label}</p>
    </div>
  );
}

/* The chain, drawn. Same data as the Routing list below it — this is the
   shape of it and that is the detail of it, and neither replaces the other. */
function RouteMap({ chain, live }: { chain: ModelHealth['chain']; live: boolean }) {
  if (chain.length === 0) {
    return (
      <p className="px-3 py-6 text-center text-[11px] text-on-surface/50">
        Nothing configured to route to yet.
      </p>
    );
  }
  return (
    <div className="space-y-2">
      {chain.map((step, i) => {
        const blocked = !step.eligible;
        return (
          <div key={step.key + i} className="flex items-center gap-2">
            <span className="px-label w-4 shrink-0 tabular-nums">{i + 1}</span>
            <div
              className={`min-w-0 flex-1 rounded-lg border px-3 py-2 transition duration-200
                ${i === 0 && !blocked
                  ? 'border-primary/40 bg-primary/[0.04]'
                  : blocked
                    ? 'border-on-surface/[0.05] opacity-55'
                    : 'border-on-surface/[0.12]'}
                ${live && i === 0 && !blocked ? 'px-breathe' : ''}`}>
              <span className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 shrink-0 rounded-full
                  ${blocked ? 'bg-warn' : i === 0 ? 'bg-success' : 'bg-on-surface/30'}`} />
                <span className="min-w-0 flex-1 truncate text-[12px]">
                  {step.provider === 'active' ? 'Active provider' : step.provider}
                </span>
                <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-on-surface/50">
                  {i === 0 ? 'first' : blocked ? 'skipped' : 'fallback'}
                </span>
              </span>
              <span className="mt-0.5 block truncate text-[11px] text-on-surface/50">
                {step.model}{step.local ? ' · on this machine' : ''}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function MissionControl() {
  const [tele, setTele] = useState<Telemetry | null>(null);
  const [health, setHealth] = useState<ModelHealth | null>(null);
  const [testing, setTesting] = useState(false);
  const [log, setLog] = useState<string[]>([]);

  const load = useCallback(() => {
    api.telemetry().then(setTele).catch(() => setTele(null));
    api.modelHealth().then(setHealth).catch(() => setHealth(null));
  }, []);
  useEffect(load, [load]);

  /* Polled only while a turn is in flight or a breaker is counting down.
     A dashboard that re-fetches every five seconds to watch nothing change is
     a request every five seconds for nothing. */
  const busy = (tele?.turns.live ?? 0) > 0 || (tele?.open_circuits ?? 0) > 0;
  useEffect(() => {
    if (!busy) return;
    const t = window.setInterval(load, 4000);
    return () => window.clearInterval(t);
  }, [busy, load]);

  const latency = useCountUp(tele?.latency_ms ?? null);

  /* The connection test, narrated. Each line appears as its step actually
     finishes — the log is the test happening, not a canned sequence played
     back at a fixed speed while something else runs. */
  const runTest = useCallback(async () => {
    setTesting(true);
    setLog(['Testing every configured provider…']);
    try {
      const { results } = await api.testAllProfiles();
      const lines = results.map(r => r.ok
        ? `${r.profile}: reachable in ${r.latency_ms}ms, ${r.models.length} models offered.`
        : `${r.profile}: ${r.reason.replace(/_/g, ' ')} — ${r.error.slice(0, 90)}`);
      const passed = results.filter(r => r.ok).length;
      setLog([...lines, `${passed} of ${results.length} answered.`]);
      load();
      // The test just measured latency the Compare table is showing as
      // "not measured". One event rather than a shared store: three panels
      // read the same endpoints and only ever need to know "go and look
      // again", which is a notification, not state.
      window.dispatchEvent(new CustomEvent('primnox:providers-measured'));
    } catch (e: any) {
      setLog([`The test could not run: ${String(e?.message ?? e)}`]);
    } finally { setTesting(false); }
  }, [load]);

  const healthy = tele?.healthy ?? true;

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-3">
        <h3 className="px-eyebrow">Mission control</h3>
        <span className={`px-label ${healthy ? 'text-success' : 'text-warn'}`}>
          {healthy ? 'all clear' : `${tele?.open_circuits} benched`}
        </span>
        <button onClick={load} aria-label="Refresh"
          className="px-interactive ml-auto rounded-lg p-1.5 text-on-surface/50 hover:bg-on-surface/[0.05] hover:text-on-surface">
          <RotateCw size={12} />
        </button>
      </div>

      <div className="flex flex-wrap gap-2">
        <Stat value={tele?.providers ?? null} label="Providers" />
        <Stat value={tele?.local_loaded ?? null} label="Loaded locally"
          tone={(tele?.local_loaded ?? 0) > 0 ? 'good' : 'neutral'} />
        <Stat value={tele?.requests_today ?? null} label="Turns today" />
        <Stat
          value={tele?.success_rate == null ? '—' : `${Math.round(tele.success_rate * 100)}%`}
          label="Finished"
          tone={tele?.success_rate != null && tele.success_rate < 0.9 ? 'warn' : 'neutral'} />
        <Stat
          value={tele?.local_active ? 'On device' : tele?.scrubbing ? 'Scrubbed' : 'Unscrubbed'}
          label="This turn"
          tone={tele?.local_active || tele?.scrubbing ? 'good' : 'warn'} />
      </div>

      <div className="grid gap-2 md:grid-cols-[1fr_18rem]">
        <div className="rounded-xl border border-on-surface/[0.07] p-3">
          <p className="px-label mb-2.5">Route map</p>
          <RouteMap chain={health?.chain ?? []} live={(tele?.turns.live ?? 0) > 0} />
        </div>

        <div className="space-y-2 rounded-xl border border-on-surface/[0.07] p-3">
          <p className="px-label">This session</p>
          <dl className="space-y-1.5 text-[11px]">
            {[
              ['First token', latency == null ? 'not measured yet' : `${latency} ms`],
              ['Turns today', String(tele?.requests_today ?? 0)],
              ['Failed', String(tele?.turns.failed ?? 0)],
              ['Benched', String(tele?.open_circuits ?? 0)],
            ].map(([k, v]) => (
              <div key={k} className="flex justify-between gap-3">
                <dt className="text-on-surface/50">{k}</dt>
                <dd className="tabular-nums text-on-surface/85">{v}</dd>
              </div>
            ))}
          </dl>

          <button onClick={runTest} disabled={testing}
            className="px-interactive flex w-full items-center justify-center gap-2 rounded-lg
                       border border-on-surface/[0.12] py-2 font-mono text-[10px] uppercase
                       tracking-[0.12em] text-on-surface/70 hover:border-on-surface/25
                       hover:text-on-surface disabled:opacity-50">
            {testing ? <Loader2 size={11} className="px-spin" /> : null}
            Run connection test
          </button>

          {log.length > 0 && (
            <ol className="space-y-1 border-t border-on-surface/[0.07] pt-2">
              {log.map((line, i) => (
                <li key={i}
                  className="animate-[settings-panel-in_180ms_cubic-bezier(0.23,1,0.32,1)]
                             font-mono text-[10px] leading-relaxed text-on-surface/60">
                  {line}
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>

      {/* Loaded local models, with what they are actually costing in memory.
          Ollama reports resident size per model through /api/ps; "installed"
          and "loaded" are different states and only one of them uses VRAM. */}
      {(tele?.loaded_models.length ?? 0) > 0 && (
        <div className="flex flex-wrap gap-2 rounded-xl border border-on-surface/[0.07] px-3 py-2">
          <span className="px-label">Resident</span>
          {tele!.loaded_models.map((m: { name: string; vram_gb: number }) => (
            <span key={m.name} className="text-[11px] text-on-surface/70">
              {m.name}
              <span className="text-on-surface/50"> · {m.vram_gb} GB</span>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}
