import { useEffect, useState } from 'react'

import { MetronomoPage } from './pages/MetronomoPage'

type Aba = 'metronomo' | 'mapa'

/**
 * Roteamento manual por hash, no mesmo espirito do `noticias-app`: sao duas
 * telas, e uma lib de roteamento seria mais codigo que o app inteiro.
 *
 * Hash e nao path porque o app e servido por `serve -s` (SPA fallback), e o hash
 * dispensa qualquer configuracao de servidor — inclusive se um dia for aberto de
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
        <p className="cabecalho__marca">Médico 360</p>
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
      </header>

      <main className="conteudo">
        {aba === 'metronomo' ? (
          <MetronomoPage />
        ) : (
          <div className="em-breve">
            <h1>Mapa de DEA</h1>
            <p>
              Em construção. Aqui vai ficar o mapa colaborativo de desfibriladores
              externos automáticos.
            </p>
          </div>
        )}
      </main>

      <footer className="rodape">
        Em caso de parada cardiorrespiratória, ligue <strong>192 (SAMU)</strong> e
        inicie a reanimação enquanto o DEA é buscado.
      </footer>
    </div>
  )
}
