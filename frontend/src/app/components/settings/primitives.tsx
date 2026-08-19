/**
 * Settings primitives, built in the website's design language.
 *
 * The previous Settings screen was a 1,625-line component with every control
 * styled inline, which is why no two rows lined up and why hardcoded colours
 * kept surviving theme sweeps. These are the only building blocks the settings
 * screen needs; each one is themed through the site's tokens, so a new palette
 * needs no changes here.
 *
 * Editorial, not card-based: hairline rules and negative space, mono micro-labels,
 * Syne for headings. Matches primnox.github.io.
 */
import { ReactNode, useState } from 'react';
import { Eye, EyeOff, Check } from 'lucide-react';

/* ── Section ────────────────────────────────────────────────────────────────
   A numbered section heading, mirroring the site's `.sec-head` (mono index in a
   narrow column, display title beside it) with a hairline under it. */
export const Section = ({ index, title, children }: {
  index: string; title: string; children: ReactNode;
}) => (
  <section className="mb-10 rounded-panel border border-on-surface/10 bg-surface-container-low/70 px-5 py-5 shadow-panel sm:px-6">
    <div className="grid grid-cols-[38px_1fr] items-baseline pb-4 border-b border-on-surface/10">
      <span className="px-eyebrow">{index}</span>
      <h3 className="px-display px-display-sm text-on-surface">{title}</h3>
    </div>
    <div>{children}</div>
  </section>
);

/* ── Row ────────────────────────────────────────────────────────────────────
   One setting: label and description on the left, control on the right. The
   site's `.feat-row` — a hairline rule between rows, no card, no shadow.
   `stack` puts the control on its own line for wide inputs. */
export const Row = ({ label, hint, children, stack = false }: {
  label: string; hint?: string; children?: ReactNode; stack?: boolean;
}) => (
  <div className={`py-5 border-b border-on-surface/10 last:border-b-0 px-interactive hover:bg-on-surface/[0.025] ${
    stack ? '' : 'grid grid-cols-[minmax(0,1fr)_auto] gap-6 items-center'
  }`}>
    <div className={stack ? 'mb-3' : 'min-w-0'}>
      <div className="px-label !text-on-surface !tracking-[0.14em]">{label}</div>
      {hint && <p className="mt-1.5 text-[12px] leading-[1.7] text-on-surface/45 max-w-[62ch]">{hint}</p>}
    </div>
    <div className={stack ? '' : 'shrink-0 flex items-center justify-end'}>{children}</div>
  </div>
);

/* ── Toggle ─────────────────────────────────────────────────────────────────
   On = inverted fill, exactly like the site's primary button: the knob takes the
   page background so it reads correctly on light and dark palettes alike. */
export const Toggle = ({ checked, onChange, label }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string;
}) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    onClick={() => onChange(!checked)}
    className={`px-interactive relative w-[46px] h-[26px] rounded-full shrink-0 border cursor-pointer focus-visible:shadow-focus ${
      checked ? 'bg-on-surface border-on-surface' : 'bg-transparent border-on-surface/25 hover:border-on-surface/45'
    }`}
  >
    <span
      className={`absolute top-1/2 -translate-y-1/2 w-[18px] h-[18px] rounded-full transition-all duration-300 ${
        checked ? 'left-[24px] bg-surface' : 'left-[3px] bg-on-surface/40'
      }`}
    />
  </button>
);

/* ── Field ──────────────────────────────────────────────────────────────────
   A first pass styled these as a bare underline with a 25%-opacity placeholder.
   It matched the site, but it did not read as a text box — with a password field
   (which renders dots) it was not obvious that typing had registered at all.
   So: keep the hairline language, but give the input a real filled area, a
   legible placeholder and a visible focus state. Affordance beats purity.

   `label` is optional: left unset, `aria-label` renders as nothing and the
   browser falls back to the placeholder for the accessible name, which every
   call site supplies. Pass it where the placeholder is an example rather than
   a description ("Work", "hey primnox"). */
export const Field = ({ value, onChange, placeholder, type = 'text', mono = false, suffix, label }: {
  value: string; onChange: (v: string) => void; placeholder?: string;
  type?: string; mono?: boolean; suffix?: ReactNode; label?: string;
}) => (
  <div className="flex items-center gap-2 w-full group">
    <div className="relative flex-1 min-w-0">
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        spellCheck={false}
        autoComplete="off"
        aria-label={label}
        className={`w-full bg-[var(--surface)] border border-on-surface/15
          hover:border-on-surface/30 focus:border-primary focus:bg-[var(--p-faint)]
          outline-none rounded px-3.5 py-2.5 text-[13px] text-on-surface
          placeholder:text-on-surface/60 transition-colors
          ${mono ? 'font-mono text-[12px]' : ''}`}
      />
    </div>
    {suffix}
  </div>
);

/* Secret input: masked by default with a reveal toggle. Keys are never rendered
   in plain text unless the user asks for it. */
export const SecretField = ({ value, onChange, placeholder, label }: {
  value: string; onChange: (v: string) => void; placeholder?: string; label?: string;
}) => {
  const [shown, setShown] = useState(false);
  const isSet = value.trim().length > 0;
  return (
    <div className="w-full">
      <Field
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        label={label}
        type={shown ? 'text' : 'password'}
        mono
        suffix={
          <button
            type="button"
            onClick={() => setShown(s => !s)}
            aria-label={shown ? 'Hide value' : 'Reveal value'}
            className="p-2 text-on-surface/60 hover:text-on-surface transition-colors shrink-0"
          >
            {shown ? <EyeOff size={14} /> : <Eye size={14} />}
          </button>
        }
      />
      {/* A masked field gives no sign that input registered. This says so
          without putting the secret on screen. */}
      <div className="mt-1.5 flex items-center gap-1.5">
        {isSet
          ? <><Check size={10} className="text-[var(--green)]" />
              <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-[var(--green)]">
                Set · {value.trim().length} chars
              </span></>
          : <span className="font-mono text-[9px] uppercase tracking-[0.12em] text-on-surface/55">
              Not set
            </span>}
      </div>
    </div>
  );
};

