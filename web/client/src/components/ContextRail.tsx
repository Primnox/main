import { useMemo } from 'react';
import { Check, Circle, Cpu, FileText, Loader2, Package, PanelRight, ShieldAlert, Terminal } from 'lucide-react';
import { TERMINAL, type Turn } from '../lib/crs';
import { STATUS_COPY } from '../lib/status';

/* The right-hand rail: what this conversation has produced and what the stream
   is doing.
 *
 * Two sections of the desktop rail are absent rather than faked:
 *   - the sandbox line, because nothing executes on web at all. Desktop can
 *     say "AppContainer" or honestly warn "NONE — code runs unisolated"; web
 *     has no execution backend, so either string would describe a thing that
 *     does not exist.
 *   - the download link on a file, because there is no asset endpoint to point
 *     at. Files still list, they just are not links yet.
 */
export function ContextRail({
  turns, cursor, connected, synced, liveTurn, model, onClose,
}: {
  turns: Turn[];
  cursor: number;
  connected: boolean;
  synced: boolean;
  liveTurn: Turn | undefined;
  model?: { provider: string; model: string } | null;
  onClose: () => void;
}) {
  // One step per state the turn actually passes through, so Progress reflects
  // the runtime rather than a hardcoded three-stage guess.
  const ORDER = ['queued', 'building_context', 'thinking', 'streaming'];
  const steps = liveTurn
    ? ORDER.map((s, i) => ({
        label: STATUS_COPY[s],
        done: TERMINAL.includes(liveTurn.status) || ORDER.indexOf(liveTurn.status) > i,
      }))
    : [];

  // Everything this conversation produced, newest first. Files belong at the
  // top of the panel that has the room for them.
  const files = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; name: string; bytes?: number }[] = [];
    for (const t of turns) {
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
  }, [turns]);

  const workspaces = useMemo(() => {
    const seen = new Set<string>();
    const out: { id: string; title: string; version: number }[] = [];
    for (const t of turns) {
      for (const w of t.workspaces) {
        if (!seen.has(w.id)) { seen.add(w.id); out.push(w); }
      }
    }
    return out.reverse();
  }, [turns]);

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
                <li key={f.id} className="flex items-center gap-2.5 -mx-2 px-2 py-1.5">
                  <FileText size={13} className="shrink-0 text-on-surface/50" />
                  <span className="text-[11px] text-on-surface/75 truncate flex-1">{f.name}</span>
                  {f.bytes != null && (
                    <span className="font-mono text-[9px] text-on-surface/50 tabular-nums shrink-0">
                      {f.bytes < 1024 ? `${f.bytes}B` : `${(f.bytes / 1024).toFixed(0)}K`}
                    </span>
                  )}
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
                {model ? `${model.provider} · ${model.model}` : 'no provider — add a key'}
              </span></li>
            <li className="flex items-center gap-2.5"><Terminal size={13} className="text-on-surface/50 shrink-0" />
              <span className="text-[11px] text-on-surface/70">{turns.length} turns in context</span></li>
            {/* Every web provider is a cloud provider — the browser calls it
                directly. Worth saying once, here, rather than nowhere. */}
            {model && (
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
            <li className="flex justify-between"><span>cursor</span><span className="tabular-nums text-on-surface/75">{cursor}</span></li>
            <li className="flex justify-between"><span>socket</span><span className="text-on-surface/75">{connected ? 'open' : 'closed'}</span></li>
            <li className="flex justify-between"><span>synced</span><span className="text-on-surface/75">{synced ? 'yes' : 'no'}</span></li>
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
