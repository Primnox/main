import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { readFileSync } from 'fs'

const pkg = JSON.parse(readFileSync('./package.json', 'utf-8'))

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    // Inject package.json version as a typed global — avoids import.meta.env TS issues
    '__APP_VERSION__': JSON.stringify(pkg.version),
  },

  base: process.env.NODE_ENV === 'production' ? './' : '/',
  server: {
    port: 5173,
  },
  build: {
    minify: 'terser',
    terserOptions: {
      compress: {
        drop_console: true,
        drop_debugger: true,
        pure_funcs: ['console.log', 'console.info', 'console.warn'],
        passes: 3
      },
      mangle: {
        toplevel: true,
        properties: false
      },
      format: {
        comments: false
      }
    },
    rollupOptions: {
      output: {
        manualChunks: undefined,
        entryFileNames: '[hash].js',
        chunkFileNames: '[hash].js',
        assetFileNames: '[hash].[ext]'
      }
    }
  }
})
