import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  BPM_MAXIMO,
  BPM_MINIMO,
  CICLO_SEGUNDOS,
  COMPRESSOES_POR_CICLO_302,
  Metronomo,
  VENTILACOES_POR_CICLO_302,
  formatarTempo,
  type TipoBatida,
} from './metronomo'

/**
 * AudioContext falso com relogio controlado pelo teste.
 *
 * O motor le `currentTime` e agenda osciladores em instantes absolutos; aqui
 * registramos cada instante agendado para poder medir a DERIVA, que e a
 * propriedade que realmente importa num metronomo de compressao toracica.
 */
class ContextoFalso {
  currentTime = 0
  state: 'running' | 'suspended' | 'interrupted' = 'running'
  onstatechange: (() => void) | null = null
  /** Instantes em que cada clique foi agendado, na ordem. */
  agendados: number[] = []
  /**
   * Quanto cada clique estava ATRASADO ao ser agendado (0 = no futuro). E o que
   * um AudioContext de verdade faz de diferente do falso antigo: `start()` num
   * instante ja passado nao viaja no tempo, toca AGORA. O falso aceitava o passado
   * calado, e por isso um teste chegou a exigir a rajada como comportamento certo.
   */
  atrasos: number[] = []
  destination = {}

  /** O sistema tira (ou devolve) o audio: ligacao, tela bloqueada. */
  mudarEstado(novo: 'running' | 'suspended' | 'interrupted') {
    this.state = novo
    this.onstatechange?.()
  }

  createOscillator() {
    const registrar = (quando: number) => {
      this.agendados.push(quando)
      this.atrasos.push(Math.max(0, this.currentTime - quando))
    }
    return {
      frequency: { value: 0 },
      type: 'sine',
      connect: () => {},
      start: registrar,
      stop: () => {},
    }
  }

  createGain() {
    return {
      gain: {
        setValueAtTime: () => {},
        linearRampToValueAtTime: () => {},
        exponentialRampToValueAtTime: () => {},
      },
      connect: () => {},
    }
  }

  /** `false` simula o iOS recusando o `resume()` sem gesto do usuario. */
  aceitaResume = true

  async resume() {
    if (!this.aceitaResume) throw new Error('NotAllowedError')
    this.mudarEstado('running')
  }

  async close() {}
}

let contexto: ContextoFalso

