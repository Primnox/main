import { defineConfig } from 'vitest/config';

// Kept separate from vite.config.ts: the app build runs terser with
// `drop_console`, which would strip the console warnings the bridge tests
// assert on.
export default defineConfig({
  test: {
    environment: 'jsdom',
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    globals: false,
    restoreMocks: true,
  },
});
