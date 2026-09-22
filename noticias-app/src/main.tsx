import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'

// O roteador existe por causa dos links do digest por e-mail: `/artigo/:id` e
// `/preferencias`. Antes o app navegava só por estado interno, então esses dois
// links carregavam o feed genérico e o médico perdia o destaque que tinha
// escolhido ler — e o de `/preferencias` é o link de descadastro.
//
// O `serve.json` já reescreve qualquer caminho fora de `/assets` para o
// index.html, então não é preciso mexer no servidor.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
