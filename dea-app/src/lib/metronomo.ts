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
    }
    // Navegadores criam o contexto suspenso ate um gesto do usuario. `iniciar`
    // e sempre chamado de um clique, entao o resume aqui e o que destrava.
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume()
    }

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
   * O `while` (em vez de um `if`) e o que torna o metronomo robusto: se o
   * navegador estrangulou o timer e nos acordamos 400 ms atrasados, este laco
   * enfileira de uma vez todas as batidas perdidas, mantendo o compasso. O
   * relogio de referencia e sempre `proximaBatida`, nunca `currentTime` — e por
   * isso que o erro nao acumula.
   */
  private agendar(): void {
    const ctx = this.ctx
    if (ctx === null) return

    const intervalo = 60 / this.opcoes.bpm

    while (this.proximaBatida < ctx.currentTime + LOOKAHEAD_SEGUNDOS) {
      const tipo = this.tipoDaBatidaAtual()
      tocarClique(ctx, this.proximaBatida, tipo)
      this.opcoes.aoBater?.(tipo)

      if (tipo === 'compressao') {
        this.estado.compressoes += 1
      }
      this.estado.emVentilacao = tipo === 'ventilacao'

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
