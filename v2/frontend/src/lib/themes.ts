/* The world, and its one variant.
 *
 * There were ten palettes here, ported from primnox.github.io — six dark, four
 * light. They are gone, and their absence is the point: ten palettes is the
 * opposite of committing to an aesthetic, and a product that ships both a
 * light and a dark substrate has made every component decide twice and commit
 * to neither.
 *
 * What is left is Tactical Telemetry and a substrate variant. #0A0A0A and
 * #121212 are both named in the archetype; the difference between them is the
 * room you are sitting in, not a change of identity. Every other decision —
 * white phosphor, hazard red as the only accent, zero radius, monospace — is
 * identical across both, which is what makes this a variant rather than a
 * second theme.
 */
export type ThemeName = 'tactical' | 'tactical-dim';

export type Theme = {
  name: ThemeName;
  label: string;
  /** Whether the ground is light. Drives contrast checks, not styling. */
  light: boolean;
  swatch: { bg: string; primary: string; accent: string };
};

export const THEMES: Theme[] = [
  { name: 'tactical', label: 'Tactical', light: false,
    swatch: { bg: '#0A0A0A', primary: '#E61919', accent: '#4AF626' } },
  { name: 'tactical-dim', label: 'Tactical Dim', light: false,
    swatch: { bg: '#121212', primary: '#E61919', accent: '#4AF626' } },
];

export const DEFAULT_THEME: ThemeName = 'tactical';

const KEY = 'primnox2.theme';

const NAMES = new Set(THEMES.map(t => t.name));

function isTheme(value: unknown): value is ThemeName {
  return typeof value === 'string' && NAMES.has(value as ThemeName);
}

/** What is stored, or the default. Never throws — private mode denies access
 *  to localStorage entirely, and a theme lookup must not take the app down. */
export function storedTheme(): ThemeName {
  try {
    const raw = localStorage.getItem(KEY);
    if (isTheme(raw)) return raw;
  } catch { /* private mode */ }
  return DEFAULT_THEME;
}

/** Apply and remember. `tactical` is :root's own palette, so it clears the
 *  attribute rather than setting `data-theme="tactical"` — same result, and it
 *  keeps the DOM honest about which theme is the default. */
export function applyTheme(name: ThemeName): void {
  const root = document.documentElement;
  if (name === DEFAULT_THEME) delete root.dataset.theme;
  else root.dataset.theme = name;
  try { localStorage.setItem(KEY, name); } catch { /* private mode */ }
}

/** Called from main.tsx before React mounts.
 *
 * Before first paint, not in an effect: an effect runs after the first render,
 * so the app would paint `tactical` and then repaint the real theme — a visible
 * flash of the wrong palette on every launch, worst on the light themes where
 * it is a full black-to-white flash. */
export function initTheme(): ThemeName {
  const name = storedTheme();
  applyTheme(name);
  return name;
}
