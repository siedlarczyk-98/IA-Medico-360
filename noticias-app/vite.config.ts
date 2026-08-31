import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  // Porta propria: 5173 e o app principal, 5174 as calculadoras, 5175 as LPs.
  server: { port: 5176 },
})
