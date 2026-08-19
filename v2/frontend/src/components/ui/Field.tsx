import { useId } from 'react';
import type { ReactNode } from 'react';

/* A labelled input.
 *
 * The label is not optional and is not the placeholder. Placeholder-as-label
 * was the single most repeated defect in the old screens — the composer, the
 * memory search, the folder-name field and the index-target field all named
 * themselves only in grey text that vanishes the moment you type, leaving no
 * way to check what a half-filled form is asking for.
 *
 * `hideLabel` keeps the label in the accessibility tree while removing it from
 * the layout, for the cases where a search field really does sit beside its own
 * magnifier icon and a visible caption would be noise.
 */
export function Field({
  label, hideLabel, hint, as = 'input', className = '', ...rest
}: {
  label: string;
  hideLabel?: boolean;
  hint?: ReactNode;
  as?: 'input' | 'textarea';
  className?: string;
  [key: string]: any;
}) {
  const id = useId();
  const Tag: any = as;
  return (
    <div className="min-w-0 space-y-1.5">
      <label htmlFor={id} className={hideLabel ? 'sr-only' : 'px-label block'}>
        {label}
      </label>
      <Tag id={id}
        className={`w-full bg-transparent border border-on-surface/[0.12] rounded-xl
                    px-4 py-2.5 text-sm outline-none px-interactive
                    focus-visible:border-on-surface/40
                    placeholder:text-on-surface/25 ${className}`}
        {...rest} />
      {hint && <p className="text-[11px] leading-snug text-on-surface/40">{hint}</p>}
    </div>
  );
}

/* A closed set of options, as segmented buttons rather than a <select>.
 *
 * Used where the choices are few and worth seeing at once — api type, sandbox
 * policy. `radiogroup` rather than a row of independent buttons, so a screen
 * reader announces "2 of 3" instead of three unrelated toggles.
 */
export function Choice({
  label, value, options, onChange, hint,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
  hint?: ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span className="px-label block" id={`${label}-label`}>{label}</span>
      <div role="radiogroup" aria-labelledby={`${label}-label`} className="flex flex-wrap gap-2">
        {options.map(o => (
          <button key={o.value} type="button" role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={`px-interactive px-3 py-1.5 rounded-lg border text-[12px]
              ${value === o.value
                ? 'border-on-surface/40 text-on-surface bg-on-surface/[0.05]'
                : 'border-on-surface/[0.12] text-on-surface/55 hover:text-on-surface/85'}`}>
            {o.label}
          </button>
        ))}
      </div>
      {hint && <p className="text-[11px] leading-snug text-on-surface/40">{hint}</p>}
    </div>
  );
}
