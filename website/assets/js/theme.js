/* Ten-theme colour system, ported from the live site.

   The palettes live in tokens.css as [data-theme] blocks; this only moves the
   attribute. "dark" is the :root default and has no selector of its own, so
   selecting it removes the attribute rather than setting data-theme="dark".

   A tiny inline script in each page's <head> applies the stored theme before
   first paint — without it every visit flashes the default palette first. */

import { bus } from './core.js';

export const THEMES = [
  { id: 'dark',     label: 'Dark',     dark: true },
  { id: 'void',     label: 'Void',     dark: true },
  { id: 'carbon',   label: 'Carbon',   dark: true },
  { id: 'midnight', label: 'Midnight', dark: true },
  { id: 'ember',    label: 'Ember',    dark: true },
  { id: 'phosphor', label: 'Phosphor', dark: true },
  { id: 'paper',    label: 'Paper',    dark: false },
  { id: 'clinical', label: 'Clinical', dark: false },
  { id: 'sand',     label: 'Sand',     dark: false },
  { id: 'mono',     label: 'Mono',     dark: false },
];

const KEY = 'primnox-theme';   // same key as the live site, so it carries over
const DEFAULT = 'dark';

const byId = (id) => THEMES.find((t) => t.id === id);

export function currentTheme() {
  return document.documentElement.getAttribute('data-theme') || DEFAULT;
}

export function applyTheme(id) {
  const theme = byId(id) || byId(DEFAULT);
  const root = document.documentElement;

  if (theme.id === DEFAULT) root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', theme.id);

  // Lets the OS style form controls and scrollbars to match.
  root.style.colorScheme = theme.dark ? 'dark' : 'light';

  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    meta.content = getComputedStyle(root).getPropertyValue('--bg').trim() || '#070707';
  }

  const nameEl = document.getElementById('themeName');
  if (nameEl) nameEl.textContent = theme.label;

  const btn = document.getElementById('themeTg');
  if (btn) btn.title = `Theme: ${theme.label} — click or press T to cycle`;

  try { localStorage.setItem(KEY, theme.id); } catch { /* private mode */ }

  // Canvas colours are sampled from CSS vars, so they must be re-read.
  bus.emit('theme:change', theme);
}

export function cycleTheme(step = 1) {
  const i = THEMES.findIndex((t) => t.id === currentTheme());
  const next = THEMES[(((i + step) % THEMES.length) + THEMES.length) % THEMES.length];
  applyTheme(next.id);
}

export function initTheme() {
  // The head script already set the attribute; sync the rest of the UI to it.
  applyTheme(currentTheme());

  document.getElementById('themeTg')?.addEventListener('click', () => cycleTheme(1));

  addEventListener('keydown', (e) => {
    if (e.key !== 't' && e.key !== 'T') return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    const el = document.activeElement;
    if (el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName))) return;
    cycleTheme(e.shiftKey ? -1 : 1);
  });

  // Another tab changed it.
  addEventListener('storage', (e) => {
    if (e.key === KEY && e.newValue && byId(e.newValue)) applyTheme(e.newValue);
  });
}
