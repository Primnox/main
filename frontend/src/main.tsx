import React from 'react'
import ReactDOM from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './app/App.tsx'
import './styles/tailwind.css'
import { ErrorBoundary } from './app/components/ErrorBoundary'
import { initTheme, installThemeSync } from './app/hooks/useTheme'
import { installElectronBridge } from './bridge/electronBridge'

// Under Tauri there is no preload script, so `window.electron` has to be
// installed here — before React mounts and components start registering IPC
// listeners. No-op under Electron, where preload.js already provided it.
installElectronBridge();

// Apply the saved theme before the first paint, otherwise the window shows the
// default palette for a frame and then swaps — very visible on light themes.
initTheme();
// Keep this window's theme live even if it never mounts SettingsView (e.g.
// the Dynamic Island's own window) — see installThemeSync's doc comment.
installThemeSync();

// ── Island overlay window: make body transparent BEFORE React renders ─────────
// The tailwind base layer sets body { bg-surface } globally. When this window is
// the always-on-top island overlay (loaded with ?primnox_island=1), override
// that with inline styles so the Electron transparent window shows through.
if (new URLSearchParams(window.location.search).get('primnox_island') === '1') {
  document.documentElement.style.background = 'transparent';
  document.body.style.background = 'transparent';
  document.body.style.backgroundImage = 'none';
  // Also override the root div styles
  document.documentElement.style.height = '100%';
}

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    {/* tailwind.css already zeroes CSS animation for prefers-reduced-motion, but
        Motion animates inline styles from rAF, so that media query never touched
        the screen transitions, island morphs or toasts — the people who asked for
        less motion still got all of it. reducedMotion="user" makes Motion honour
        the same OS setting. */}
    <MotionConfig reducedMotion="user">
      <ErrorBoundary>
        <App />
      </ErrorBoundary>
    </MotionConfig>
  </React.StrictMode>,
)
