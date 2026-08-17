import path from 'path'
import { fileURLToPath } from 'url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const root = path.dirname(fileURLToPath(import.meta.url))
const nm = (pkg) => path.resolve(root, 'node_modules', pkg)

export default defineConfig({
  plugins: [react()],
  base: '/app/trips/',
  resolve: {
    dedupe: ['react', 'react-dom'],
    alias: {
      '@bldrdojo/markdown-editor': path.resolve(root, '../shared-frontend/markdown-editor/src/index.js'),
      react: nm('react'),
      'react-dom': nm('react-dom'),
      'react/jsx-runtime': path.resolve(root, 'node_modules/react/jsx-runtime.js'),
      'react/jsx-dev-runtime': path.resolve(root, 'node_modules/react/jsx-dev-runtime.js'),
      'react-markdown': nm('react-markdown'),
      'remark-gfm': nm('remark-gfm'),
      'rehype-raw': nm('rehype-raw'),
    },
  },
  server: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    fs: {
      allow: [root, path.resolve(root, '../shared-frontend')],
    },
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
