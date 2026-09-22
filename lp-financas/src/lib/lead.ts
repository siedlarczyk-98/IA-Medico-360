/**
 * Quem é o médico que abriu esta landing page.
 *
 * ANTES: vinha no `?email=` da URL, colocado lá pelo LMS.
 * AGORA: vem do handshake com a Waid, trocado por `/auth/embed/identidade`.
 *
 * POR QUE MUDOU
 * O `?email=` não prova nada, e a Waid o posiciona como legado. Nas telas
 * autenticadas isso era um buraco de segurança; aqui não é — a LP é pública e o
 * e-mail só pré-preenche um campo. Mas manter dois mecanismos de identidade
 * vivos significa manter os dois, e o antigo tem data para morrer.
 *
 * FALHAR AQUI É BARATO, E ISSO MUDA O DESENHO
 * Sem identidade, o lead digita o próprio e-mail — como em qualquer formulário
 * da internet. Por isso não há tela de erro: `pronto` fica `true` mesmo quando a
 * identificação falha, e o formulário simplesmente pede o e-mail. É o oposto
 * das telas autenticadas, onde falhar significa não entrar.
 *
 * `emailMissing` sobrevive à mudança: continua marcando explicitamente que a
 * plataforma não nos disse quem era, para dar para medir. Sem ela, "e-mail
 * nulo" fica ambíguo com o tempo (a plataforma falhou vs. o lead não quis dar).
 */

import { useEffect, useState } from 'react'

import { montarOrigensWaid, useIdentidadeSimplesWaid } from '@shared/embed/identidade'

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')
const WAID_ORIGIN = import.meta.env.VITE_WAID_ORIGIN ?? 'https://www.medico360.app'

/**
 * Duas origens, não uma: no navegador a resposta vem do portal da Waid; no app
 * nativo, do domínio público. Vale aqui como nos apps do produto — as LPs são
 * embedadas do mesmo jeito, e quem abre pelo celular abre pelo app.
 */
const ORIGENS_WAID = montarOrigensWaid(WAID_ORIGIN)

export interface Lead {
  email?: string
  name?: string
  emailMissing: boolean
}

/**
 * O lead resolvido, para quem não é componente React.
 *
 * `api.ts` monta o corpo do POST no momento do envio, fora do ciclo de render.
 * Guardar em módulo é o que permite isso sem passar o lead por três camadas de
 * props. Quando o envio acontece, a identificação já terminou — o formulário só
 * habilita depois.
 */
let leadAtual: Lead = { emailMissing: true }

export function getLead(): Lead {
  return leadAtual
}

/** Resolve a identidade uma vez, no carregamento da página. */
export function useLead(): { lead: Lead; pronto: boolean } {
  const [lead, setLead] = useState<Lead>(leadAtual)
  const [pronto, setPronto] = useState(false)

  const { fase } = useIdentidadeSimplesWaid({
    apiBase: API_BASE,
    waidOrigin: ORIGENS_WAID,
    aoIdentificar: ({ nome, email }) => {
      leadAtual = { email, name: nome ?? undefined, emailMissing: !email }
      setLead(leadAtual)
      setPronto(true)
    },
  })

  useEffect(() => {
    // Erro aqui não é erro para o usuário: seguimos sem identidade e o
    // formulário pede o e-mail. Acontece, por exemplo, nos aplicativos da Waid,
    // que abrem a seção sem iframe.
    if (fase === 'erro') {
      leadAtual = { emailMissing: true }
      // `fase` vem de um hook externo e 'erro' é terminal: um render a mais, uma
      // vez. Sem teste nestas páginas, não se mexe no fluxo por causa de lint.
      // eslint-disable-next-line react-hooks/set-state-in-effect -- ver acima
      setLead(leadAtual)
      setPronto(true)
    }
  }, [fase])

  return { lead, pronto }
}
