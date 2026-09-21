import { Suspense, lazy, useEffect, useState } from 'react'

import { MetronomoPage } from './pages/MetronomoPage'

// O mapa traz o Leaflet (~150 KB, mais o CSS dele) e so e usado na segunda aba. O
// app abre no METRONOMO — a tela que alguem precisa com uma parada em andamento e
// rede ruim —, e antes pagava o download do mapa inteiro para mostrar um botao
// "Iniciar". Agora o mapa so baixa quando a aba dele e aberta.
const MapaPage = lazy(() => import('./pages/MapaPage').then((m) => ({ default: m.MapaPage })))

type Aba = 'metronomo' | 'mapa'

/**
 * Roteamento manual por hash, no mesmo espirito do `noticias-app`: sao duas
 * telas, e uma lib de roteamento seria mais codigo que o app inteiro.
 *
 * Hash e nao path porque o hash dispensa qualquer configuracao de servidor — inclusive se um dia for aberto de
 * `file://` num tablet sem rede, que e um cenario plausivel num curso.
 */
function abaDoHash(): Aba {
  return window.location.hash.replace('#/', '') === 'mapa' ? 'mapa' : 'metronomo'
}

export function App() {
  const [aba, setAba] = useState<Aba>(abaDoHash)

  useEffect(() => {
    const aoTrocar = () => setAba(abaDoHash())
    window.addEventListener('hashchange', aoTrocar)
    return () => window.removeEventListener('hashchange', aoTrocar)
  }, [])

  return (
    <div className="app">
      <header className="cabecalho">
        <div className="cabecalho__interno">
          <nav className="abas">
            <a
              href="#/metronomo"
              className={aba === 'metronomo' ? 'aba aba--ativa' : 'aba'}
              aria-current={aba === 'metronomo' ? 'page' : undefined}
            >
              Metrônomo RCP
            </a>
            <a
              href="#/mapa"
              className={aba === 'mapa' ? 'aba aba--ativa' : 'aba'}
              aria-current={aba === 'mapa' ? 'page' : undefined}
            >
              Mapa de DEA
            </a>
          </nav>
        </div>
      </header>

      <main className="conteudo">
        {aba === 'metronomo' ? (
          <MetronomoPage />
        ) : (
          <Suspense fallback={<p className="estado">Carregando o mapa...</p>}>
            <MapaPage />
          </Suspense>
        )}
      </main>

      <footer className="rodape">
        <strong>Médico 360</strong> · Ferramentas de apoio à prática clínica
      </footer>
    </div>
  )
}
