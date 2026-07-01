import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import '@medico360/shared/index.css'
import App from './App.tsx'
import { loadIntercom } from './lib/intercom'
import { IntercomIdentity } from './lib/IntercomIdentity'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 60_000,
      retry: 1,
    },
  },
})

const intercomAppId = import.meta.env.VITE_INTERCOM_APP_ID

// Inicializa o widget uma única vez, fora do React (não pisca com re-render).
if (intercomAppId) loadIntercom(intercomAppId)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
      {intercomAppId && <IntercomIdentity />}
    </QueryClientProvider>
  </StrictMode>,
)
