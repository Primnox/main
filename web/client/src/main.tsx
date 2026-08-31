import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { initTheme } from './theme';
import './styles/tailwind.css';

// Before render, not in an effect — an effect runs after first paint, so a
// light-theme user would see the dark palette flash first.
initTheme();

const el = document.getElementById('root');
if (!el) throw new Error('#root missing');
createRoot(el).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
