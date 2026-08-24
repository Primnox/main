import { useCallback, useEffect, useRef, useState } from 'react';
import { RotateCw, ShieldAlert, Zap } from 'lucide-react';
import { api, type Circuit, type ModelHealth, type RouteStep } from '../lib/crs';
import { SectionHeader } from './ui';
import { GuideInline } from './GuideInline';

/* Where a turn will actually go, and what happened to the ones that failed.
 *
 * The profile list above answers "which provider did I pick". It cannot answer
 * the question that matters when something is wrong — "why did my last reply
 * come from Ollama when I picked Groq" — because the answer lives in state the
 * settings screen never had: a rate limit an hour ago, a breaker still counting
 * down, a key the provider has started rejecting.
 *
 * So this renders the chain in the order the gateway will walk it, and the
 * circuits behind it. Nothing here is editable except Reset, which is what "I
 * just pasted a new key, stop waiting out the cooldown" means to a breaker.
 *
 * It polls only while something is open. A countdown that does not count down
 * is worse than no countdown, and polling a healthy chain every five seconds
 * to watch nothing change is a request per five seconds for nothing.
 */

const FACTOR_LABELS: Record<string, string> = {
  capability: 'capability',
  allocation: 'allocation',
  health: 'health',
  reliability: 'reliability',
  latency: 'latency',
  preference: 'preference',
  cost: 'cost',
  quota: 'quota',
  circuit: 'circuit',
};

