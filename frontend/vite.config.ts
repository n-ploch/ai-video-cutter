import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const API_TARGET = process.env.API_TARGET ?? 'http://localhost:8000'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: true, // bind 0.0.0.0 so Docker port mapping works
    proxy: {
      '/api': API_TARGET,
      '/files': API_TARGET,
      '/health': API_TARGET,
    },
  },
})