/* Unlike an <input>, a <select> has no placeholder to fall back on, so without
   `label` it reaches a screen reader with no accessible name at all. Required
   for that reason — every call site passes one. */
export const Select = ({ value, onChange, options, label }: {
  value: string; onChange: (v: string) => void; options: { value: string; label: string }[];
  label: string;
}) => (
  <select
    value={value}
    onChange={(e) => onChange(e.target.value)}
    aria-label={label}
    className="bg-[var(--surface)] border border-on-surface/15 hover:border-on-surface/30
      focus:border-primary outline-none rounded px-3.5 py-2.5 pr-8 font-mono text-[12px]
      text-on-surface cursor-pointer transition-colors"
  >
    {options.map(o => (
      /* Menu items render in the OS popup, which does not inherit our tokens —
         colour-scheme on <html> is what makes these legible per theme. */
      <option key={o.value} value={o.value} className="bg-surface text-on-surface">{o.label}</option>
    ))}
  </select>
);

/* ── Slider ─────────────────────────────────────────────────────────────────
   Hairline track, primary-filled to the thumb. Fill is painted with a gradient
   so it needs no extra element and stays exact at any width.

   Thumb and track styling live in tailwind.css as `.px-slider`. They used to be
   an inline <style> block built around a useId() selector, which put an
   identical copy in the DOM for every slider on the screen; nothing in it
   depended on the instance.

   `label` is required for the same reason as on Select — a range input has no
   placeholder, so without it the control is announced unnamed. `aria-valuetext`
   carries the formatted value, so a reader says "168h" rather than "168". */
export const Slider = ({ value, onChange, min = 0, max = 100, step = 1, format, label }: {
  value: number; onChange: (v: number) => void;
  min?: number; max?: number; step?: number; format?: (v: number) => string;
  label: string;
}) => {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex items-center gap-5 w-full max-w-[340px]">
      <input
        type="range"
        min={min} max={max} step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-label={label}
        aria-valuetext={format ? format(value) : undefined}
        className="px-slider flex-1 appearance-none bg-transparent cursor-pointer outline-none"
        style={{
          background: `linear-gradient(to right, var(--primary) ${pct}%, var(--border) ${pct}%)`,
          height: '1px',
        }}
      />
      <span className="font-mono text-[11px] text-on-surface/60 tabular-nums w-11 text-right shrink-0">
        {format ? format(value) : value}
      </span>
    </div>
  );
};

/* ── Buttons ────────────────────────────────────────────────────────────────
   `px-btn` / `px-btn-ghost` are the site's own button classes (tailwind.css). */
export const Button = ({ children, onClick, variant = 'ghost', disabled, title }: {
  children: ReactNode; onClick?: () => void;
  variant?: 'solid' | 'ghost' | 'danger'; disabled?: boolean; title?: string;
}) => {
  const base = 'px-interactive cursor-pointer disabled:opacity-35 disabled:pointer-events-none';
  const cls =
    variant === 'solid' ? `px-btn ${base}`
    : variant === 'danger'
      ? `${base} font-mono text-[10px] uppercase tracking-[0.14em] px-6 py-3 rounded-full border border-error/40 text-error hover:bg-error/10`
      : `px-btn-ghost ${base}`;
  return (
    <button type="button" onClick={onClick} disabled={disabled} title={title} className={cls}>
      {children}
    </button>
  );
};

/* ── Choice ─────────────────────────────────────────────────────────────────
   A selectable option in a set (privacy architecture, storage provider). Reads
   as a hairline tile that gains a primary rule and tint when chosen — no
   drop shadow, no heavy fill. */
export const Choice = ({ selected, onClick, icon, title, hint }: {
  selected: boolean; onClick: () => void; icon?: ReactNode; title: string; hint?: string;
}) => (
  <button
    type="button"
    onClick={onClick}
    aria-pressed={selected}
    className={`px-interactive text-left p-4 rounded-control border relative cursor-pointer ${
      selected
        ? 'border-[var(--p-line-2)] bg-[var(--p-fill)]'
        : 'border-on-surface/10 hover:border-on-surface/25 hover:bg-[var(--hover)]'
    }`}
  >
    <div className="flex items-center gap-2 mb-1.5">
      {icon && <span className={selected ? 'text-primary' : 'text-on-surface/58'}>{icon}</span>}
      <span className={`font-mono text-[10px] uppercase tracking-[0.14em] ${
        selected ? 'text-primary' : 'text-on-surface/70'
      }`}>{title}</span>
      {selected && <Check size={12} className="text-primary ml-auto shrink-0" />}
    </div>
    {hint && <p className="text-[11px] leading-[1.65] text-on-surface/60">{hint}</p>}
  </button>
);

/* Status line — mono, colour-coded, used for async results (backup ran, vault
   unlocked, connection failed). */
export const Status = ({ tone = 'muted', children }: {
  tone?: 'muted' | 'good' | 'warn' | 'bad'; children: ReactNode;
}) => {
  const colour =
    tone === 'good' ? 'text-[var(--green)]'
    : tone === 'warn' ? 'text-[var(--accent)]'
    : tone === 'bad' ? 'text-error'
    : 'text-on-surface/60';
  return (
    <span className={`font-mono text-[10px] uppercase tracking-[0.12em] ${colour}`}>{children}</span>
  );
};
