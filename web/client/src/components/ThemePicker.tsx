import { useState } from 'react';
import { THEMES, applyTheme, storedTheme, type ThemeName } from '../theme';

/* Just the rail's one-press theme cycle. Desktop also exports a full
   ThemePicker grid, which belongs in a Settings section web has not ported —
   it is the only reason this file would need the ui/SectionHeader primitive.

   Cycles web's own four Tactical variants, not desktop's ten palettes. That is
   deliberate on web's side (see theme.ts) and the swatch shape is identical,
   so this component is unchanged either way. */
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
