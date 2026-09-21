import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type Coordenada,
  type EstadoLocalizacao,
  solicitarLocalizacao,
} from '../lib/localizacao'

export type { Coordenada } from '../lib/localizacao'

/**
 * Praça da Sé, marco zero de São Paulo.
 *
 * Só é usado quando não há posição real — e nesse caso a interface diz
 * explicitamente que está mostrando outra região (`avisoDeLocalizacao`), não
 * busca enquanto ainda está tentando, e não mostra distâncias.
 */
export const CENTRO_PADRAO: Coordenada = { lat: -23.5505, lng: -46.6333 }

function geolocalizacao(): Geolocation | undefined {
  if (typeof navigator === 'undefined' || !('geolocation' in navigator)) return undefined
  return navigator.geolocation
}

/**
 * O estado inicial é derivado no primeiro render, não setado por efeito: se o
 * navegador não tem a API, isso já se sabe antes de qualquer efeito rodar.
 */
function estadoInicial(): EstadoLocalizacao {
  return geolocalizacao()
    ? { situacao: 'buscando' }
    : { situacao: 'indisponivel', motivo: 'sem-api' }
}

/**
 * Localização do usuário, pedida ao abrir o mapa. A lógica — duas tentativas,
 * teto de espera, o que conta como falha — está em `lib/localizacao.ts`.
 */
export function useLocalizacao() {
  const [estado, setEstado] = useState<EstadoLocalizacao>(estadoInicial)
  const cancelar = useRef<() => void>(() => {})

  const iniciar = useCallback(() => {
    cancelar.current()
    cancelar.current = solicitarLocalizacao(geolocalizacao(), setEstado)
  }, [])

  useEffect(() => {
    iniciar()
    return () => cancelar.current()
  }, [iniciar])

  /** Nova tentativa por ação do usuário — aí sim voltando a "buscando". */
  const solicitar = useCallback(() => {
    setEstado({ situacao: 'buscando' })
    iniciar()
  }, [iniciar])

  const posicao = estado.situacao === 'ok' ? estado.posicao : CENTRO_PADRAO
  return { estado, posicao, temPosicaoReal: estado.situacao === 'ok', solicitar }
}
