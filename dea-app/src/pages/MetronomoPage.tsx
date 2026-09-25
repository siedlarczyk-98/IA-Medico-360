import { useCallback, useEffect, useRef, useState } from 'react'

import { useWakeLock } from '../hooks/useWakeLock'
import {
  BPM_MAXIMO,
  BPM_MINIMO,
  BPM_PADRAO,
  CICLO_SEGUNDOS,
  Metronomo,
  formatarTempo,
  type EstadoMetronomo,
} from '../lib/metronomo'

const ESTADO_ZERADO: EstadoMetronomo = {
  compressoes: 0,
  ciclos: 0,
  segundosNoCiclo: 0,
  emVentilacao: false,
}

/**
 * O metrônomo marca sempre o 30:2 — o toggle que permitia desligá-lo saiu da
 * tela. O motor continua aceitando `modo302: false` (compressão contínua, que é
 * o ritmo correto com via aérea avançada) e os testes cobrem os dois modos; o
 * que se decidiu é que a escolha não cabe a quem está com as mãos no tórax.
 * Para reexpor, basta voltar isto a um `useState` e devolver o checkbox.
 */
const MODO_302 = true

export function MetronomoPage() {
  const [bpm, setBpm] = useState(BPM_PADRAO)
  const [rodando, setRodando] = useState(false)
  const [estado, setEstado] = useState<EstadoMetronomo>(ESTADO_ZERADO)
  const [avisoTroca, setAvisoTroca] = useState(false)
  // O sistema cortou o audio com o metronomo ligado (ligacao, tela bloqueada).
  const [semSom, setSemSom] = useState(false)

  const metronomoRef = useRef<Metronomo | null>(null)
  const { solicitar: pedirWakeLock, liberar: liberarWakeLock } = useWakeLock()

  // Sem pulso visual por batida. O círculo crescia a cada compressão, depois
  // virou um anel que acendia e apagava — e nos dois casos, no Android dentro da
  // Waid, a tela "tremia" (homologação, 2026-09-25). Piscar ~2x por segundo é
  // exatamente o que incomoda. O ritmo é do SOM; a tela mostra a FASE, com cor
  // fixa que só muda quando a fase muda (ver `classeDaFase`).

  const aoFecharCiclo = useCallback(() => {
    setAvisoTroca(true)
    setTimeout(() => setAvisoTroca(false), 8000)
  }, [])

  /**
   * Cria o metronomo sob demanda, nunca durante o render.
   *
   * Instanciar direto no corpo do componente parece inofensivo, mas o
   * `Metronomo` carrega um `AudioContext`: sob StrictMode o React renderiza duas
   * vezes e o primeiro objeto seria descartado sem `destruir()`, vazando um
   * contexto de audio que o navegador limita a poucas dezenas por aba.
   */
  const obterMetronomo = useCallback((): Metronomo => {
    if (metronomoRef.current === null) {
      metronomoRef.current = new Metronomo({
        bpm,
        modo302: MODO_302,
        aoFecharCiclo,
        aoMudarAudio: setSemSom,
      })
    }
    return metronomoRef.current
  }, [bpm, aoFecharCiclo])

  // Ao voltar para o app (fim da ligacao, tela desbloqueada), tenta devolver o
  // som sozinho. No iOS isso so funciona com gesto do usuario — por isso o botao
  // "Retomar som" no aviso continua sendo o caminho garantido.
  useEffect(() => {
    const aoVoltar = () => {
      if (!document.hidden) void metronomoRef.current?.retomarAudio()
    }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => document.removeEventListener('visibilitychange', aoVoltar)
  }, [])

  // Os callbacks capturam estado; reinjeta-los a cada mudanca mantem o motor
  // falando com a versao atual sem recriar o metronomo (o que zeraria o compasso
  // no meio do atendimento). So atualiza se ja existir: criar aqui ligaria o
  // AudioContext antes de qualquer gesto do usuario, e o navegador o bloquearia.
  useEffect(() => {
    metronomoRef.current?.atualizar({ bpm, modo302: MODO_302, aoFecharCiclo })
  }, [bpm, aoFecharCiclo])

  // Espelha o estado do motor na UI. 100ms e suficiente para o cronometro e bem
  // mais barato que redesenhar a cada batida.
  useEffect(() => {
    if (!rodando) return
    const id = setInterval(() => {
      const atual = metronomoRef.current?.instantaneo()
      if (atual) setEstado(atual)
    }, 100)
    return () => clearInterval(id)
  }, [rodando])

  // Só no unmount. Lê o ref dentro do cleanup (não no corpo do efeito) para
  // pegar a instância que existir naquele momento — o metrônomo pode ter sido
  // criado depois deste efeito rodar, no primeiro clique em "Iniciar".
  useEffect(() => {
    return () => {
      void metronomoRef.current?.destruir()
      metronomoRef.current = null
    }
  }, [])

  async function alternar() {
    const metronomo = obterMetronomo()

    if (metronomo.rodando) {
      metronomo.parar()
      liberarWakeLock()
      setRodando(false)
      return
    }
    await metronomo.iniciar()
    void pedirWakeLock()
    setRodando(true)
  }

  function reiniciar() {
    metronomoRef.current?.reiniciar()
    liberarWakeLock()
    setRodando(false)
    setEstado(ESTADO_ZERADO)
    setAvisoTroca(false)
  }

  const restanteNoCiclo = Math.max(0, CICLO_SEGUNDOS - estado.segundosNoCiclo)
  const progresso = Math.min(100, (estado.segundosNoCiclo / CICLO_SEGUNDOS) * 100)

  return (
    <div className="metronomo">
      <div className="titulo">
        <h1>Metrônomo de RCP</h1>
      </div>

      <p className="aviso-emergencia" role="note">
        Em parada cardiorrespiratória: <strong>ligue 192 (SAMU)</strong> e comece as
        compressões. Este metrônomo é apoio de ritmo, não substitui treinamento.
      </p>

      <div
        className={
          !rodando ? 'pulso' : estado.emVentilacao ? 'pulso pulso--ventilacao' : 'pulso pulso--compressao'
        }
        aria-hidden="true"
      >
        <span className="pulso__bpm">{bpm}</span>
        <span className="pulso__unidade">/min</span>
      </div>

      {/* Uma ligacao para o 192 suspende o audio do navegador. Sem este aviso a
          tela seguia mostrando "Parar", com o contador parado e em silencio. */}
      {rodando && semSom && (
        <p className="erro" role="alert">
          O som foi interrompido (ligação ou tela bloqueada).{' '}
          <button
            type="button"
            className="link"
            onClick={() => void metronomoRef.current?.retomarAudio()}
          >
            Retomar som
          </button>
        </p>
      )}

      {/* aria-live separado do pulso visual: leitor de tela nao deve anunciar
          cada batida, so a mudanca de fase. */}
      <p className="fase" aria-live="polite">
        {!rodando
          ? 'Parado'
          : estado.emVentilacao
            ? 'Ventilação — 2 insuflações'
            : 'Compressão'}
      </p>

      <div className="controles">
        <button
          type="button"
          className={rodando ? 'botao botao--parar' : 'botao botao--iniciar'}
          onClick={() => void alternar()}
        >
          {rodando ? 'Parar' : 'Iniciar'}
        </button>
        <button type="button" className="botao botao--secundario" onClick={reiniciar}>
          Zerar
        </button>
      </div>

      <div className="campo">
        <label htmlFor="bpm">
          Ritmo: <strong>{bpm}</strong> compressões por minuto
        </label>
        <input
          id="bpm"
          type="range"
          min={BPM_MINIMO}
          max={BPM_MAXIMO}
          step={1}
          value={bpm}
          onChange={(e) => setBpm(Number(e.target.value))}
        />
        <p className="dica">
          A AHA recomenda de {BPM_MINIMO} a {BPM_MAXIMO} por minuto para adultos.
        </p>
      </div>

      <div className="painel">
        <div className="painel__item">
          <span className="painel__rotulo">Compressões</span>
          <span className="painel__valor">{estado.compressoes}</span>
        </div>
        <div className="painel__item">
          <span className="painel__rotulo">Ciclos de 2 min</span>
          <span className="painel__valor">{estado.ciclos}</span>
        </div>
        <div className="painel__item">
          <span className="painel__rotulo">Próxima troca</span>
          <span className="painel__valor">{formatarTempo(restanteNoCiclo)}</span>
        </div>
      </div>

      <div
        className="progresso"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={CICLO_SEGUNDOS}
        aria-valuenow={Math.floor(estado.segundosNoCiclo)}
        aria-label="Tempo no ciclo atual"
      >
        <div className="progresso__barra" style={{ width: `${progresso}%` }} />
      </div>

      {avisoTroca && (
        <p className="aviso-troca" role="alert">
          2 minutos completos — <strong>troque quem está comprimindo</strong>.
        </p>
      )}
    </div>
  )
}
