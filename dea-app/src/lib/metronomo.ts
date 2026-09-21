/**
 * Motor do metronomo de RCP.
 *
 * POR QUE NAO `setInterval`
 * -------------------------
 * `setInterval` e agendado pelo event loop do navegador, que atrasa sob carga e
 * e agressivamente estrangulado quando a aba perde o foco (a maioria dos
 * navegadores limita timers de aba oculta a 1 por segundo). Num metronomo de
 * compressao toracica isso e inaceitavel duas vezes: o erro ACUMULA — 8 ms de
 * atraso por batida viram quase uma batida inteira de defasagem em dois minutos
 * — e a tela do celular apagando nao pode parar o som.
 *
 * A solucao padrao e agendar no relogio do `AudioContext`, que roda no thread de
 * audio e nao sofre estrangulamento. Um timer barato so "acorda" a cada 25 ms
 * para enfileirar as batidas dos proximos 100 ms; quem toca no instante certo e
 * o proprio hardware de audio. E o padrao "lookahead scheduler" descrito por
 * Chris Wilson (A Tale of Two Clocks) e usado por praticamente todo metronomo
 * web serio.
 *
 * Faixa de 100-120/min: e a recomendacao de compressao toracica de adulto da AHA
 * (2020), repetida no ACLS. Abaixo de 100 a perfusao cai; acima de 120 a
 * profundidade da compressao cai porque nao ha tempo de retorno do torax.
 */

/** Compressoes por minuto recomendadas para adulto (AHA/ACLS). */
export const BPM_MINIMO = 100
export const BPM_MAXIMO = 120
export const BPM_PADRAO = 110

/**
 * Duracao do ciclo antes de trocar quem comprime, em segundos.
 *
 * A AHA recomenda revezar a cada 2 minutos (ou antes, se houver fadiga): a
 * qualidade da compressao cai mensuravelmente com o cansaco, e quem esta
 * comprimindo e o ultimo a perceber.
 */
export const CICLO_SEGUNDOS = 120

/** Compressoes por ventilacao no ciclo 30:2 (adulto, via aerea nao avancada). */
export const COMPRESSOES_POR_CICLO_302 = 30
export const VENTILACOES_POR_CICLO_302 = 2

/** Antecedencia com que as batidas sao enfileiradas no hardware de audio. */
const LOOKAHEAD_SEGUNDOS = 0.1
/** De quanto em quanto tempo o agendador acorda para enfileirar. */
const INTERVALO_AGENDADOR_MS = 25

export type TipoBatida = 'compressao' | 'ventilacao'

export type EstadoMetronomo = {
  /** Compressoes contadas desde o inicio (nao zera a cada ciclo). */
  compressoes: number
  /** Ciclos de 2 minutos completos. */
  ciclos: number
  /** Segundos decorridos dentro do ciclo atual. */
  segundosNoCiclo: number
  /** `true` enquanto as 2 ventilacoes do 30:2 estao sendo marcadas. */
  emVentilacao: boolean
}

type Opcoes = {
  bpm: number
  /** Quando `true`, marca a pausa 30:2. Quando `false`, e compressao continua. */
  modo302: boolean
  /** Chamado a cada batida agendada, para a UI piscar em sincronia. */
  aoBater?: (tipo: TipoBatida) => void
  /** Chamado quando um ciclo de 2 minutos fecha. */
  aoFecharCiclo?: (ciclo: number) => void
  /**
   * O sistema tirou o audio do app (ligacao, tela bloqueada, outra aba tomando o
   * foco de audio) — ou devolveu. `true` = o metronomo esta "rodando" em silencio.
   */
  aoMudarAudio?: (interrompido: boolean) => void
}

/**
 * Janela de agendamento com a aba OCULTA. O navegador estrangula timers de aba
 * em segundo plano para 1 disparo por segundo; com os 100 ms normais o som
 * falharia em nove de cada dez batidas. 1,5 s cobre o estrangulamento com folga.
 */
const LOOKAHEAD_OCULTO_SEGUNDOS = 1.5

/**
 * Quanto uma batida pode estar no passado e ainda ser tocada. `start()` num
 * instante passado toca AGORA, entao um atraso pequeno so desloca o clique alguns
 * milissegundos; um atraso grande viraria rajada (ver `agendar`).
 */
const TOLERANCIA_DE_ATRASO_SEGUNDOS = 0.025

function abaOculta(): boolean {
  return typeof document !== 'undefined' && document.hidden
}

/**
 * Sintetiza um clique curto. Preferido a um arquivo de audio: nao ha download,
 * nao ha latencia de decodificacao, e o envelope pode ser afiado o suficiente
 * para o inicio do som ser inequivoco (num metronomo, o ATAQUE e a informacao).
 */
