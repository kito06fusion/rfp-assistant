import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  root: './frontend',
  plugins: [react()],
  server: {
    port: 8000,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      // Proxy all API endpoints to backend
      '/process-rfp': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/run-requirements': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/build-query': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/generate-response': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/preview-responses': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/update-response': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/generate-pdf-from-preview': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/generate-questions': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
      '/chat': {
        target: 'http://127.0.0.1:8001',
        changeOrigin: true,
      },
    },
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './frontend/src'),
    },
  },
})

