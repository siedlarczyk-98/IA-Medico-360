import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // `shared/` na raiz do monorepo: codigo que os tres apps compartilham (hoje o
  // onboarding, escrito uma vez para nao divergir entre eles).
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
          if (id.includes('react-router')) return 'router';
          if (id.includes('@tanstack/react-query')) return 'react-query';
        },
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
