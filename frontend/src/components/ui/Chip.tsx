import { useId, useState } from 'react';
import type { ReactNode } from 'react';

/* A compact label — provenance, status, a tunable's source.
 *
 * Two rules it exists to enforce:
 *
 * 1. It never wraps. A pill that breaks to a second line stops reading as a
 *    pill and starts reading as broken layout, so the label is `nowrap` with
 *    `min-w-0` and truncates instead.
 *
 * 2. Its explanation is never hover-only. The old provenance chips carried
 *    their meaning in `title=`, which is invisible to keyboard users, invisible
 *    on touch, and unreliable for screen readers. When `detail` is given the
 *    chip becomes a real <button> that toggles the text inline — operable by
 *    pointer, keyboard and touch alike.
 */
export function Chip({
  tone = 'neutral', detail, className = '', children,
}: {
  tone?: 'neutral' | 'primary' | 'success' | 'warn' | 'error';
  detail?: string;
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();

  const tones: Record<string, string> = {
    neutral: 'border-on-surface/[0.18] text-on-surface/55',
    primary: 'border-primary/35 text-primary',
    success: 'border-success/40 text-success',
    warn:    'border-warn/40 text-warn',
    error:   'border-error/45 text-error',
  };
  const shell = `inline-flex min-w-0 max-w-full items-center whitespace-nowrap
                 rounded-full border px-2 py-[3px] font-mono text-[10px]
                 uppercase tracking-[0.12em] ${tones[tone]} ${className}`;

  if (!detail) {
    return <span className={shell}><span className="truncate">{children}</span></span>;
  }

  return (
    <span className="inline-flex min-w-0 flex-col items-start gap-1">
      <button type="button" onClick={() => setOpen(o => !o)}
        aria-expanded={open} aria-controls={id}
        className={`${shell} px-interactive hover:border-on-surface/35 hover:text-on-surface/85`}>
        <span className="truncate">{children}</span>
      </button>
      {open && (
        <span id={id} className="text-[11px] leading-snug text-on-surface/50">
          {detail}
        </span>
      )}
    </span>
  );
}
