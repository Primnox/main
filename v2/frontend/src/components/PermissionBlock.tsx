import { ShieldAlert, ShieldCheck } from 'lucide-react';
import { api, type PermissionRequest } from '../lib/crs';


/* What a settled question says afterwards. An approval you gave by hand must
   not read back as one the machine gave itself — that is the difference
   between a record and a reassurance. */
export const RESOLUTION_COPY: Record<string, string> = {
  allow_auto: 'approved automatically',
  allow_once: 'you allowed this once',
  allow_turn: 'you allowed this for the turn',
  deny: 'you declined',
};

/* A permission question. Auto-approved ones are still shown — the user should
   be able to see afterwards what ran without having been interrupted. */
export function PermissionBlock({ p }: { p: PermissionRequest }) {
  if (p.auto || p.resolved) {
    return (
      <div className="mb-3 flex items-center gap-2 text-[11px] text-on-surface/40">
        {p.resolved === 'deny'
          ? <ShieldAlert size={11} className="shrink-0" />
          : <ShieldCheck size={11} className="shrink-0" />}
        <span className="font-mono">{p.action}</span>
        <span>
          {p.resolved
            ? RESOLUTION_COPY[p.resolved] ?? p.resolved
            : 'approved automatically'}
        </span>
      </div>
    );
  }
  return (
    <div className="mb-3 rounded-xl border border-primary/25 bg-primary/[0.05] px-3.5 py-3">
      <div className="flex items-start gap-2.5">
        <ShieldAlert size={14} className="shrink-0 mt-0.5 text-primary/80" />
        <div className="min-w-0 flex-1">
          <p className="px-label mb-1">Permission needed</p>
          <p className="text-[12px] leading-5 text-on-surface/75 whitespace-pre-wrap">{p.detail}</p>
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {p.options.map(o => (
              <button key={o.id} onClick={() => api.resolvePermission(p.id, o.id)}
                className="px-2.5 py-1 rounded-lg border border-on-surface/15 hover:bg-on-surface/[0.06] transition-all duration-200 px-label">
                {o.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/* One turn: the user's message, the reply, and — critically — its own status.
   There is no global "thinking" indicator anywhere in this file (CRS §5.3). */
