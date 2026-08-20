import type { ReactNode } from 'react';
import { Button as BaseButton } from '@base-ui-components/react/button';

/* Buttons.
 *
 * `solid` and `ghost` map to the site's .px-btn / .px-btn-ghost so an action in
 * the app and the same action on primnox.github.io are the same object. `quiet`
 * is the in-app addition: a dense toolbar has no room for a 26px-padded pill,
 * and the site never needed one.
 *
 * No focus styling here on purpose. tailwind.css already applies a theme-aware
 * :focus-visible ring to every button globally, and a per-component ring would
 * be a second definition to keep in sync — which is how 203 of 206 controls
 * ended up with no visible focus at all last time.
 *
 * On Base UI's Button for one prop: `focusableWhenDisabled`. A natively
 * disabled button drops out of the tab order entirely, so a keyboard or screen
 * reader user cannot land on it to find out why it is unavailable — which is
 * precisely the case where a reason exists and is worth hearing. Off by default,
 * matching native; opt in where the disabled state carries an explanation.
 */
export function Button({
  variant = 'quiet', size = 'md', className = '', children, ...rest
}: {
  variant?: 'solid' | 'ghost' | 'quiet' | 'danger';
  size?: 'sm' | 'md';
  className?: string;
  children?: ReactNode;
  [key: string]: any;
}) {
  const pad = size === 'sm' ? 'px-2.5 py-1.5' : 'px-3.5 py-2';
  const variants: Record<string, string> = {
    solid: 'px-btn',
    ghost: 'px-btn-ghost',
    quiet: `${pad} rounded-lg border border-on-surface/[0.12] font-mono text-[10px]
            uppercase tracking-[0.14em] text-on-surface/70
            hover:border-on-surface/30 hover:text-on-surface`,
    danger: `${pad} rounded-lg border border-error/40 font-mono text-[10px]
             uppercase tracking-[0.14em] text-error hover:bg-error/10`,
  };
  return (
    <BaseButton type="button"
      className={`px-interactive disabled:opacity-40 data-[disabled]:opacity-40
                  ${variants[variant]} ${className}`}
      {...rest}>
      {children}
    </BaseButton>
  );
}

/* An icon-only control.
 *
 * `label` is required rather than optional, and that is the whole point of the
 * component: an icon button with no accessible name is a button a screen reader
 * announces as "button", and the icon rail is made entirely of them. Making the
 * name part of the type means the compiler catches the omission.
 *
 * `pressed` and `expanded` map to aria-pressed / aria-expanded — state a sighted
 * user reads from the highlight and everyone else reads from nothing at all,
 * unless it is exposed here.
 */
export function IconButton({
  label, pressed, expanded, active, className = '', children, ...rest
}: {
  label: string;
  pressed?: boolean;
  expanded?: boolean;
  active?: boolean;
  className?: string;
  children?: ReactNode;
  [key: string]: any;
}) {
  return (
    <BaseButton type="button" aria-label={label} title={label}
      aria-pressed={pressed} aria-expanded={expanded}
      className={`px-interactive p-1.5 rounded-lg disabled:opacity-40 data-[disabled]:opacity-40
                  ${active ? 'text-on-surface bg-on-surface/[0.07]'
                           : 'text-on-surface/50 hover:text-on-surface hover:bg-on-surface/[0.05]'}
                  ${className}`}
      {...rest}>
      {children}
    </BaseButton>
  );
}
