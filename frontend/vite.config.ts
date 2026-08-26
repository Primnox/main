import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 5273, not 5173 — v2 runs alongside v1 during the migration, and two dev
// servers fighting over one port is a needless way to lose an afternoon.
// 5311 is reserved for the navigation-composer prototype demo.
export default defineConfig({
  plugins: [react()],
  server: { port: 5273, strictPort: true },
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        demo: 'demo-composer.html',
      },
    },
  },
})
