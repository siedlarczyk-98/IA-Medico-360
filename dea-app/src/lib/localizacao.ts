/**
 * A lógica de localização, fora do React.
 *
 * Vive aqui, e não dentro do hook, pelo mesmo motivo de `metronomo.ts`: é o que
 * decide o que o socorrista vê, e precisa de teste sem depender de DOM. O hook
 * (`useLocalizacao`) só liga isto ao estado do componente.
 *
 * ## O defeito que isto veio consertar
 *
 * Timeout de GPS e posição indisponível viravam o estado `indisponivel`, que não
 * tinha interface NENHUMA: a tela só avisava quando a permissão era negada. O
 * centro de São Paulo era usado como se fosse a posição do usuário, a lista era
 * buscada a partir dele e as distâncias apareciam normalmente. Em ambiente
 * interno — onde o GPS demora, e onde as paradas acontecem — o socorrista via
 * aparelhos e distâncias de outro lugar, sem aviso.
 */

export type Coordenada = { lat: number; lng: number }

export type MotivoIndisponivel = 'sem-api' | 'timeout' | 'falha'

export type EstadoLocalizacao =
  | { situacao: 'buscando' }
  | { situacao: 'ok'; posicao: Coordenada; precisaoM: number }
  | { situacao: 'negada' }
  | { situacao: 'indisponivel'; motivo: MotivoIndisponivel }

/**
 * Primeira tentativa: rápida e de baixa precisão (rede/wi-fi). Responde em
 * ambiente interno, onde o GPS não pega, e aceita uma posição de até um minuto.
 */
export const OPCOES_RAPIDA: PositionOptions = {
  enableHighAccuracy: false,
  timeout: 5000,
  maximumAge: 60000,
}

/**
 * Segunda tentativa: GPS. Gasta bateria, mas a diferença entre 20 m e 2 km
 * decide se o "DEA mais próximo" é o certo.
 */
export const OPCOES_PRECISA: PositionOptions = {
  enableHighAccuracy: true,
  timeout: 10000,
  maximumAge: 0,
}

/**
 * Teto para a espera toda. O `timeout` do navegador só começa a contar DEPOIS
 * que a permissão é concedida: com o pedido de permissão ignorado, nenhum
 * callback é chamado e a tela ficaria "buscando" para sempre.
 */
export const ESPERA_MAXIMA_MS = 12000

const PERMISSAO_NEGADA = 1
const TEMPO_ESGOTADO = 3

type Relogio = {
  setTimeout: (fn: () => void, ms: number) => unknown
  clearTimeout: (id: never) => void
}

/**
 * Pede a localização em dois tempos e informa cada mudança por `aoMudar`.
 * Devolve a função que cancela — depois dela nenhum callback muda mais nada.
 */
export function solicitarLocalizacao(
  geo: Pick<Geolocation, 'getCurrentPosition'> | undefined,
  aoMudar: (estado: EstadoLocalizacao) => void,
  relogio: Relogio = globalThis as unknown as Relogio,
): () => void {
  if (!geo) {
    aoMudar({ situacao: 'indisponivel', motivo: 'sem-api' })
    return () => {}
  }

  let cancelado = false
  let melhorPrecisao: number | null = null

  const guarda = relogio.setTimeout(() => {
    if (!cancelado && melhorPrecisao === null) {
      aoMudar({ situacao: 'indisponivel', motivo: 'timeout' })
    }
  }, ESPERA_MAXIMA_MS)

  const aceitar = (pos: GeolocationPosition) => {
    if (cancelado) return
    // Uma posição pior que a que já temos não substitui a melhor.
    if (melhorPrecisao !== null && pos.coords.accuracy >= melhorPrecisao) return
    melhorPrecisao = pos.coords.accuracy
    relogio.clearTimeout(guarda as never)
    aoMudar({
      situacao: 'ok',
      posicao: { lat: pos.coords.latitude, lng: pos.coords.longitude },
      precisaoM: pos.coords.accuracy,
    })
  }

  const falhar = (erro: GeolocationPositionError) => {
    // Já existe uma posição real: a falha do refinamento não a invalida.
    if (cancelado || melhorPrecisao !== null) return
    relogio.clearTimeout(guarda as never)
    if (erro.code === PERMISSAO_NEGADA) {
      aoMudar({ situacao: 'negada' })
      return
    }
    aoMudar({
      situacao: 'indisponivel',
      motivo: erro.code === TEMPO_ESGOTADO ? 'timeout' : 'falha',
    })
  }

  const tentarPrecisa = () => {
    if (!cancelado) geo.getCurrentPosition(aceitar, falhar, OPCOES_PRECISA)
  }

  geo.getCurrentPosition(
    (pos) => {
      aceitar(pos)
      tentarPrecisa() // refina em segundo plano
    },
    (erro) => {
      if (cancelado) return
      if (erro.code === PERMISSAO_NEGADA) {
        falhar(erro)
        return
      }
      tentarPrecisa() // a rápida falhou; o GPS é a última chance
    },
    OPCOES_RAPIDA,
  )

  return () => {
    cancelado = true
    relogio.clearTimeout(guarda as never)
  }
}

export type AvisoDeLocalizacao = { texto: string; podeTentarDeNovo: boolean }

/**
 * O que a tela DIZ em cada estado. `null` = nada a dizer.
 *
 * Todo estado sem posição real tem texto. Era essa a lacuna: `indisponivel`
 * caía no `null` implícito e a tela seguia como se soubesse onde o usuário está.
 */
export function avisoDeLocalizacao(estado: EstadoLocalizacao): AvisoDeLocalizacao | null {
  switch (estado.situacao) {
    case 'ok':
    case 'buscando':
      return null
    case 'negada':
      return {
        texto:
          'Sem acesso à sua localização — mostrando o centro de São Paulo, não onde você está.',
        podeTentarDeNovo: true,
      }
    case 'indisponivel':
      if (estado.motivo === 'sem-api') {
        return {
          texto:
            'Este navegador não informa localização — mostrando o centro de São Paulo, ' +
            'não onde você está.',
          podeTentarDeNovo: false,
        }
      }
      return {
        texto:
          'Não foi possível obter sua localização (comum em ambiente interno) — mostrando ' +
          'o centro de São Paulo, não onde você está.',
        podeTentarDeNovo: true,
      }
  }
}
