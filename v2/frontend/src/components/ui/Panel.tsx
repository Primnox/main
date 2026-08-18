import { forwardRef } from 'react';
import type { ReactNode } from 'react';

/* The surface everything else sits on.
 *
 * Three treatments, all already defined in styles/tailwind.css and all derived
 * from theme tokens rather than a literal rgba(255,255,255,…):
 *
 *   glass  — .px-glass: a ~12% fill over blur(16px) saturate(180%), a hairline
 *            border and a lit top edge. For anything that genuinely floats over
 *            content: popovers, overlays, the composer.
 *            NOT `.glass-panel`, which fills with --nav-bg at 85% opacity —
 *            correct for a nav bar, which exists to hide what scrolls under it,
 *            and useless as glass, which exists to show it.
 *   solid  — .px-panel: a gradient mixed from --text into --bg. For anything
 *            that IS the content: settings sections, list rows.
 *   bare   — border and radius only.
 *
 * Deriving from tokens is what lets glass survive a theme switch. A hardcoded
 * translucent white assumes a dark ground, and four of the ten themes (paper,
 * clinical, sand, mono) are light — there it would wash out to an invisible
 * rectangle instead of reading as a raised surface.
 *
 *
 * forwardRef because callers measure it — RowMenu reads its height after render
 * to decide whether to open the menu upward or downward.
 */
export const Panel = forwardRef<any, {
  as?: any;
  variant?: 'glass' | 'solid' | 'bare';
  className?: string;
  children?: ReactNode;
  [key: string]: any;
}>(function Panel(
  { as: Tag = 'div', variant = 'solid', className = '', children, ...rest }, ref,
) {
  const base =
    variant === 'glass' ? 'px-glass'
    : variant === 'solid' ? 'px-panel'
    : 'rounded-[var(--radius-panel)] border border-on-surface/[0.09]';
  return <Tag ref={ref} className={`${base} ${className}`} {...rest}>{children}</Tag>;
});
