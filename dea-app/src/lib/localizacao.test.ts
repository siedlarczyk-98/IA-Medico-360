import { describe, expect, it } from 'vitest'

import {
  ESPERA_MAXIMA_MS,
  type EstadoLocalizacao,
  OPCOES_PRECISA,
  OPCOES_RAPIDA,
  avisoDeLocalizacao,
  solicitarLocalizacao,
} from './localizacao'

/**
 * Geolocalização falsa: guarda cada pedido para o teste responder quando quiser.
 *
 * É o que permite reproduzir o defeito — o GPS que não responde, ou responde
 * com timeout — sem navegador e sem DOM.
 */
class GeoFalsa {
  pedidos: {
    sucesso: PositionCallback
    erro: PositionErrorCallback
    opcoes: PositionOptions
  }[] = []

  getCurrentPosition(
    sucesso: PositionCallback,
    erro?: PositionErrorCallback | null,
    opcoes?: PositionOptions,
  ) {
    this.pedidos.push({ sucesso, erro: erro ?? (() => {}), opcoes: opcoes ?? {} })
  }

  responder(indice: number, lat: number, lng: number, precisao: number) {
    this.pedidos[indice].sucesso({
      coords: { latitude: lat, longitude: lng, accuracy: precisao },
    } as GeolocationPosition)
  }

  falhar(indice: number, code: 1 | 2 | 3) {
    this.pedidos[indice].erro({ code } as GeolocationPositionError)
  }
}

class RelogioFalso {
  private fila: { id: number; fn: () => void; ms: number }[] = []
  private proximo = 1

  setTimeout = (fn: () => void, ms: number) => {
    this.fila.push({ id: this.proximo, fn, ms })
    return this.proximo++
  }

  clearTimeout = (id: never) => {
    this.fila = this.fila.filter((t) => t.id !== (id as number))
  }

  avancar(ms: number) {
    const vencidos = this.fila.filter((t) => t.ms <= ms)
    this.fila = this.fila.filter((t) => t.ms > ms)
    vencidos.forEach((t) => t.fn())
  }
}

function cenario() {
  const geo = new GeoFalsa()
  const relogio = new RelogioFalso()
  const estados: EstadoLocalizacao[] = []
  const cancelar = solicitarLocalizacao(geo, (e) => estados.push(e), relogio)
  return { geo, relogio, estados, cancelar, ultimo: () => estados.at(-1) }
}

const PERMISSAO_NEGADA = 1
const POSICAO_INDISPONIVEL = 2
const TIMEOUT = 3