function tocarClique(ctx: AudioContext, quando: number, tipo: TipoBatida): void {
  const osc = ctx.createOscillator()
  const ganho = ctx.createGain()

  // Ventilacao num tom mais grave e mais longo: precisa ser distinguivel sem
  // olhar para a tela, que e exatamente o momento em que a pessoa esta olhando
  // para o torax do paciente.
  const frequencia = tipo === 'ventilacao' ? 520 : 880
  const duracao = tipo === 'ventilacao' ? 0.18 : 0.05

  osc.frequency.value = frequencia
  osc.type = 'sine'

  // Ataque quase instantaneo e queda exponencial. Sem o ataque de 1 ms o
  // oscilador comeca com um "clique" de descontinuidade; sem a queda suave ele
  // termina com outro.
  ganho.gain.setValueAtTime(0, quando)
  ganho.gain.linearRampToValueAtTime(tipo === 'ventilacao' ? 0.5 : 0.8, quando + 0.001)
  ganho.gain.exponentialRampToValueAtTime(0.001, quando + duracao)

  osc.connect(ganho)
  ganho.connect(ctx.destination)
  osc.start(quando)
  osc.stop(quando + duracao + 0.02)
}

/**
 * Metronomo com agendamento por lookahead.
 *
 * Uso:
 *   const m = new Metronomo({ bpm: 110, modo302: true })
 *   await m.iniciar()   // precisa partir de um gesto do usuario (politica de autoplay)
 *   m.parar()
 */
export class Metronomo {
  private ctx: AudioContext | null = null
  private timer: ReturnType<typeof setInterval> | null = null
  /** Instante, no relogio do AudioContext, da proxima batida a enfileirar. */
  private proximaBatida = 0
  private opcoes: Opcoes
  private estado: EstadoMetronomo = {
    compressoes: 0,
    ciclos: 0,
    segundosNoCiclo: 0,
    emVentilacao: false,
  }
  /** Instante em que o ciclo de 2 minutos corrente comecou. */
  private inicioDoCiclo = 0
  /** Posicao dentro do padrao 30:2 — 0..29 comprime, 30..31 ventila. */
  private posicaoNoPadrao = 0
  /** Batidas agendadas cujo som ainda nao saiu (ver `registrarNaHora`). */
  private avisosPendentes = new Set<ReturnType<typeof setTimeout>>()

  constructor(opcoes: Opcoes) {
    this.opcoes = opcoes
  }

  get rodando(): boolean {
    return this.timer !== null
  }

  /** Ajusta parametros sem parar o metronomo (o usuario mexe no slider). */
  atualizar(parciais: Partial<Opcoes>): void {
    this.opcoes = { ...this.opcoes, ...parciais }
  }

  async iniciar(): Promise<void> {
    if (this.timer !== null) return

    if (this.ctx === null) {
      this.ctx = new AudioContext()
      // Uma ligacao para o 192 — que e exatamente o que se faz numa parada —
      // suspende o audio do navegador. O relogio do contexto para, nenhuma batida
      // nova e agendada, e a tela seguia mostrando "Parar" com o contador parado
      // e SEM SOM, sem dizer nada. Quem esta comprimindo precisa saber na hora.
      this.ctx.onstatechange = () => this.avisarEstadoDoAudio()
    }
    // Navegadores criam o contexto suspenso ate um gesto do usuario. `iniciar`
    // e sempre chamado de um clique, entao o resume aqui e o que destrava.
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume()
    }

