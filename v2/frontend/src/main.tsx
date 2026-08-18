import React from 'react'
import ReactDOM from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './App'
import { initTheme } from './lib/themes'
import './styles/tailwind.css'

// Before render, not in an effect. An effect runs after the first paint, so the
// app would show the default palette and then swap — a full black-to-white
// flash on every launch for anyone who picked one of the light themes.
initTheme()

// tailwind.css zeroes CSS animation for prefers-reduced-motion, but Motion
// animates inline styles from rAF, so that media query never reaches it.
// reducedMotion="user" makes Motion honour the same OS setting.
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <App />
    </MotionConfig>
  </React.StrictMode>,
)
