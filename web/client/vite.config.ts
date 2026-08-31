/// <reference types="vitest" />
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import tailwindcss from 'tailwindcss';
import autoprefixer from 'autoprefixer';

// base: served from a project page at cyanexani.github.io/primnox-chat (D8).
// port 5274 so it never fights the desktop v2 dev server on 5273.
// PostCSS is wired explicitly rather than via auto-discovered postcss.config.js.
export default defineConfig({
  base: '/primnox-chat/',
  plugins: [react()],
  server: { port: 5274, strictPort: true },
  css: {
    postcss: {
      plugins: [tailwindcss(), autoprefixer()],
    },
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
