import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In development, requests to /api go to the FastAPI backend on port 8000.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_URL || 'http://localhost:8000',
    },
  },
})
