import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Built into frontend/dist, which FastAPI serves. During `npm run dev` the
// /api calls proxy to the FastAPI process so both can run with hot reload.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
