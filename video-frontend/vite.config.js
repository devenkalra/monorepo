import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const root = path.dirname(fileURLToPath(import.meta.url))
const nm = (pkg) => path.resolve(root, 'node_modules', pkg)

export default defineConfig({
  plugins: [react()],
  base: '/app/productions/',
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      react: nm('react'),
      'react-dom': nm('react-dom'),
      'react/jsx-runtime': path.resolve(root, 'node_modules/react/jsx-runtime.js'),
      'react/jsx-dev-runtime': path.resolve(root, 'node_modules/react/jsx-dev-runtime.js'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5181,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/login': { target: 'http://localhost:8000', changeOrigin: true },
      '/accounts': { target: 'http://localhost:8000', changeOrigin: true },
      '/static': { target: 'http://localhost:8000', changeOrigin: true },
      '/media': { target: 'http://localhost:8000', changeOrigin: true },
    },
  },
  build: {
    sourcemap: true,
    minify: false,
  },
})
