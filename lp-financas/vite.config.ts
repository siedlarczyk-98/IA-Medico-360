import path from 'node:path'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
      // `shared/` na raiz do monorepo: o handshake de identidade com a Waid,
      // escrito uma vez e usado por todos os apps do repo.
      '@shared': path.resolve(import.meta.dirname, '../shared'),
    },
    // `shared/` fica fora deste pacote, entao a resolucao de modulos a partir
    // dele sobe ate a raiz e nao encontra node_modules — nem o React. `dedupe`
    // forca a resolucao a partir daqui, e garante uma copia so (duas quebrariam
    // os hooks).
    dedupe: ['react', 'react-dom'],
  },
  server: {
    port: 5175,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
