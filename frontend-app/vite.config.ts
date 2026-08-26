import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('react-markdown')) return 'react-markdown';
          if (id.includes('react-router')) return 'router';
          if (id.includes('@tanstack/react-query')) return 'react-query';
        },
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    // Só os testes do app. Sem isto o vitest varre node_modules e o e2e do
    // Playwright de outros pacotes, que usam um runner diferente.
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    css: false,
  },
})
