import { useState } from 'react';
import { Check } from 'lucide-react';
import { THEMES, applyTheme, storedTheme, type ThemeName } from '../lib/themes';
import { SectionHeader } from './ui';

/* Four substrates as four swatches — two dark, two light.
 *
 * Each is a real <button>, not a div with a click handler, so it is reachable
 * by Tab and gets the global focus ring for free. The accessible name carries
 * both the palette and its state — "Phosphor theme, active" — because the
 * checkmark that says "active" to a sighted user says nothing otherwise.
 *
 * Applied on click rather than behind a Save: a palette is the one setting whose
 * effect IS the preview, and making someone commit before seeing it means
 * choosing blind.
 */
export function ThemePicker() {
  const [current, setCurrent] = useState<ThemeName>(() => storedTheme());

  const choose = (name: ThemeName) => {
    applyTheme(name);
    setCurrent(name);
  };

  return (
    <section className="space-y-4">
      <SectionHeader title="Appearance" level={3}
        note="One system, four substrates. Applied immediately and remembered." />

      <ul role="list" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {THEMES.map(t => {
          const active = t.name === current;
          return (
            <li key={t.name}>
              <button type="button" onClick={() => choose(t.name)}
                aria-label={`${t.label} theme${active ? ', active' : ''}`}
                aria-pressed={active}
                className={`px-interactive w-full flex items-center gap-2.5 rounded-xl border
                            px-3 py-2.5 text-left
                  ${active ? 'border-on-surface/40 bg-on-surface/[0.05]'
                           : 'border-on-surface/[0.10] hover:border-on-surface/25'}`}>
                {/* The preview has to paint its own colours — it is showing a
                    palette that is not the active one, so tokens cannot help. */}
                <span aria-hidden="true"
                  className="relative h-7 w-7 shrink-0 overflow-hidden rounded-full border border-on-surface/20"
                  style={{ background: t.swatch.bg }}>
                  <span className="absolute inset-x-0 bottom-0 h-1/2"
                    style={{ background: t.swatch.primary }} />
                  <span className="absolute bottom-0 right-0 h-1/2 w-1/2"
                    style={{ background: t.swatch.accent }} />
                </span>

                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px]">{t.label}</span>
                  <span className="px-label block">{t.light ? 'light' : 'dark'}</span>
                </span>

                {active && <Check size={14} className="shrink-0 text-on-surface/70" aria-hidden="true" />}
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* The same choice as a single cycling control, for the rail's foot.
 *
 * A swatch grid does not fit a 64px rail, and a dropdown there would cover the
 * conversation list. Cycling keeps it to one button; the full grid stays in
 * Settings for picking deliberately rather than stepping through.
 *
 * Cycling order runs dark → dim → light → paper, so the two substrates a user
 * is switching between for room brightness are adjacent, and crossing into the
 * light pair takes a deliberate second press rather than happening by accident
 * on the way back round.
 */
export function ThemeCycle() {
  const [current, setCurrent] = useState<ThemeName>(() => storedTheme());
  const index = Math.max(0, THEMES.findIndex(t => t.name === current));
  const next = THEMES[(index + 1) % THEMES.length];
  const active = THEMES[index];

  return (
    <button type="button"
      onClick={() => { applyTheme(next.name); setCurrent(next.name); }}
      aria-label={`Theme: ${active.label}. Switch to ${next.label}`}
      title={`Theme: ${active.label} — click for ${next.label}`}
      className="px-interactive relative h-6 w-6 overflow-hidden rounded-full
                 border border-on-surface/25 hover:border-on-surface/50"
      style={{ background: active.swatch.bg }}>
      <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-1/2"
        style={{ background: active.swatch.primary }} />
      <span aria-hidden="true" className="absolute bottom-0 right-0 h-1/2 w-1/2"
        style={{ background: active.swatch.accent }} />
    </button>
  );
}