beforeEach(() => {
  vi.useFakeTimers()
  contexto = new ContextoFalso()
  // Precisa ser construtivel (`new AudioContext()`), entao uma arrow function
  // nao serve. A classe devolve sempre a MESMA instancia, para o teste manter
  // acesso ao relogio e a lista de agendamentos.
  vi.stubGlobal(
    'AudioContext',
    class {
      constructor() {
        return contexto
      }
    },
  )
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

/** Avanca o relogio de audio e o dos timers juntos, como no navegador. */
async function avancar(segundos: number) {
  const passoMs = 25
  const passos = Math.round((segundos * 1000) / passoMs)
  for (let i = 0; i < passos; i++) {
    contexto.currentTime += passoMs / 1000
    await vi.advanceTimersByTimeAsync(passoMs)
  }
}

/** Intervalos entre batidas consecutivas, a partir de um indice. */
function intervalosDesde(indice: number): number[] {
  const fatia = contexto.agendados.slice(indice)
  return fatia.slice(1).map((t, i) => t - fatia[i]!)
}

describe('Metronomo', () => {
  it('agenda batidas no intervalo correto para o bpm', async () => {
    const m = new Metronomo({ bpm: 120, modo302: false })
    await m.iniciar()
    await avancar(10)
    m.parar()

    // 120 bpm = 1 batida a cada 0,5s.
    for (const intervalo of intervalosDesde(0)) {
      expect(intervalo).toBeCloseTo(0.5, 6)
    }
  })

  it('depois de um congelamento, retoma NA GRADE e sem rajada', async () => {
    // INVERTIDO em 2026-09-21. Este teste exigia que as ~5 batidas perdidas num
    // congelamento de 3 s fossem todas agendadas ("sem perder batidas"). Num
    // AudioContext real, agendar no passado e tocar AGORA: as cinco saiam juntas,
    // numa rajada, no meio de uma massagem cardiaca. O falso aceitava o passado
    // sem reclamar, entao o teste passava confirmando o defeito.
    const m = new Metronomo({ bpm: 100, modo302: false })
    await m.iniciar()

    await avancar(5)
    const antes = contexto.agendados.length

    // Aba congela: o relogio de audio anda 3s, o timer so dispara uma vez.
    contexto.currentTime += 3
    await vi.advanceTimersByTimeAsync(25)
    await avancar(2)

    // Nenhum clique foi agendado com atraso que o ouvido perceba...
    expect(Math.max(...contexto.atrasos)).toBeLessThanOrEqual(0.025)
    // ...e o compasso voltou exatamente onde estaria: toda batida cai num
    // multiplo de 0,6 s da primeira. Pular batidas nao desloca a grade.
    const primeira = contexto.agendados[0]!
    for (const quando of contexto.agendados.slice(antes)) {
      const posicao = (quando - primeira) / 0.6
      expect(Math.abs(posicao - Math.round(posicao))).toBeLessThan(1e-6)
    }
    // O buraco existe: ~5 batidas de 0,6 s nao foram tocadas.
    const maiorIntervalo = Math.max(...intervalosDesde(0))
    expect(maiorIntervalo).toBeGreaterThan(2.9)
  })

  it('batida pulada nao conta como compressao', async () => {
    const m = new Metronomo({ bpm: 100, modo302: false })
    await m.iniciar()
    await avancar(5)
    const contadas = m.instantaneo().compressoes

    contexto.currentTime += 3 // ~5 batidas que ninguem ouviu
    await vi.advanceTimersByTimeAsync(25)

    expect(m.instantaneo().compressoes - contadas).toBeLessThanOrEqual(1)
  })

  it('no 30:2, pular batidas nao desalinha a posicao das ventilacoes', async () => {
    const tipos: TipoBatida[] = []
    const m = new Metronomo({ bpm: 120, modo302: true, aoBater: (tipo) => tipos.push(tipo) })
    await m.iniciar()
    await avancar(2)

    contexto.currentTime += 4 // 8 batidas puladas, dentro das 30 compressoes
    await vi.advanceTimersByTimeAsync(25)
    await avancar(14)
    m.parar()

    // A primeira ventilacao continua sendo a batida 31 DA GRADE (indice 30), que
    // a 120 bpm cai 15 s depois da primeira.
    const primeira = contexto.agendados[0]!
    const indiceDaVentilacao = tipos.indexOf('ventilacao')
    expect(indiceDaVentilacao).toBeGreaterThan(-1)
    const quando = contexto.agendados[indiceDaVentilacao]!
    expect((quando - primeira) / 0.5).toBeCloseTo(30, 6)
  })

  // ── O pulso visual acompanha o SOM ─────────────────────────────────────────

  it('avisa a UI no instante do som, nao no do agendamento', async () => {
    const instantes: number[] = []
    const m = new Metronomo({
      bpm: 120,
      modo302: false,
      aoBater: () => instantes.push(contexto.currentTime),
    })
    await m.iniciar()
    await avancar(3)
    m.parar()

    // Cada aviso sai junto do clique correspondente (25 ms e o passo do relogio
    // falso). Antes saia ate 100 ms ANTES: a tela adiantava o compasso.
    instantes.forEach((instante, i) => {
      expect(instante).toBeGreaterThanOrEqual(contexto.agendados[i]! - 1e-9)
      expect(instante - contexto.agendados[i]!).toBeLessThanOrEqual(0.026)
    })
  })

  // ── Audio interrompido: uma ligacao para o 192 faz exatamente isto ─────────

  it('avisa quando o sistema corta o audio, e quando devolve', async () => {
    const avisos: boolean[] = []
    const m = new Metronomo({ bpm: 110, modo302: false, aoMudarAudio: (i) => avisos.push(i) })
    await m.iniciar()
    await avancar(1)

    contexto.mudarEstado('interrupted')
    expect(m.audioInterrompido).toBe(true)

    expect(await m.retomarAudio()).toBe(true)
    expect(m.audioInterrompido).toBe(false)
    expect(avisos).toEqual([true, false])
  })

  it('sem gesto do usuario o resume e recusado, e o aviso continua', async () => {
    const avisos: boolean[] = []
    const m = new Metronomo({ bpm: 110, modo302: false, aoMudarAudio: (i) => avisos.push(i) })
    await m.iniciar()
    contexto.mudarEstado('suspended')
    contexto.aceitaResume = false

    expect(await m.retomarAudio()).toBe(false)
    expect(m.audioInterrompido).toBe(true)
    expect(avisos.at(-1)).toBe(true)
  })

  it('metronomo parado nao avisa de audio interrompido', async () => {
    const avisos: boolean[] = []
    const m = new Metronomo({ bpm: 110, modo302: false, aoMudarAudio: (i) => avisos.push(i) })
    await m.iniciar()
    m.parar()

    contexto.mudarEstado('suspended')

    expect(avisos).toEqual([])
    expect(m.audioInterrompido).toBe(false)
  })

  it('deriva acumulada fica abaixo de 1ms em 2 minutos', async () => {
    const m = new Metronomo({ bpm: 110, modo302: false })
    await m.iniciar()
    await avancar(CICLO_SEGUNDOS)
    m.parar()

    const intervalo = 60 / 110
    const primeira = contexto.agendados[0]!
    const ultima = contexto.agendados[contexto.agendados.length - 1]!
    const batidas = contexto.agendados.length - 1

    expect(Math.abs(ultima - (primeira + batidas * intervalo))).toBeLessThan(0.001)
  })

  it('marca 30 compressoes e 2 ventilacoes no modo 30:2', async () => {
    const tipos: TipoBatida[] = []
    const m = new Metronomo({
      bpm: 120,
      modo302: true,
      aoBater: (tipo) => tipos.push(tipo),
    })
    await m.iniciar()
    // 32 batidas do padrao a 120bpm = 16s. Damos folga.
    await avancar(16.5)
    m.parar()

    const padrao = tipos.slice(0, COMPRESSOES_POR_CICLO_302 + VENTILACOES_POR_CICLO_302)
    expect(padrao.filter((t) => t === 'compressao')).toHaveLength(COMPRESSOES_POR_CICLO_302)
    expect(padrao.filter((t) => t === 'ventilacao')).toHaveLength(VENTILACOES_POR_CICLO_302)

    // As ventilacoes vem DEPOIS das 30 compressoes, nunca intercaladas.
    expect(padrao.slice(0, 30).every((t) => t === 'compressao')).toBe(true)
    expect(padrao.slice(30).every((t) => t === 'ventilacao')).toBe(true)
  })

  it('conta compressoes, nao ventilacoes', async () => {
    const tipos: TipoBatida[] = []
    const m = new Metronomo({
      bpm: 120,
      modo302: true,
      aoBater: (tipo) => tipos.push(tipo),
    })
    await m.iniciar()
    await avancar(16.5)
    m.parar()

    // Ancorado no que foi de fato emitido, nao num numero fixo: quantas batidas
    // cabem na janela depende de arredondamento do relogio falso, e o que se
    // afirma aqui e a RELACAO — o contador ignora ventilacoes.
    const compressoesEmitidas = tipos.filter((t) => t === 'compressao').length
    expect(m.instantaneo().compressoes).toBe(compressoesEmitidas)
    expect(compressoesEmitidas).toBeLessThan(tipos.length)
  })

  it('fecha um ciclo a cada 2 minutos e avisa', async () => {
    const ciclosVistos: number[] = []
    const m = new Metronomo({
      bpm: 110,
      modo302: false,
      aoFecharCiclo: (c) => ciclosVistos.push(c),
    })
    await m.iniciar()
    await avancar(CICLO_SEGUNDOS + 1)
    m.parar()

    expect(ciclosVistos).toEqual([1])
    expect(m.instantaneo().ciclos).toBe(1)
  })

  it('modo continuo nunca marca ventilacao', async () => {
    const tipos: TipoBatida[] = []
    const m = new Metronomo({
      bpm: 120,
      modo302: false,
      aoBater: (tipo) => tipos.push(tipo),
    })
    await m.iniciar()
    await avancar(20)
    m.parar()

    expect(tipos.length).toBeGreaterThan(30)
    expect(tipos.every((t) => t === 'compressao')).toBe(true)
  })

  it('reiniciar zera os contadores', async () => {
    const m = new Metronomo({ bpm: 120, modo302: true })
    await m.iniciar()
    await avancar(20)
    m.reiniciar()

    expect(m.instantaneo()).toEqual({
      compressoes: 0,
      ciclos: 0,
      segundosNoCiclo: 0,
      emVentilacao: false,
    })
    expect(m.rodando).toBe(false)
  })

  it('atualizar bpm em execucao muda o compasso sem parar', async () => {
    const m = new Metronomo({ bpm: 100, modo302: false })
    await m.iniciar()
    await avancar(5)
    expect(m.rodando).toBe(true)

    m.atualizar({ bpm: 120 })
    const antes = contexto.agendados.length
    await avancar(5)
    m.parar()

    // A partir da proxima batida agendada, o intervalo e o novo.
    for (const intervalo of intervalosDesde(antes)) {
      expect(intervalo).toBeCloseTo(0.5, 6)
    }
  })

  it('iniciar duas vezes nao duplica o agendador', async () => {
    const m = new Metronomo({ bpm: 120, modo302: false })
    await m.iniciar()
    await m.iniciar()
    await avancar(5)
    m.parar()

    // A 120bpm em 5s: ~10 batidas. Um agendador duplicado daria ~20.
    expect(contexto.agendados.length).toBeLessThanOrEqual(12)
  })

  it('parar interrompe o agendamento', async () => {
    const m = new Metronomo({ bpm: 120, modo302: false })
    await m.iniciar()
    await avancar(5)
    m.parar()

    const depoisDeParar = contexto.agendados.length
    await avancar(5)
    expect(contexto.agendados.length).toBe(depoisDeParar)
  })
})

describe('faixa recomendada', () => {
  it('cobre a recomendacao de 100-120/min da AHA para adultos', () => {
    expect(BPM_MINIMO).toBe(100)
    expect(BPM_MAXIMO).toBe(120)
  })
})

describe('formatarTempo', () => {
  it.each([
    [0, '00:00'],
    [9, '00:09'],
    [60, '01:00'],
    [95, '01:35'],
    [120, '02:00'],
  ])('formata %i segundos como %s', (entrada, esperado) => {
    expect(formatarTempo(entrada)).toBe(esperado)
  })

  it('trata negativo como zero', () => {
    expect(formatarTempo(-5)).toBe('00:00')
  })
})
