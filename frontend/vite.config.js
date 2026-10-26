import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// dev server proxies /api to the backend
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': process.env.API_URL || 'http://localhost:8000',
    },
  },
})
