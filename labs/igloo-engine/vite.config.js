import { defineConfig } from 'vite';

export default defineConfig({
  server: { port: 5178, host: '127.0.0.1' },
  build: {
    target: 'esnext',
    rollupOptions: {
      output: {
        // Mirrors igloo.inc's split: a tiny entry shell + a fat 3D chunk.
        // Vite 8 runs on rolldown, which only accepts the function form.
        manualChunks(id) {
          return id.includes('node_modules/three') ? 'App3D' : undefined;
        },
      },
    },
  },
});
