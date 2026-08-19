/* The ten palettes, and the one place that applies them.
 *
 * styles/themes.css has defined all ten since it was ported from
 * primnox.github.io, keyed on `data-theme` on <html>. Nothing ever set that
 * attribute, so nine of them had never been rendered by this app at all — the
 * CSS shipped, the switch did not exist.
 *
 * The swatch colours below are COPIES of each theme's --bg / --primary /
 * --accent. Copying is deliberate: reading them back with getComputedStyle
 * means mounting each theme to sample it, which flashes ten palettes across the
 * screen on first paint. They exist only to draw a 3-dot preview; if one drifts
 * the preview is slightly wrong and nothing else is, whereas the live UI always
 * reads the real token.
 */
export type ThemeName =
  | 'signature' | 'void' | 'carbon' | 'midnight' | 'ember'
  | 'phosphor' | 'paper' | 'clinical' | 'sand' | 'mono';

export type Theme = {
  name: ThemeName;
  label: string;
  /** Whether the ground is light. Drives contrast checks, not styling. */
  light: boolean;
  swatch: { bg: string; primary: string; accent: string };
};

export const THEMES: Theme[] = [
  { name: 'signature', label: 'Signature', light: false,
    swatch: { bg: '#070707', primary: '#c3c0ff', accent: '#ffb695' } },
  { name: 'void', label: 'Void', light: false,
    swatch: { bg: '#000000', primary: '#ffffff', accent: '#ff4f2b' } },
  { name: 'carbon', label: 'Carbon', light: false,
    swatch: { bg: '#0e1014', primary: '#5fd8ff', accent: '#ffcc66' } },
  { name: 'midnight', label: 'Midnight', light: false,
    swatch: { bg: '#060a1a', primary: '#6ea8ff', accent: '#ff7ab8' } },
  { name: 'ember', label: 'Ember', light: false,
    swatch: { bg: '#140f0b', primary: '#f5a524', accent: '#ff6b5e' } },
  { name: 'phosphor', label: 'Phosphor', light: false,
    swatch: { bg: '#040a06', primary: '#4ade80', accent: '#d9f99d' } },
  { name: 'paper', label: 'Paper', light: true,
    swatch: { bg: '#f6f4ef', primary: '#4b3fbf', accent: '#b8501f' } },
  { name: 'clinical', label: 'Clinical', light: true,
    swatch: { bg: '#ffffff', primary: '#1447e6', accent: '#d81b4a' } },
  { name: 'sand', label: 'Sand', light: true,
    swatch: { bg: '#ece5d8', primary: '#1c6b47', accent: '#b0451a' } },
  { name: 'mono', label: 'Mono', light: true,
    swatch: { bg: '#f2f1ee', primary: '#121212', accent: '#3f3f3f' } },
];

export const DEFAULT_THEME: ThemeName = 'signature';

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

/** Apply and remember. `signature` is :root's own palette, so it clears the
 *  attribute rather than setting `data-theme="signature"` — same result, and it
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
 * so the app would paint `signature` and then repaint the real theme — a visible
 * flash of the wrong palette on every launch, worst on the light themes where
 * it is a full black-to-white flash. */
export function initTheme(): ThemeName {
  const name = storedTheme();
  applyTheme(name);
  return name;
}
