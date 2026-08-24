import { useId } from 'react';
import type { ReactNode } from 'react';
import { Field as BaseField } from '@base-ui-components/react/field';
import { RadioGroup } from '@base-ui-components/react/radio-group';
import { Radio } from '@base-ui-components/react/radio';

/* A labelled input, on Base UI's Field.
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
 *
 * Field.Root wires Label to Control and Description to aria-describedby itself,
 * so the useId/htmlFor bookkeeping this file used to carry is gone. The props
 * are unchanged — every existing call site keeps working.
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
  return (
    <BaseField.Root className="min-w-0 space-y-1.5">
      <BaseField.Label className={hideLabel ? 'sr-only' : 'px-label block'}>
        {label}
      </BaseField.Label>
      <BaseField.Control
        render={as === 'textarea' ? <textarea /> : undefined}
        className={`w-full bg-transparent border border-on-surface/[0.12] rounded-xl
                    px-4 py-2.5 text-sm outline-none px-interactive
                    focus-visible:border-on-surface/40
                    placeholder:text-on-surface/50 ${className}`}
        {...rest} />
      {hint && (
        <BaseField.Description className="text-[11px] leading-snug text-on-surface/50">
          {hint}
        </BaseField.Description>
      )}
    </BaseField.Root>
  );
}

/* A closed set of options, as segmented buttons rather than a <select>.
 *
 * Used where the choices are few and worth seeing at once — api type, sandbox
 * policy. On Base UI's RadioGroup, which supplies what the hand-rolled version
 * did not: a roving tabindex, so the group is one tab stop rather than three,
 * and arrow-key movement between options. Both are required of a radiogroup and
 * neither falls out of putting role="radio" on a row of buttons.
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
  const labelId = useId();
  return (
    <div className="space-y-1.5">
      <span className="px-label block" id={labelId}>{label}</span>
      <RadioGroup
        value={value}
        onValueChange={v => onChange(String(v))}
        aria-labelledby={labelId}
        className="flex flex-wrap gap-2">
        {options.map(o => (
          <Radio.Root key={o.value} value={o.value}
            className="px-interactive px-3 py-1.5 rounded-lg border text-[12px]
                       border-on-surface/[0.12] text-on-surface/55
                       hover:text-on-surface/85
                       data-[checked]:border-on-surface/40
                       data-[checked]:text-on-surface
                       data-[checked]:bg-on-surface/[0.05]">
            {o.label}
          </Radio.Root>
        ))}
      </RadioGroup>
      {hint && <p className="text-[11px] leading-snug text-on-surface/50">{hint}</p>}
    </div>
  );
}
