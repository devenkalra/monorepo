import { defineConfig } from 'vite'

export default defineConfig({
  base: '/app/flightstudio/',
  server: {
    host: '0.0.0.0',
    port: 5183,
    strictPort: true,
    // 127.0.0.1, not localhost: Node resolves localhost to ::1 first, nothing
    // listens there, and the fallback to IPv4 costs ~300ms on every single
    // call. That dwarfs the solve itself and makes live dragging stutter.
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/login': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/accounts': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/static': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/media': { target: 'http://127.0.0.1:8000', changeOrigin: true },
    },
  },
  build: {
    sourcemap: true,
    minify: false,
    rollupOptions: {
      input: {
        index: 'index.html',
        // The segment-model harness. Listed explicitly or a build would ship
        // only index.html and the page would 404 outside dev.
        program: 'program.html',
      },
    },
  },
})
