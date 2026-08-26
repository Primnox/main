import { useContext, useState } from 'react';
import { AlertTriangle, Check, ChevronRight, Eye, Loader2, Terminal } from 'lucide-react';
import { type Execution, type TurnError } from '../lib/crs';
import { ViewerContext } from '../lib/contexts';
import { RecoveryBlock } from './RecoveryBlock';

export function ExecutionBlock({ execution }: { execution: Execution }) {
  const [open, setOpen] = useState(false);
  const [recoveryDismissed, setRecoveryDismissed] = useState(false);
  const openAsset = useContext(ViewerContext);
  const changed = execution.changes;
  const changeCount = changed
    ? changed.created.length + changed.modified.length + changed.deleted.length
    : 0;

  // Construct a TurnError from execution failure if available
  const executionError: TurnError | null = execution.status === 'failed'
    ? {
      code: 'tool_execution_failed',
      message: execution.summary || 'Tool execution failed',
      retryable: true,
    }
    : null;

  return (
    <div className="mb-3 rounded-xl border border-on-surface/[0.09] overflow-hidden">
      <button onClick={() => setOpen(o => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left hover:bg-on-surface/[0.03] transition-colors duration-200">
        <Terminal size={12} className="shrink-0 text-on-surface/50" />
        <span className="px-label">{execution.runtime}</span>
        <span className="text-[11px] text-on-surface/50 truncate flex-1">
          {execution.status === 'running' ? 'running…' : execution.summary}
        </span>
        {execution.status === 'running'
          ? <Loader2 size={11} className="px-spin text-on-surface/50 shrink-0" />
          : execution.status === 'failed'
            ? <AlertTriangle size={11} className="text-error shrink-0" />
            : <Check size={11} className="text-primary shrink-0" />}
        <ChevronRight size={12}
          className={`shrink-0 text-on-surface/50 transition-transform duration-200 ${open ? 'rotate-90' : ''}`} />
      </button>

      {/* Outside the collapse on purpose: a generated file the user cannot
          find is the same as one that was never produced. */}
      {execution.artifacts.length > 0 && (
        <div className="flex flex-wrap gap-1.5 px-3.5 pb-3 pt-0.5">
          {execution.artifacts.map(a => (
            <button key={a.asset_id}
              onClick={() => openAsset({ id: a.asset_id, name: a.name })}
              aria-label={`Open ${a.name}`}
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-primary/30 bg-primary/[0.06] text-[11px] text-on-surface/80 hover:bg-primary/[0.12] transition-colors duration-200">
              <Eye size={11} className="text-primary/80" />
              <span className="font-mono">{a.name}</span>
              <span className="text-on-surface/50">{(a.bytes / 1024).toFixed(1)} KB</span>
            </button>
          ))}
        </div>
      )}

      {open && (
        <div className="border-t border-on-surface/[0.07]">
          {/* Recovery block for failures, before output */}
          {executionError && !recoveryDismissed && (
            <div className="px-3.5 py-3 border-b border-on-surface/[0.07]">
              <RecoveryBlock
                error={executionError}
                compact={false}
                onDismiss={() => setRecoveryDismissed(true)}
                context={{
                  tool: execution.runtime,
                }}
              />
            </div>
          )}

          {execution.output.length > 0 && (
            <pre className="max-h-64 overflow-auto px-3.5 py-3 font-mono text-[11px] leading-relaxed text-on-surface/70 bg-on-surface/[0.02]">
              {execution.output.join('\n')}
            </pre>
          )}
          {changeCount > 0 && changed && (
            <div className="px-3.5 py-2.5 border-t border-on-surface/[0.07]">
              <p className="px-label mb-1.5">Files</p>
              <ul className="space-y-0.5 font-mono text-[11px]">
                {changed.created.map(p => <li key={p} className="text-primary/80">+ {p}</li>)}
                {changed.modified.map(p => <li key={p} className="text-on-surface/60">~ {p}</li>)}
                {changed.deleted.map(p => <li key={p} className="text-error/80">− {p}</li>)}
              </ul>
            </div>
          )}
          {execution.output.length === 0 && changeCount === 0 && (
            <p className="px-3.5 py-3 text-[11px] text-on-surface/50">No output, no file changes.</p>
          )}
        </div>
      )}
    </div>
  );
}

