import L from 'leaflet'
import { useEffect, useRef } from 'react'

import type { Local } from '../api/dea'
import type { Coordenada } from '../hooks/useLocalizacao'

/**
 * Leaflet + OpenStreetMap: sem chave de API, sem billing, sem cota.
 *
 * Num app público e anônimo, uma chave do Google Maps no bundle é uma conta que
 * cresce com o tráfego de terceiros. A atribuição do OSM é obrigatória pela
 * licença e está no `attribution` abaixo — não remover.
 */

const OSM_URL = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const OSM_ATRIBUICAO =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'

/** Cores dos tokens do produto — repetidas aqui porque vão dentro do SVG. */
const VERDE = '#00d17d'
const PETROL = '#014751'
const CINZA = '#9aa6ab'
const VERMELHO = '#c8434b'

/**
 * Ícone universal de DEA: coração com raio. É o que está na sinalização real,
 * então o socorrista reconhece correndo — um pin genérico não comunica nada.
 *
 * A cor carrega a confiança: verde confirmado, cinza não confirmado, vermelho
 * contestado. Mas a cor nunca é o único sinal — o cartão da lista diz em texto.
 */
function iconeDea(cor: string, selecionado: boolean): L.DivIcon {
  const tamanho = selecionado ? 44 : 34
  return L.divIcon({
    className: 'marcador-dea',
    iconSize: [tamanho, tamanho],
    iconAnchor: [tamanho / 2, tamanho / 2],
    html: `
      <svg viewBox="0 0 48 48" width="${tamanho}" height="${tamanho}" aria-hidden="true">
        <rect x="2" y="2" width="44" height="44" rx="9" fill="${cor}"
              stroke="${selecionado ? PETROL : '#ffffff'}" stroke-width="3"/>
        <g transform="translate(9 11) scale(0.62)">
          <path d="M23.6 0c-3.4 0-6.3 2.7-7.6 5.6C14.7 2.7 11.8 0 8.4 0 3.8 0 0 3.8 0 8.4c0 9.4 9.5 11.9 16 21.2 6.1-9.2 16-12.1 16-21.2C32 3.8 28.2 0 23.6 0z" fill="#ffffff"/>
          <path d="M21 2.8 11 16.4h5l-2 7.3 7.8-10.4h-4.9z" fill="${cor}"/>
        </g>
      </svg>`,
  })
}

const ICONE_USUARIO = L.divIcon({
  className: 'marcador-usuario',
  iconSize: [22, 22],
  iconAnchor: [11, 11],
  html: `
    <svg viewBox="0 0 22 22" width="22" height="22" aria-hidden="true">
      <circle cx="11" cy="11" r="10" fill="${PETROL}" opacity="0.2"/>
      <circle cx="11" cy="11" r="5" fill="${PETROL}" stroke="#ffffff" stroke-width="2"/>
    </svg>`,
})

function corDoLocal(local: Local): string {
  const dispositivos = local.dispositivos
  if (dispositivos.some((d) => d.confianca === 'contestado')) return VERMELHO
  if (dispositivos.some((d) => d.confianca === 'alta' || d.confianca === 'media')) return VERDE
  return CINZA
}

type Props = {
  locais: Local[]
  centro: Coordenada
  posicaoUsuario: Coordenada | null
  selecionadoId: string | null
  /** Quando definido, o clique no mapa escolhe a posição em vez de navegar. */
  aoEscolherPonto?: (ponto: Coordenada) => void
  pontoEscolhido?: Coordenada | null
  aoSelecionar: (id: string) => void
}

