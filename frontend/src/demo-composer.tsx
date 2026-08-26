/**
 * Demo Entry Point for Navigation & Composer Prototype
 *
 * To use this demo:
 * 1. Create a new vite entry point or
 * 2. Temporarily import and render this in src/main.tsx instead of App
 *
 * This file wraps ComposerDemo with necessary theme initialization.
 */

import React from 'react';
import ReactDOM from 'react-dom/client';
import { MotionConfig } from 'motion/react';
import { ComposerDemo } from './components/proto/navigation-composer';
import { initTheme } from './lib/themes';
import './styles/tailwind.css';

initTheme();

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MotionConfig reducedMotion="user">
      <ComposerDemo />
    </MotionConfig>
  </React.StrictMode>,
);
