import { useCallback, useEffect, useState } from 'react';

// Themes are defined in src/styles/themes.css and ported from the live site
// (primnox.github.io) so the app and the marketing site match exactly.
// `signature` is the :root default and therefore carries no data-theme value.
export const THEMES = [
  { id: 'signature', label: 'Signature', dark: true,  swatch: ['#070707', '#c3c0ff', '#ffb695'] },
  { id: 'void',      label: 'Void',      dark: true,  swatch: ['#000000', '#ffffff', '#ff4f2b'] },
  { id: 'carbon',    label: 'Carbon',    dark: true,  swatch: ['#0e1014', '#5fd8ff', '#ffcc66'] },
  { id: 'midnight',  label: 'Midnight',  dark: true,  swatch: ['#060a1a', '#6ea8ff', '#ff7ab8'] },
  { id: 'ember',     label: 'Ember',     dark: true,  swatch: ['#140f0b', '#f5a524', '#ff6b5e'] },
  { id: 'phosphor',  label: 'Phosphor',  dark: true,  swatch: ['#040a06', '#4ade80', '#d9f99d'] },
  { id: 'paper',     label: 'Paper',     dark: false, swatch: ['#f6f4ef', '#4b3fbf', '#b8501f'] },
  { id: 'clinical',  label: 'Clinical',  dark: false, swatch: ['#ffffff', '#1447e6', '#d81b4a'] },
  { id: 'sand',      label: 'Sand',      dark: false, swatch: ['#ece5d8', '#1c6b47', '#b0451a'] },
  { id: 'mono',      label: 'Mono',      dark: false, swatch: ['#f2f1ee', '#121212', '#3f3f3f'] },
] as const;

export type ThemeId = typeof THEMES[number]['id'];

const STORAGE_KEY = 'primnox.theme';
const DEFAULT_THEME: ThemeId = 'signature';

function isValid(id: string | null): id is ThemeId {
  return !!id && THEMES.some(t => t.id === id);
}

export function applyTheme(id: ThemeId): void {
  const root = document.documentElement;
  // The default lives on :root itself, so it must clear the attribute rather
  // than set data-theme="signature" — no such selector exists.
  if (id === DEFAULT_THEME) root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', id);

  // Let the OS style form controls, scrollbars and the like to match.
  const theme = THEMES.find(t => t.id === id);
  root.style.colorScheme = theme && !theme.dark ? 'light' : 'dark';
}

/** Read the stored theme and apply it before React paints. */
export function initTheme(): ThemeId {
  let stored: string | null = null;
  try { stored = localStorage.getItem(STORAGE_KEY); } catch { /* private mode */ }
  const id = isValid(stored) ? stored : DEFAULT_THEME;
  applyTheme(id);
  return id;
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeId>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (isValid(stored)) return stored;
    } catch { /* private mode */ }
    return DEFAULT_THEME;
  });

  useEffect(() => { applyTheme(theme); }, [theme]);

  // Keep multiple windows in sync — the Island overlay is a second window
  // loading the same app, and it should not sit on a different theme.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && isValid(e.newValue)) setThemeState(e.newValue);
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  const setTheme = useCallback((id: ThemeId) => {
    setThemeState(id);
    try { localStorage.setItem(STORAGE_KEY, id); } catch { /* private mode */ }
  }, []);

  return { theme, setTheme, themes: THEMES };
}