export function MapaDea({
  locais,
  centro,
  posicaoUsuario,
  selecionadoId,
  aoEscolherPonto,
  pontoEscolhido,
  aoSelecionar,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapaRef = useRef<L.Map | null>(null)
  const marcadoresRef = useRef<Map<string, L.Marker>>(new Map())
  const marcadorUsuarioRef = useRef<L.Marker | null>(null)
  const marcadorEscolhaRef = useRef<L.Marker | null>(null)

  // Callbacks em ref: o mapa é criado uma vez só, e sem isso os handlers
  // capturariam a primeira versão das funções para sempre.
  const aoSelecionarRef = useRef(aoSelecionar)
  aoSelecionarRef.current = aoSelecionar
  const aoEscolherPontoRef = useRef(aoEscolherPonto)
  aoEscolherPontoRef.current = aoEscolherPonto

  useEffect(() => {
    if (containerRef.current === null || mapaRef.current !== null) return

    const mapa = L.map(containerRef.current, {
      center: [centro.lat, centro.lng],
      zoom: 15,
      zoomControl: true,
      // O mapa vive dentro de uma página que rola no celular; sem isto, tentar
      // rolar a página com o dedo sobre o mapa dá zoom sem querer.
      scrollWheelZoom: false,
    })
    L.tileLayer(OSM_URL, { attribution: OSM_ATRIBUICAO, maxZoom: 19 }).addTo(mapa)
    mapa.on('click', (e: L.LeafletMouseEvent) => {
      aoEscolherPontoRef.current?.({ lat: e.latlng.lat, lng: e.latlng.lng })
    })

    mapaRef.current = mapa
    // Copiado para variável local: o cleanup não deve ler `.current`, que pode
    // ter mudado até ele rodar.
    const marcadores = marcadoresRef.current
    return () => {
      mapa.remove()
      mapaRef.current = null
      marcadores.clear()
      marcadorUsuarioRef.current = null
      marcadorEscolhaRef.current = null
    }
    // Só na montagem: `centro` aqui é a posição inicial, e recriar o mapa a cada
    // mudança dela perderia o zoom e o estado de navegação do usuário.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    mapaRef.current?.panTo([centro.lat, centro.lng])
  }, [centro.lat, centro.lng])

  useEffect(() => {
    const mapa = mapaRef.current
    if (mapa === null) return
    const existentes = marcadoresRef.current

    for (const [id, marcador] of existentes) {
      if (!locais.some((l) => l.id === id)) {
        marcador.remove()
        existentes.delete(id)
      }
    }

    for (const local of locais) {
      const selecionado = local.id === selecionadoId
      const icone = iconeDea(corDoLocal(local), selecionado)
      const existente = existentes.get(local.id)

      if (existente) {
        existente.setIcon(icone)
        existente.setZIndexOffset(selecionado ? 1000 : 0)
        continue
      }
      const marcador = L.marker([local.latitude, local.longitude], {
        icon: icone,
        title: local.nome,
        zIndexOffset: selecionado ? 1000 : 0,
      })
        .addTo(mapa)
        .on('click', () => aoSelecionarRef.current(local.id))
      existentes.set(local.id, marcador)
    }
  }, [locais, selecionadoId])

  useEffect(() => {
    const mapa = mapaRef.current
    if (mapa === null) return

    if (posicaoUsuario === null) {
      marcadorUsuarioRef.current?.remove()
      marcadorUsuarioRef.current = null
      return
    }
    if (marcadorUsuarioRef.current === null) {
      marcadorUsuarioRef.current = L.marker([posicaoUsuario.lat, posicaoUsuario.lng], {
        icon: ICONE_USUARIO,
        title: 'Você está aqui',
        interactive: false,
      }).addTo(mapa)
    } else {
      marcadorUsuarioRef.current.setLatLng([posicaoUsuario.lat, posicaoUsuario.lng])
    }
  }, [posicaoUsuario])

  // Pin arrastável do cadastro: é ele que define a coordenada gravada, e não o
  // endereço digitado — quem está no local sabe melhor que qualquer geocoder.
  useEffect(() => {
    const mapa = mapaRef.current
    if (mapa === null) return

    if (!pontoEscolhido) {
      marcadorEscolhaRef.current?.remove()
      marcadorEscolhaRef.current = null
      return
    }
    if (marcadorEscolhaRef.current === null) {
      const marcador = L.marker([pontoEscolhido.lat, pontoEscolhido.lng], {
        icon: iconeDea(PETROL, true),
        draggable: true,
        title: 'Arraste até o local exato do DEA',
      }).addTo(mapa)
      marcador.on('dragend', () => {
        const p = marcador.getLatLng()
        aoEscolherPontoRef.current?.({ lat: p.lat, lng: p.lng })
      })
      marcadorEscolhaRef.current = marcador
    } else {
      marcadorEscolhaRef.current.setLatLng([pontoEscolhido.lat, pontoEscolhido.lng])
    }
  }, [pontoEscolhido])

  return <div ref={containerRef} className="mapa" />
}
