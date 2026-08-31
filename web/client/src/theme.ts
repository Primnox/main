/* The world, and its substrate variants.
 *
 * There were ten palettes here, ported from primnox.github.io. They are gone,
 * and their absence is the point: ten palettes is the opposite of committing
 * to an aesthetic. What replaced them was Tactical Telemetry and one dim
 * variant — #0A0A0A and #121212 are both named in the archetype, and the
 * difference between them is the room you are sitting in, not a change of
 * identity.
 *
 * The light pair is a later, narrower concession, and the reasoning matters
 * because this file used to argue the opposite. The old argument was that
 * shipping both a light and a dark substrate makes every component decide
 * twice and commit to neither. That is a real cost and it still applies. What
 * outweighs it is that dark-only is not a taste question for everyone:
 * photophobia, migraine and some low-vision conditions make a light ground a
 * medical requirement rather than a preference, and DESIGN.md holds WCAG 2.1
 * AA as a defect line. Claiming that line while shipping no reachable light
 * ground was the actual inconsistency.
 *
 * So this is an accessibility accommodation, not a style pivot. Every other
 * decision — hazard red as the only accent, zero radius, monospace, one
 * accent — is identical across all four, which is what keeps these variants
 * rather than four themes. Do not add a fifth on grounds of taste.
 */
export type ThemeName =
  | 'tactical'
  | 'tactical-dim'
  | 'tactical-light'
  | 'tactical-light-dim';

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
  { name: 'tactical-light', label: 'Tactical Light', light: true,
    swatch: { bg: '#F5F5F5', primary: '#E61919', accent: '#4AF626' } },
  { name: 'tactical-light-dim', label: 'Tactical Paper', light: true,
    swatch: { bg: '#FAFAFA', primary: '#E61919', accent: '#4AF626' } },
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
