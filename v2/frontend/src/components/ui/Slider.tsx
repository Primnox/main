import { useId } from 'react';
import type { ReactNode } from 'react';
import { Slider as BaseSlider } from '@base-ui-components/react/slider';

/* A range and a number input over one value.
 *
 * Both, because they answer different questions. The range answers "where does
 * this sit between the bounds" — which for a knob like context.graph_share is
 * the only question that matters, and a number box cannot show it. The number
 * answers "what exactly is it", which a range cannot: dragging to precisely
 * 2000 on a 200–200,000 track is not possible.
 *
 * They share one value and one `onChange`, so neither can drift from the other.
 * The number input is `inputMode="decimal"` and clamps on commit rather than on
 * every keystroke — clamping per keystroke makes an empty field snap to the
 * minimum the moment you clear it to type a new value.
 *
 * The range is Base UI's Slider rather than <input type="range">. What that
 * buys, none of which the native element gives for free: Home/End and
 * PageUp/PageDown (`largeStep`) as well as the arrows, and an accessible value
 * derived from `format` — so a reader announces "40%" rather than a bare "40",
 * which is the whole reason aria-valuetext had to be written by hand before.
 * The number input stays a plain <input>; Base UI's slider does not include one
 * and the pairing is deliberate.
 */
export function Slider({
  label, value, min, max, step = 1, onChange, hint, disabled, suffix, right, format,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  hint?: ReactNode;
  disabled?: boolean;
  suffix?: string;
  right?: ReactNode;
  format?: Intl.NumberFormatOptions;
}) {
  const labelId = useId();
  const clamp = (n: number) => Math.min(max, Math.max(min, n));

  return (
    <div className={`space-y-2 ${disabled ? 'opacity-60' : ''}`}>
      <div className="flex items-baseline gap-3">
        <span id={labelId} className="text-[13px] leading-snug text-on-surface/85">
          {label}
        </span>
        {right && <div className="ml-auto shrink-0">{right}</div>}
      </div>

      <div className="flex items-center gap-3">
        <BaseSlider.Root
          aria-labelledby={labelId}
          value={value}
          onValueChange={v => onChange(clamp(Number(v)))}
          min={min} max={max} step={step}
          disabled={disabled}
          format={format}
          className="flex-1 min-w-0">
          <BaseSlider.Control className="flex w-full items-center py-2 cursor-pointer data-[disabled]:cursor-not-allowed">
            <BaseSlider.Track className="h-px w-full rounded bg-on-surface/20">
              <BaseSlider.Indicator className="h-px rounded bg-[var(--color-primary)]" />
              <BaseSlider.Thumb className="size-3 rounded-full bg-[var(--color-primary)] outline-none
                                           focus-visible:ring-2 focus-visible:ring-on-surface/40" />
            </BaseSlider.Track>
          </BaseSlider.Control>
        </BaseSlider.Root>

        <div className="flex items-center gap-1.5 shrink-0">
          <input type="number" inputMode="decimal" disabled={disabled}
            aria-label={`${label}, exact value`}
            min={min} max={max} step={step} value={value}
            onChange={e => {
              const n = Number(e.target.value);
              if (e.target.value !== '' && Number.isFinite(n)) onChange(n);
            }}
            onBlur={e => {
              const n = Number(e.target.value);
              onChange(Number.isFinite(n) ? clamp(n) : min);
            }}
            className="w-[5.5rem] bg-transparent border border-on-surface/[0.12] rounded-lg
                       px-2 py-1 text-[12px] font-mono tabular-nums text-right outline-none
                       px-interactive focus-visible:border-on-surface/40" />
          {suffix && <span className="px-label">{suffix}</span>}
        </div>
      </div>

      {hint && <p className="text-[11px] leading-relaxed text-on-surface/40 max-w-[62ch]">{hint}</p>}
    </div>
  );
}
