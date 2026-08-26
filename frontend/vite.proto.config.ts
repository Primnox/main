import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Proto server runs on 5307, separate from the main v2 frontend (5273)
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5307,
    strictPort: true,
  },
  build: {
    outDir: 'dist-proto',
  },
  root: '.',
})
