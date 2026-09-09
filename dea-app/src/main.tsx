import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
// Antes do nosso CSS, para que `index.css` possa sobrescrever o que precisar
// (a atribuição do OSM, os controles de zoom).
import 'leaflet/dist/leaflet.css'
import './index.css'

const raiz = document.getElementById('root')
if (raiz === null) throw new Error('Elemento #root não encontrado')

createRoot(raiz).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
