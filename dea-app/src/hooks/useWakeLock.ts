import { useCallback, useEffect, useRef } from 'react'

/**
 * Mantem a tela acesa enquanto o metronomo roda.
 *
 * Sem isso o celular apaga a tela em ~30s e a pessoa perde o contador de ciclos
 * no meio do atendimento. O som continua (o AudioContext nao depende da tela),
 * mas a informacao visual some.
 *
 * A Screen Wake Lock API nao existe em todo navegador (notavelmente, Safari so a
 * partir do 16.4) e falha silenciosamente quando nao ha gesto do usuario. Toda
 * chamada e best-effort: se nao der, o metronomo funciona igual, so a tela
 * apaga. Nao vale degradar nada por isso.
 */
export function useWakeLock() {
  const sentinelaRef = useRef<WakeLockSentinel | null>(null)

  const liberar = useCallback(() => {
    void sentinelaRef.current?.release().catch(() => {})
    sentinelaRef.current = null
  }, [])

  const solicitar = useCallback(async () => {
    if (!('wakeLock' in navigator)) return
    try {
      sentinelaRef.current = await navigator.wakeLock.request('screen')
    } catch {
      // Negado, sem suporte, ou aba em background. Segue sem lock.
    }
  }, [])

  // O lock e perdido quando a aba vai para background. Ao voltar, se ainda
  // estivermos com um lock ativo registrado, pedimos de novo — senao a tela
  // volta a apagar depois do primeiro alt-tab.
  useEffect(() => {
    function aoVoltar() {
      if (document.visibilityState === 'visible' && sentinelaRef.current !== null) {
        void solicitar()
      }
    }
    document.addEventListener('visibilitychange', aoVoltar)
    return () => document.removeEventListener('visibilitychange', aoVoltar)
  }, [solicitar])

  useEffect(() => liberar, [liberar])

  return { solicitar, liberar }
}
