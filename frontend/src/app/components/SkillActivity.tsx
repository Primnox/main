import { useState } from 'react';
import { Check, Loader2, ChevronDown, ChevronUp, Lock, X } from 'lucide-react';

/**
 * Live activity panel for a running skill.
 *
 * A multi-step skill can run for the better part of a minute. Before this
 * the UI showed a coloured pill and nothing else, so the honest user
 * question was "is this thing dead?". Two tiers on purpose: plain-language
 * phases by default, with the actual commands behind a toggle — visible
 * enough to be trustworthy, quiet enough not to read as a debug log.
 *
 * Commands arrive already redacted (backend/redaction.py); this component
 * must never be handed a real credential to hide, because hiding it here
 * would mean it had already crossed the websocket.
 */

export interface SkillPhase {
  skill?: string;
  phase: string;
  status: 'running' | 'done' | 'failed';
  detail?: string;
  command?: string;
  step?: number;
  total?: number;
}

const StatusIcon = ({ status }: { status: SkillPhase['status'] }) => {
  if (status === 'running') return <Loader2 size={13} className="text-primary animate-spin" />;
  if (status === 'failed') return <X size={13} className="text-error" />;
  return <Check size={13} className="text-success" />;
};

export const SkillActivity = ({ phases }: { phases: SkillPhase[] }) => {
  const [showLog, setShowLog] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  if (!phases?.length) return null;

  const active = phases.find(p => p.status === 'running');
  const failed = phases.some(p => p.status === 'failed');
  const skill = phases.find(p => p.skill)?.skill;
  const current = active?.step;
  const total = phases.find(p => p.total)?.total;
  const commands = phases.filter(p => p.command);

  return (
    <div className="mb-2 rounded-xl border border-on-surface/10 bg-on-surface/[0.03] overflow-hidden">
      <button
        onClick={() => setCollapsed(c => !c)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-on-surface/[0.03] transition-colors"
      >
        {active ? (
          <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse shrink-0" />
        ) : (
          <Check size={12} className={failed ? 'text-error shrink-0' : 'text-success shrink-0'} />
        )}
        <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface/55">
          {active ? 'working' : failed ? 'finished with errors' : 'completed'}
        </span>
        {skill && (
          <span className="font-mono text-[10px] text-primary/70 lowercase">{skill}</span>
        )}
        {active && current && total && (
          <span className="ml-auto font-mono text-[10px] text-on-surface/40">
            step {current} of {total}
          </span>
        )}
        {collapsed ? (
          <ChevronDown size={13} className="text-on-surface/40 ml-auto shrink-0" />
        ) : (
          <ChevronUp size={13} className="text-on-surface/40 ml-2 shrink-0" />
        )}
      </button>

      {!collapsed && (
        <div className="px-3 pb-2.5">
          {phases.map((p, i) => (
            <div key={`${p.step ?? 'x'}-${i}`} className="flex items-start gap-2.5 py-[3px]">
              <span className="w-4 flex justify-center pt-[3px] shrink-0">
                {p.status === 'done' && i < phases.length - 1 && !active ? (
                  <Check size={13} className="text-success/70" />
                ) : (
                  <StatusIcon status={p.status} />
                )}
              </span>
              <span
                className={`text-[13px] leading-5 min-w-0 ${
                  p.status === 'running' ? 'text-on-surface/90' : 'text-on-surface/55'
                }`}
              >
                {p.phase}
              </span>
              {p.detail && (
                <span className="ml-auto font-mono text-[10px] text-on-surface/40 shrink-0 pt-[3px] truncate max-w-[45%]">
                  {p.detail}
                </span>
              )}
            </div>
          ))}

          {phases.every(p => p.status !== 'running') && (
            <div className="flex items-center gap-2 mt-2 pt-2 border-t border-on-surface/[0.07]">
              <Lock size={11} className="text-success/60" />
              <span className="font-mono text-[9px] uppercase tracking-widest text-on-surface/35">
                sandbox · network blocked
              </span>
              {commands.length > 0 && (
                <button
                  onClick={() => setShowLog(s => !s)}
                  className="ml-auto font-mono text-[9px] uppercase tracking-widest text-primary/60 hover:text-primary transition-colors"
                >
                  {showLog ? 'hide' : 'activity'}
                </button>
              )}
            </div>
          )}

          {showLog && commands.length > 0 && (
            <pre className="mt-2 rounded-lg border border-on-surface/[0.07] bg-surface/60 p-2.5 font-mono text-[10.5px] leading-relaxed text-on-surface/60 whitespace-pre-wrap break-all">
              {commands
                .map(c => `$ ${c.command}${c.detail ? `\n  ${c.detail}` : ''}`)
                .join('\n')}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};