describe('solicitarLocalizacao', () => {
  it('começa pela tentativa rápida, de baixa precisão', () => {
    const { geo } = cenario()

    expect(geo.pedidos).toHaveLength(1)
    expect(geo.pedidos[0].opcoes).toEqual(OPCOES_RAPIDA)
    expect(OPCOES_RAPIDA.enableHighAccuracy).toBe(false)
  })

  it('entrega a posição rápida e refina com o GPS em seguida', () => {
    const { geo, estados } = cenario()

    geo.responder(0, -23.56, -46.65, 1500)
    expect(estados.at(-1)).toEqual({
      situacao: 'ok',
      posicao: { lat: -23.56, lng: -46.65 },
      precisaoM: 1500,
    })
    expect(geo.pedidos[1].opcoes).toEqual(OPCOES_PRECISA)

    geo.responder(1, -23.5613, -46.6565, 12)
    expect(estados.at(-1)).toMatchObject({ situacao: 'ok', precisaoM: 12 })
  })

  it('uma posição PIOR não substitui a que já se tem', () => {
    const { geo, estados } = cenario()
    geo.responder(0, -23.56, -46.65, 40)

    geo.responder(1, -23.9, -46.9, 3000)

    expect(estados).toHaveLength(1)
    expect(estados[0]).toMatchObject({ precisaoM: 40 })
  })

  it('falha do refinamento não derruba a posição que já existe', () => {
    const { geo, ultimo } = cenario()
    geo.responder(0, -23.56, -46.65, 800)

    geo.falhar(1, TIMEOUT)

    expect(ultimo()).toMatchObject({ situacao: 'ok', precisaoM: 800 })
  })

  it('se a rápida falha, o GPS ainda é tentado antes de desistir', () => {
    const { geo, estados, ultimo } = cenario()

    geo.falhar(0, POSICAO_INDISPONIVEL)
    expect(estados).toHaveLength(0) // ainda "buscando": nada a anunciar
    expect(geo.pedidos[1].opcoes).toEqual(OPCOES_PRECISA)

    geo.responder(1, -23.56, -46.65, 25)
    expect(ultimo()).toMatchObject({ situacao: 'ok', precisaoM: 25 })
  })

  // O defeito da varredura de 2026-09-18: este estado não tinha interface.
  it('timeout nas duas tentativas vira INDISPONÍVEL por timeout, não silêncio', () => {
    const { geo, ultimo } = cenario()

    geo.falhar(0, TIMEOUT)
    geo.falhar(1, TIMEOUT)

    expect(ultimo()).toEqual({ situacao: 'indisponivel', motivo: 'timeout' })
  })

  it('posição indisponível vira INDISPONÍVEL por falha', () => {
    const { geo, ultimo } = cenario()

    geo.falhar(0, POSICAO_INDISPONIVEL)
    geo.falhar(1, POSICAO_INDISPONIVEL)

    expect(ultimo()).toEqual({ situacao: 'indisponivel', motivo: 'falha' })
  })

  it('permissão negada encerra na hora, sem insistir no GPS', () => {
    const { geo, ultimo } = cenario()

    geo.falhar(0, PERMISSAO_NEGADA)

    expect(ultimo()).toEqual({ situacao: 'negada' })
    expect(geo.pedidos).toHaveLength(1)
  })

  it('pedido de permissão ignorado não deixa a tela "buscando" para sempre', () => {
    // O `timeout` do navegador só conta depois da permissão concedida. Com o
    // pedido ignorado, NENHUM callback é chamado.
    const { relogio, ultimo } = cenario()

    relogio.avancar(ESPERA_MAXIMA_MS)

    expect(ultimo()).toEqual({ situacao: 'indisponivel', motivo: 'timeout' })
  })

  it('posição que chega depois do teto de espera ainda é aproveitada', () => {
    const { geo, relogio, ultimo } = cenario()
    relogio.avancar(ESPERA_MAXIMA_MS)

    geo.responder(0, -23.56, -46.65, 60)

    expect(ultimo()).toMatchObject({ situacao: 'ok', precisaoM: 60 })
  })

  it('o teto de espera não dispara depois que a posição chegou', () => {
    const { geo, relogio, estados } = cenario()
    geo.responder(0, -23.56, -46.65, 60)

    relogio.avancar(ESPERA_MAXIMA_MS)

    expect(estados.filter((e) => e.situacao === 'indisponivel')).toHaveLength(0)
  })

  it('depois de cancelar, nenhum callback muda mais nada', () => {
    const { geo, relogio, estados, cancelar } = cenario()

    cancelar()
    geo.responder(0, -23.56, -46.65, 10)
    geo.falhar(0, TIMEOUT)
    relogio.avancar(ESPERA_MAXIMA_MS)

    expect(estados).toHaveLength(0)
  })

  it('navegador sem a API responde na hora', () => {
    const estados: EstadoLocalizacao[] = []

    solicitarLocalizacao(undefined, (e) => estados.push(e))

    expect(estados).toEqual([{ situacao: 'indisponivel', motivo: 'sem-api' }])
  })
})

describe('avisoDeLocalizacao', () => {
  it('não diz nada quando há posição real ou ainda está buscando', () => {
    expect(avisoDeLocalizacao({ situacao: 'buscando' })).toBeNull()
    expect(
      avisoDeLocalizacao({ situacao: 'ok', posicao: { lat: 0, lng: 0 }, precisaoM: 10 }),
    ).toBeNull()
  })

  // A trava da classe: todo estado SEM posição real precisa dizer ao socorrista
  // que o mapa não mostra onde ele está.
  it.each<EstadoLocalizacao>([
    { situacao: 'negada' },
    { situacao: 'indisponivel', motivo: 'timeout' },
    { situacao: 'indisponivel', motivo: 'falha' },
    { situacao: 'indisponivel', motivo: 'sem-api' },
  ])('$situacao / $motivo avisa que a posição mostrada não é a do usuário', (estado) => {
    const aviso = avisoDeLocalizacao(estado)

    expect(aviso).not.toBeNull()
    expect(aviso?.texto).toContain('não onde você está')
  })

  it('oferece nova tentativa quando ela pode dar certo, e só então', () => {
    expect(avisoDeLocalizacao({ situacao: 'indisponivel', motivo: 'timeout' })?.podeTentarDeNovo).toBe(true)
    expect(avisoDeLocalizacao({ situacao: 'negada' })?.podeTentarDeNovo).toBe(true)
    expect(avisoDeLocalizacao({ situacao: 'indisponivel', motivo: 'sem-api' })?.podeTentarDeNovo).toBe(false)
  })
})