    this.ultimoAvisoDeAudio = false
    const agora = this.ctx.currentTime
    // Meio quadro de folga: agendar exatamente em `currentTime` as vezes perde a
    // primeira batida, porque o instante ja passou quando o no e conectado.
    this.proximaBatida = agora + 0.05
    this.inicioDoCiclo = agora
    this.timer = setInterval(() => this.agendar(), INTERVALO_AGENDADOR_MS)
  }

  parar(): void {
    if (this.timer !== null) {
      clearInterval(this.timer)
      this.timer = null
    }
    this.avisosPendentes.forEach(clearTimeout)
    this.avisosPendentes.clear()
  }

  /** `true` quando o metronomo esta ligado mas o sistema cortou o audio. */
  get audioInterrompido(): boolean {
    return this.timer !== null && this.ctx !== null && this.ctx.state !== 'running'
  }

  /**
   * Tenta devolver o som. No iOS so funciona a partir de um gesto do usuario —
   * por isso a tela oferece um botao, alem da tentativa automatica ao voltar
   * para a aba. O compasso NAO precisa ser reancorado: com o contexto suspenso o
   * relogio dele congela, entao `proximaBatida` continua valendo ao retomar.
   */
  async retomarAudio(): Promise<boolean> {
    if (this.ctx === null) return false
    try {
      await this.ctx.resume()
    } catch {
      // sem gesto do usuario: a tela continua avisando
    }
    this.avisarEstadoDoAudio()
    return this.ctx.state === 'running'
  }

  /** Ultimo estado avisado: o evento do contexto e o `retomarAudio` se sobrepoem. */
  private ultimoAvisoDeAudio = false

  private avisarEstadoDoAudio(): void {
    if (this.timer === null) return
    const interrompido = this.audioInterrompido
    if (interrompido === this.ultimoAvisoDeAudio) return
    this.ultimoAvisoDeAudio = interrompido
    this.opcoes.aoMudarAudio?.(interrompido)
  }

  /**
   * Conta a batida e avisa a UI NO INSTANTE do som, nao no do agendamento. A
   * batida e enfileirada ate `lookahead` antes de tocar; fazer isto na hora de
   * enfileirar adiantava o pulso visual em ate 100 ms — e quem comprime olhando a
   * tela seguia um compasso diferente de quem comprime ouvindo.
   *
   * Contador e pulso saem do MESMO disparo de proposito: sao a mesma afirmacao
   * ("esta batida aconteceu") e nao podem discordar. Separados, um `parar()` no
   * meio da janela deixava a batida contada e nunca piscada.
   */
  private registrarNaHora(tipo: TipoBatida, quando: number, agora: number): void {
    const esperaMs = Math.max(0, (quando - agora) * 1000)
    const id = setTimeout(() => {
      this.avisosPendentes.delete(id)
      if (tipo === 'compressao') {
        this.estado.compressoes += 1
      }
      this.estado.emVentilacao = tipo === 'ventilacao'
      this.opcoes.aoBater?.(tipo)
    }, esperaMs)
    this.avisosPendentes.add(id)
  }

  /** Para e zera contadores. */
  reiniciar(): void {
    this.parar()
    this.estado = { compressoes: 0, ciclos: 0, segundosNoCiclo: 0, emVentilacao: false }
    this.posicaoNoPadrao = 0
  }

  instantaneo(): EstadoMetronomo {
    return { ...this.estado }
  }

  /** Libera o contexto de audio. Chamar no unmount. */
  async destruir(): Promise<void> {
    this.parar()
    if (this.ctx !== null) {
      await this.ctx.close()
      this.ctx = null
    }
  }

  /**
   * Enfileira todas as batidas que caem na janela de lookahead.
   *
   * O `while` (em vez de um `if`) e o que torna o metronomo robusto: se o timer
   * acordar atrasado, o laco percorre de uma vez todas as batidas devidas,
   * mantendo o compasso. O relogio de referencia e sempre `proximaBatida`, nunca
   * `currentTime` — e por isso que o erro nao acumula.
   *
   * BATIDA NO PASSADO NAO TOCA. `start()` num instante ja passado toca AGORA:
   * depois de a aba ficar suspensa por 3 s, as cinco batidas "recuperadas" saiam
   * todas juntas, numa rajada, e ainda inflavam o contador de compressoes com
   * compressoes que ninguem ouviu. Elas agora sao PULADAS — avancam a grade e a
   * posicao no 30:2, para o compasso voltar exatamente onde estaria, mas nao
   * tocam nem contam.
   */
  private agendar(): void {
    const ctx = this.ctx
    if (ctx === null) return

    const intervalo = 60 / this.opcoes.bpm
    const agora = ctx.currentTime
    const lookahead = abaOculta() ? LOOKAHEAD_OCULTO_SEGUNDOS : LOOKAHEAD_SEGUNDOS

    while (this.proximaBatida < agora + lookahead) {
      const tipo = this.tipoDaBatidaAtual()
      const perdida = this.proximaBatida < agora - TOLERANCIA_DE_ATRASO_SEGUNDOS

      if (!perdida) {
        tocarClique(ctx, this.proximaBatida, tipo)
        this.registrarNaHora(tipo, this.proximaBatida, agora)
      }

      this.avancarPadrao()
      this.proximaBatida += intervalo
    }

    this.estado.segundosNoCiclo = ctx.currentTime - this.inicioDoCiclo
    if (this.estado.segundosNoCiclo >= CICLO_SEGUNDOS) {
      this.estado.ciclos += 1
      this.inicioDoCiclo = ctx.currentTime
      this.estado.segundosNoCiclo = 0
      this.opcoes.aoFecharCiclo?.(this.estado.ciclos)
    }
  }

  private tipoDaBatidaAtual(): TipoBatida {
    if (!this.opcoes.modo302) return 'compressao'
    return this.posicaoNoPadrao < COMPRESSOES_POR_CICLO_302 ? 'compressao' : 'ventilacao'
  }

  private avancarPadrao(): void {
    if (!this.opcoes.modo302) return
    const total = COMPRESSOES_POR_CICLO_302 + VENTILACOES_POR_CICLO_302
    this.posicaoNoPadrao = (this.posicaoNoPadrao + 1) % total
  }
}

/** `95` → `"01:35"`. */
export function formatarTempo(segundos: number): string {
  const s = Math.max(0, Math.floor(segundos))
  const min = Math.floor(s / 60)
  const seg = s % 60
  return `${String(min).padStart(2, '0')}:${String(seg).padStart(2, '0')}`
}
