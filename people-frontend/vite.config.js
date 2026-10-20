import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

function redirectBareBase() {
  const redirect = (req, res, next) => {
    const [path, query] = (req.url || '').split('?')
    if (path === '/app/people') {
      res.statusCode = 301
      res.setHeader('Location', query ? `/app/people/?${query}` : '/app/people/')
      res.end()
      return
    }
    next()
  }
  return {
    name: 'redirect-people-base',
    configureServer(server) {
      server.middlewares.use(redirect)
    },
    configurePreviewServer(server) {
      server.middlewares.use(redirect)
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), redirectBareBase()],
  base: '/app/people/',
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/media': {
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
    },
  },
  build: {
    sourcemap: true,  // Generates .map files; use 'inline' to embed (larger output)
    minify: false,    // Keeps code readable in DevTools
    target: 'esnext', // Modern output for better debugging
  },
})
