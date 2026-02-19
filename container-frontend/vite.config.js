import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: '/',
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/people-app': {
        target: 'http://localhost:5173',
        changeOrigin: true,
        ws: true,
      },
      '/cad-app': {
        target: 'http://localhost:5174',
        changeOrigin: true,
        ws: true,
      },
      '/food-app': {
        target: 'http://localhost:5175',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  build: {
    sourcemap: true,
    minify: false,
  },
})
