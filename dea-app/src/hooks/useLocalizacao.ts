import { useCallback, useEffect, useState } from 'react'

export type Coordenada = { lat: number; lng: number }

/**
 * Praça da Sé, marco zero de São Paulo.
 *
 * Só é usado quando não há permissão de localização — e nesse caso a interface
 * diz explicitamente que está mostrando outra região, em vez de fingir que o
 * usuário está aqui.
 */
export const CENTRO_PADRAO: Coordenada = { lat: -23.5505, lng: -46.6333 }

type Estado =
  | { situacao: 'buscando' }
  | { situacao: 'ok'; posicao: Coordenada; precisaoM: number }
  | { situacao: 'negada' }
  | { situacao: 'indisponivel' }

/**
 * O estado inicial é derivado no primeiro render, não setado por efeito: se o
 * navegador não tem a API, isso já se sabe antes de qualquer efeito rodar.
 */
function estadoInicial(): Estado {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) {
    return { situacao: 'indisponivel' }
  }
  return { situacao: 'buscando' }
}

/**
 * Localização do usuário, pedida uma vez ao abrir o mapa.
 *
 * `enableHighAccuracy` liga o GPS: gasta bateria, mas a diferença entre 20 m e
 * 2 km decide se o "DEA mais próximo" é o certo. Vale o custo aqui.
 */
export function useLocalizacao() {
  const [estado, setEstado] = useState<Estado>(estadoInicial)

  const solicitar = useCallback(() => {
    // Sem `setEstado` síncrono aqui: a ausência da API já foi resolvida em
    // `estadoInicial()`, durante o render. Tudo abaixo roda em callback do
    // navegador, que é assíncrono por natureza.
    if (!('geolocation' in navigator)) return

    navigator.geolocation.getCurrentPosition(
      (pos) =>
        setEstado({
          situacao: 'ok',
          posicao: { lat: pos.coords.latitude, lng: pos.coords.longitude },
          precisaoM: pos.coords.accuracy,
        }),
      (erro) =>
        setEstado(
          erro.code === erro.PERMISSION_DENIED
            ? { situacao: 'negada' }
            : { situacao: 'indisponivel' },
        ),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 },
    )
  }, [])

  useEffect(solicitar, [solicitar])

  const posicao = estado.situacao === 'ok' ? estado.posicao : CENTRO_PADRAO
  return { estado, posicao, temPosicaoReal: estado.situacao === 'ok', solicitar }
}
