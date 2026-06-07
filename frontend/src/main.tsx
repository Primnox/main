import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './app/App.tsx'
import './styles/tailwind.css'
import { ErrorBoundary } from './app/components/ErrorBoundary'

// ── Island overlay window: make body transparent BEFORE React renders ─────────
// The tailwind base layer sets body { bg-black } globally. When this window is
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
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
