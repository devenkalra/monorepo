import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'public-gallery-spa-fallback',
      configureServer(server) {
        // Must not steal /api/gallery/* (backend) or reserved first segments.
        const reserved = new Set([
          'app', 'apps', 'admin', 'accounts', 'api', 'static', 'media',
          'login', 'logout', 'health', 'favicon.ico', 'robots.txt',
        ])
        server.middlewares.use((req, _res, next) => {
          const url = req.url || ''
          const m = url.match(/^\/([^/?#]+)\/gallery(\/|$|\?)/)
          if (m && !reserved.has(m[1].toLowerCase())) {
            req.url = '/app/gallery/'
          }
          next()
        })
      },
    },
  ],
  base: '/app/gallery/',
  server: {
    host: '0.0.0.0',
    port: 5178,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/login': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/accounts': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,
    minify: false,
  },
})
