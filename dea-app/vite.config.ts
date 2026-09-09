import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // `shared/` na raiz do monorepo. Este app e o unico que NAO e embed: nao vive
  // em iframe do LMS, nao tem identidade nem onboarding. O alias fica aqui
  // porque nao custa e evita reconfigurar os tres arquivos se um dia precisar.
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
  // Porta propria: 5173 e o app principal, 5174 as calculadoras, 5175 as LPs,
  // 5176 as noticias.
  server: { port: 5177 },
})