function countdown(seconds: number): string {
  if (seconds <= 0) return 'any moment';
  if (seconds < 60) return `${Math.ceil(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  return `${mins}m ${Math.ceil(seconds % 60)}s`;
}

/* The one factor that killed a candidate, rather than all nine. A score of zero
   always has a cause, and naming it is the whole point of showing factors. */
function blocker(step: RouteStep): string | null {
  if (step.eligible) return null;
  const zero = Object.entries(step.factors ?? {}).find(([, v]) => v === 0);
  return zero ? FACTOR_LABELS[zero[0]] ?? zero[0] : 'unavailable';
}

export function RoutingHealth() {
  const [data, setData] = useState<ModelHealth | null>(null);
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | null>(null);

  const load = useCallback(async () => {
    try {
      setData(await api.modelHealth());
      setFailed(false);
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll only while a breaker is counting down — see the note at the top.
  const anyOpen = (data?.circuits ?? []).some(c => c.open);
  useEffect(() => {
    if (!anyOpen) return;
    timer.current = window.setInterval(load, 2000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [anyOpen, load]);

  const reset = useCallback(async (key?: string) => {
    setBusy(true);
    try { setData(await api.resetModelHealth(key)); }
    finally { setBusy(false); }
  }, []);

  if (failed) {
    return (
      <section className="space-y-3">
        <SectionHeader title="Routing" level={3} />
        <p className="text-[11px] text-on-surface/50">
          The backend did not answer. Routing state is in memory, so this is
          empty until it has been asked to send something.
        </p>
      </section>
    );
  }

  const chain = data?.chain ?? [];
  const circuits = data?.circuits ?? [];
  const troubled = circuits.filter(c => c.open || c.terminal || c.failures > 0);

  return (
    <section className="space-y-3">
      <div className="flex items-center gap-2">
        <p className="px-eyebrow">Routing</p>
        <span className="text-[11px] text-on-surface/50">
          {data ? `up to ${data.attempts_allowed} provider${data.attempts_allowed === 1 ? '' : 's'} per turn` : ''}
        </span>
        <button onClick={load} aria-label="Refresh routing state"
          className="ml-auto p-1.5 rounded-lg text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition duration-150">
          <RotateCw size={12} />
        </button>
      </div>

      <p className="text-[11px] text-on-surface/50 leading-relaxed">
        The order the next turn will try. The provider you activated is always
        first; the rest are ranked by what has actually been observed of them.
        A local provider never falls back to a cloud one.
      </p>

      {/* The two guides that explain this table, under the table. The scores,
          the breaker countdown and the local rule all raise the same question
          at the same moment, and the answer should not be in another tab. */}
      <div className="space-y-1.5">
        <GuideInline slug="routing-and-failover" label="Why did it pick that one?" />
        <GuideInline slug="what-leaves-your-device" label="What leaves this device" />
      </div>

      {chain.length === 0 && (
        <p className="text-[11px] text-on-surface/50">Nothing configured to route to yet.</p>
      )}

      <ol className="space-y-1.5">
        {chain.map((step, i) => {
          const why = blocker(step);
          return (
            <li key={step.key + i}
              className={`flex items-center gap-3 px-3 py-2 rounded-lg border text-[12px] transition duration-150
                ${why ? 'border-on-surface/[0.07] opacity-55' : 'border-on-surface/[0.12]'}`}>
              <span className="px-label w-4 shrink-0 tabular-nums">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate">
                {step.provider === 'active' ? 'Active provider' : step.provider}
                <span className="text-on-surface/50"> · {step.model}</span>
                {step.local && <span className="px-label ml-2">local</span>}
              </span>
              {/* No score on the active provider. It is tried first because it
                  was chosen, not because it ranked — printing its score beside
                  a fallback's invites reading 1.00 vs 0.28 as "that one is
                  worse", when the number only ever orders the fallbacks. */}
              {why
                ? <span className="shrink-0 text-warn text-[11px]">skipped · {why}</span>
                : step.origin === 'active'
                  ? <span className="px-label shrink-0">your choice</span>
                  : <span className="shrink-0 text-on-surface/50 text-[11px] tabular-nums"
                      title={step.reasons.join(' · ')}>
                      {step.score.toFixed(2)}
                    </span>}
            </li>
          );
        })}
      </ol>

      {troubled.length > 0 && (
        <div className="space-y-1.5 pt-2">
          <div className="flex items-center gap-2">
            <p className="px-eyebrow">Observed</p>
            <button onClick={() => reset()} disabled={busy}
              className="ml-auto text-[11px] uppercase tracking-[0.1em] text-on-surface/50 hover:text-on-surface transition-colors duration-200 disabled:opacity-40">
              Clear all
            </button>
          </div>
          {troubled.map(c => <CircuitRow key={c.key} circuit={c} busy={busy} onReset={reset} />)}
        </div>
      )}
    </section>
  );
}

function CircuitRow({ circuit, busy, onReset }: {
  circuit: Circuit;
  busy: boolean;
  onReset: (key: string) => void;
}) {
  /* The endpoint, not the profile name — health is recorded against the URL
     and model so that renaming a profile does not lose its history. Showing
     the whole URL in a settings row is noise, so it is trimmed to the host. */
  const [url, model] = circuit.key.split('|');
  let host = url;
  try { host = new URL(url).host; } catch { /* local://echo and friends */ }

  const state = circuit.open
    ? { tone: 'text-warn', icon: <ShieldAlert size={11} />, label: `benched · ${countdown(circuit.opens_in_s)}` }
    : circuit.state === 'half_open'
      ? { tone: 'text-on-surface/60', icon: <Zap size={11} />, label: 'probing' }
      : { tone: 'text-on-surface/50', icon: null, label: 'ok' };

  return (
    <div className="group flex items-center gap-3 px-3 py-2 rounded-lg border border-on-surface/[0.07] text-[11px]">
      <span className={`flex items-center gap-1.5 shrink-0 ${state.tone}`}>
        {state.icon}
        {state.label}
      </span>
      <span className="min-w-0 flex-1 truncate text-on-surface/55">
        {host} · {model}
        {circuit.latency_ms !== null && (
          <span className="text-on-surface/50"> · {Math.round(circuit.latency_ms)}ms</span>
        )}
        {circuit.calls > 0 && (
          <span className="text-on-surface/50">
            {' '}· {circuit.failures}/{circuit.calls} failed
          </span>
        )}
      </span>
      {/* The reason, with the full error on hover — "benched" without a cause
          sends someone to a log file to find out what this screen already knew. */}
      <span className="shrink-0 text-on-surface/50 max-w-[40%] truncate"
        title={circuit.last_error || circuit.reason}>
        {circuit.reason}
      </span>
      <button onClick={() => onReset(circuit.key)} disabled={busy}
        aria-label={`Retry ${host} now`} title="Forget this and try it on the next turn"
        className="shrink-0 p-1 rounded text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05] transition duration-150 disabled:opacity-40">
        <RotateCw size={11} />
      </button>
    </div>
  );
}
