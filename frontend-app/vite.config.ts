import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // `shared/` na raiz do monorepo: código que os tres apps compartilham (hoje o
  // onboarding). Alias em vez de npm workspaces porque workspaces arrastariam
  // build, CI e Dockerfile dos tres de uma vez, sem destravar nada a mais.
  resolve: {
    alias: {
      '@shared': fileURLToPath(new URL('../shared', import.meta.url)),
    },
    // `shared/` fica fora deste pacote, entao a resolucao de modulos a partir
    // dele sobe ate a raiz do monorepo e nao encontra node_modules — nem o
    // React. `dedupe` forca a resolucao a partir daqui, e de quebra garante uma
    // unica copia do React (duas quebrariam os hooks).
    dedupe: ['react', 'react-dom'],
  },
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
