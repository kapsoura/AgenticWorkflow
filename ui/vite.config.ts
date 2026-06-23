import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(() => ({
  // GitHub Pages serves project sites under /<repo>/, so asset URLs must be
  // rooted there for that target. Vercel (and dev) serve from "/" — set
  // GITHUB_PAGES=true only for GitHub Pages builds (see deploy-pages.yml and
  // the "deploy" script in package.json).
  base: process.env.GITHUB_PAGES === 'true' ? '/AgenticWorkflow/' : '/',
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
}))
