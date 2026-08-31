import { useMemo } from 'react';
import { Check, Circle, Cpu, Download, FileText, Loader2, Package, PanelRight, ShieldAlert, ShieldCheck, Terminal } from 'lucide-react';
import { API, TERMINAL, type ConversationState, type Turn } from '../lib/crs';
import { STATUS_COPY } from '../lib/status';

export function ContextRail({ state, liveTurn, health, onClose }:
  { state: ConversationState; liveTurn: Turn | undefined; health: any; onClose: () => void }) {
  // One step per state the turn actually passes through, so Progress reflects
  // the runtime rather than a hardcoded three-stage guess.
  const ORDER = ['queued', 'building_context', 'thinking', 'streaming'];
  const steps = liveTurn
    ? ORDER.map((s, i) => ({
        label: STATUS_COPY[s],
        done: TERMINAL.includes(liveTurn.status) || ORDER.indexOf(liveTurn.status) > i,
      }))
    : [];

  // Everything this conversation produced, newest first. The rail used to be
  // six lines of diagnostics above 500px of black, while the generated file —
  // the entire point of the app — was a chip you could miss next to the
  // avatar. Files belong at the top of the panel that has the room for them.
  const files = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; name: string; bytes?: number }[] = [];
    for (const t of state.turns) {
      for (const x of t.executions) {
        for (const a of x.artifacts ?? []) {
          if (!seen.has(a.asset_id)) {
            seen.add(a.asset_id);
            out.push({ id: a.asset_id, name: a.name, bytes: a.bytes });
          }
        }
      }
      for (const a of t.assets) {
        if (!seen.has(a.id)) {
          seen.add(a.id);
          out.push({ id: a.id, name: a.name });
        }
      }
    }
    return out.reverse();
  }, [state.turns]);

  const workspaces = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; title: string; version: number }[] = [];
    for (const t of state.turns) {
      for (const w of t.workspaces) {
        if (!seen.has(w.id)) { seen.add(w.id); out.push(w); }
      }
    }
    return out.reverse();
  }, [state.turns]);

  return (
    <aside aria-label="Context" className="w-[288px] h-full flex flex-col border-l border-on-surface/[0.07] bg-[var(--nav-bg)]">
      <header className="h-14 shrink-0 flex items-center justify-between px-5 border-b border-on-surface/[0.07]">
        <span className="px-label">Context</span>
        <button onClick={onClose} aria-label="Hide context panel"
          className="p-1 -mr-1 rounded text-on-surface/50 hover:text-on-surface transition duration-150">
          <PanelRight size={14} />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* Progress only exists while something is running. A permanent
            "Steps appear here as a turn runs" is a heading explaining its own
            emptiness — it occupied the top of the panel to say nothing. */}
        {steps.length > 0 && (
          <section className="px-5 py-4 border-b border-on-surface/[0.07]">
            <p className="px-label mb-3">Progress</p>
            <ol className="space-y-2.5">
              {steps.map(s => (
                <li key={s.label} className="flex items-center gap-2.5">
                  {s.done ? <Check size={12} className="text-primary shrink-0" />
                          : <Loader2 size={12} className="text-on-surface/50 px-spin shrink-0" />}
                  <span className={`text-[11px] ${s.done ? 'text-on-surface/55' : 'text-on-surface/80'}`}>{s.label}</span>
                </li>
              ))}
            </ol>
          </section>
        )}

        {(files.length > 0 || workspaces.length > 0) && (
          <section className="px-5 py-4 border-b border-on-surface/[0.07]">
            <p className="px-label mb-3">Files</p>
            <ul className="space-y-1">
              {files.map(f => (
                <li key={f.id}>
                  <a href={`${API}/assets/${f.id}/download`} download={f.name}
                    className="group flex items-center gap-2.5 -mx-2 px-2 py-1.5 rounded-lg
                               hover:bg-on-surface/[0.05] transition-colors duration-200">
                    <FileText size={13} className="shrink-0 text-on-surface/50" />
                    <span className="text-[11px] text-on-surface/75 truncate flex-1">{f.name}</span>
                    {f.bytes != null && (
                      <span className="font-mono text-[9px] text-on-surface/50 tabular-nums shrink-0">
                        {f.bytes < 1024 ? `${f.bytes}B` : `${(f.bytes / 1024).toFixed(0)}K`}
                      </span>
                    )}
                    <Download size={11} className="shrink-0 text-on-surface/0 group-hover:text-on-surface/50 transition-colors duration-200" />
                  </a>
                </li>
              ))}
              {workspaces.map(w => (
                <li key={w.id} className="flex items-center gap-2.5 -mx-2 px-2 py-1.5">
                  <Package size={13} className="shrink-0 text-primary/60" />
                  <span className="text-[11px] text-on-surface/75 truncate flex-1">{w.title}</span>
                  <span className="font-mono text-[9px] text-on-surface/50 shrink-0">v{w.version}</span>
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="px-5 py-4 border-b border-on-surface/[0.07]">
          <p className="px-label mb-3">Context</p>
          <ul className="space-y-2.5">
            <li className="flex items-center gap-2.5"><Cpu size={13} className="text-on-surface/50 shrink-0" />
              <span className="text-[11px] text-on-surface/70">
                {health?.model ? `${health.model.provider} · ${health.model.model}` : 'resolving provider…'}
              </span></li>
            <li className="flex items-center gap-2.5"><Terminal size={13} className="text-on-surface/50 shrink-0" />
              <span className="text-[11px] text-on-surface/70">{state.turns.length} turns in context</span></li>
            {/* Says which backend is actually isolating execution — or that
                none is, rather than implying a sandbox that isn't there. */}
            {/* Warming is its own state, not a flavour of "unavailable".
                The first launch after an install spends ~80s inside the
                AppContainer icacls grant, and reporting that as "execution
                refused" for the whole of it describes a broken install
                rather than a one-time setup that is working. */}
            <li className="flex items-start gap-2.5">
              {health?.sandbox_warming
                ? <Loader2 size={13} className="text-on-surface/50 shrink-0 mt-0.5 px-spin" />
                : health?.sandbox
                  ? <ShieldCheck size={13} className="text-on-surface/50 shrink-0 mt-0.5" />
                  : <ShieldAlert size={13} className="text-error/70 shrink-0 mt-0.5" />}
              <span className={`text-[11px] ${health?.sandbox || health?.sandbox_warming ? 'text-on-surface/50' : 'text-error/80'}`}>
                {health?.sandbox_warming ? 'Sandbox: preparing on first run — this takes about a minute'
                  : health?.sandbox === 'appcontainer' ? 'Sandbox: AppContainer isolation'
                  : health?.sandbox === 'unsandboxed' ? 'Sandbox: NONE — code runs unisolated'
                  : health ? 'Sandbox: unavailable — execution refused'
                  : 'Checking sandbox…'}
              </span>
            </li>
            {/* Python is bundled in the app; Node is not, and is resolved from
                PATH only at the moment JS runs. Without this the first
                JavaScript execution is where the user discovers it. */}
            {health && health.node === false && (
              <li className="flex items-start gap-2.5"><ShieldAlert size={13} className="text-error/70 shrink-0 mt-0.5" />
                <span className="text-[11px] text-error/80">Node.js not found — JavaScript execution unavailable</span></li>
            )}
            {health?.model && !health.model.local && (
              <li className="flex items-start gap-2.5"><ShieldAlert size={13} className="text-on-surface/50 shrink-0 mt-0.5" />
                <span className="text-[11px] text-on-surface/50">Cloud provider — prompts leave this device</span></li>
            )}
          </ul>
        </section>

        {/* The cursor, on screen. Reconnect correctness is the whole reason the
            sequence is global and gapless, so it is worth being able to see. */}
        <section className="px-5 py-4">
          <p className="px-label mb-3">Stream</p>
          <ul className="space-y-2.5 font-mono text-[10px] text-on-surface/50">
            <li className="flex justify-between"><span>cursor</span><span className="tabular-nums text-on-surface/75">{state.cursor}</span></li>
            <li className="flex justify-between"><span>socket</span><span className="text-on-surface/75">{state.connected ? 'open' : 'closed'}</span></li>
            <li className="flex justify-between"><span>synced</span><span className="text-on-surface/75">{state.synced ? 'yes' : 'no'}</span></li>
          </ul>
        </section>
      </div>

      <footer className="h-10 shrink-0 flex items-center gap-2 px-5 border-t border-on-surface/[0.07]">
        <Circle size={7} className={liveTurn ? 'text-primary fill-current animate-pulse' : 'text-on-surface/50 fill-current'} />
        <span className="px-label">{liveTurn ? STATUS_COPY[liveTurn.status] ?? 'Working' : 'Idle'}</span>
      </footer>
    </aside>
  );
}
