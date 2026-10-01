import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'node:path'

// FastAPI backend (backend/app/main.py) — `make run` serves it on port 8000.
const backendUrl = process.env.VITE_BACKEND_URL || 'http://localhost:8000'

// Vite config — https://vitejs.dev/config/
export default defineConfig({
  // Single .env at the repo root; only VITE_* variables reach the browser.
  envDir: '..',
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // 5173 is already allowed by CORS_ORIGINS in .env.example
    port: 5173,
    strictPort: true,
    // Backend paths are proxied, so they never collide with frontend routes
    proxy: {
      '/api': backendUrl,
      '/health': backendUrl,
    },
  },
  preview: {
    port: 5173,
  },
})
