import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: '/people-app/',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,  // Generates .map files; use 'inline' to embed (larger output)
    minify: false,    // Keeps code readable in DevTools
    target: 'esnext', // Modern output for better debugging
  },
})
