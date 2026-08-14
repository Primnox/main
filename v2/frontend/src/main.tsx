import React from 'react'
import ReactDOM from 'react-dom/client'
import { MotionConfig } from 'motion/react'
import App from './App'
import './styles/tailwind.css'

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
