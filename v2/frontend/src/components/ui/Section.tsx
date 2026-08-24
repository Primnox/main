import type { ReactNode } from 'react';

/* A section's heading.
 *
 * `level` is a real heading level, not a font size. Screen readers navigate by
 * heading, so a panel whose sections are all styled <p> is a panel with no
 * structure to jump through — and one that skips h1 to h4 reports a gap that
 * isn't there. The visual weight comes from .px-eyebrow regardless of level.
 */
export function SectionHeader({
  title, level = 2, note, right,
}: {
  title: string;
  level?: 2 | 3 | 4;
  note?: ReactNode;
  right?: ReactNode;
}) {
  const H: any = `h${level}`;
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-3">
        <H className="px-eyebrow">{title}</H>
        {right && <div className="ml-auto shrink-0">{right}</div>}
      </div>
      {note && <p className="text-[11px] leading-relaxed text-on-surface/50 max-w-[62ch]">{note}</p>}
    </div>
  );
}

/* Nothing here yet — said in a way that explains what would put something here.
 *
 * "No results" is a dead end; "nothing indexed under this scope, point it at a
 * folder" is a next step. Every empty state in the app should read as the
 * second kind, which is easier to hold to when there is one component for it.
 */
export function EmptyState({
  icon, title, children,
}: {
  icon?: ReactNode;
  title?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-8 py-12 text-center">
      {icon && <div className="text-on-surface/50" aria-hidden="true">{icon}</div>}
      {title && <p className="px-label">{title}</p>}
      {children && (
        <p className="max-w-sm text-sm leading-relaxed text-on-surface/55">{children}</p>
      )}
    </div>
  );
}
