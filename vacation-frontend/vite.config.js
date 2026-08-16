import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/app/vacation/',
  server: {
    host: '0.0.0.0',
    port: 5179,
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
