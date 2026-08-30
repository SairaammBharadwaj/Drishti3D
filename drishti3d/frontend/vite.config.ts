import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The frontend talks to the FastAPI backend on :8000. We proxy /api so that
// uploads and the SSE progress stream work with no CORS during development.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
  },
})
