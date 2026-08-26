import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// 5273, not 5173 — v2 runs alongside v1 during the migration, and two dev
// servers fighting over one port is a needless way to lose an afternoon.
//
// proto.html is a second entry point, not a second app: it mounts the UI
// research prototypes behind a switcher so all thirteen are reachable from one
// dev server. Thirteen prototypes on thirteen ports was the alternative, and
// nobody was going to run thirteen servers to compare two components.
export default defineConfig({
  plugins: [react()],
  server: { port: 5273, strictPort: true },
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
        proto: 'proto.html',
      },
    },
  },
})
