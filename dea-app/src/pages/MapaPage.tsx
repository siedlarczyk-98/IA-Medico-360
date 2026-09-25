import { useCallback, useEffect, useRef, useState } from 'react'

import {
  ErroApi,
  type Local,
  ROTULO_ACESSO,
  buscarLocais,
  descreverConfianca,
  formatarDistancia,
  verificarDispositivo,
} from '../api/dea'
import { FormularioCadastro } from '../components/FormularioCadastro'
import { MapaDea, type MapaDeaControle } from '../components/MapaDea'
import { type Coordenada, useLocalizacao } from '../hooks/useLocalizacao'
import { avisoDeLocalizacao } from '../lib/localizacao'

const RAIO_KM = 5

type Modo = 'navegar' | 'escolhendo-ponto' | 'preenchendo'

export function MapaPage() {
  const { estado, posicao, temPosicaoReal, solicitar } = useLocalizacao()
  const [locais, setLocais] = useState<Local[]>([])
  const [carregando, setCarregando] = useState(true)
  const [erro, setErro] = useState<string | null>(null)
  const [selecionadoId, setSelecionadoId] = useState<string | null>(null)
  const [modo, setModo] = useState<Modo>('navegar')
  const [ponto, setPonto] = useState<Coordenada | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)
  // Mapa em tela cheia. No celular, fora dela, o mapa é prévia e não prende o
  // dedo — ver `interativo` abaixo e em MapaDea.
  const [ampliado, setAmpliado] = useState(false)
  const [toque] = useState(() => window.matchMedia?.('(pointer: coarse)').matches ?? false)
  const mapa = useRef<MapaDeaControle>(null)
  // Tocou em "minha localização" sem ter posição: pede de novo ao GPS e
  // centraliza quando ela chegar (efeito mais abaixo).
  const centralizarQuandoChegar = useRef(false)

  /**
   * Busca os locais em volta.
   *
   * Não seta `carregando` no início de propósito: o estado já nasce `true`, e
   * setá-lo aqui seria uma atualização síncrona disparada pelo efeito. Quem
   * recarrega por ação do usuário chama `recarregar`, abaixo.
   */
  const localizando = estado.situacao === 'buscando'

  const carregar = useCallback(
    async (sinal?: AbortSignal) => {
      // Enquanto a localização não se resolve, NÃO se busca: a lista sairia em
      // volta do centro de São Paulo e seria trocada segundos depois — ou pior,
      // ficaria na tela como se fosse a vizinhança do socorrista.
      if (localizando) return
      try {
        const resposta = await buscarLocais({
          latitude: posicao.lat,
          longitude: posicao.lng,
          raioKm: RAIO_KM,
          sinal,
        })
        // Só depois do `await`: nenhum estado é atualizado sincronamente na
        // passagem disparada pelo efeito.
        setErro(null)
        setLocais(resposta.locais)
      } catch (e) {
        if (e instanceof DOMException && e.name === 'AbortError') return
        setErro(
          e instanceof ErroApi
            ? e.message
            : 'Não foi possível carregar o mapa. Verifique sua conexão.',
        )
      } finally {
        // O oxlint marca esta linha como `set-state-in-effect`. É falso
        // positivo: o `finally` só roda depois do `await` acima, nunca no
        // caminho síncrono do efeito. A análise não consegue provar isso, e
        // reescrever o fluxo para silenciá-la deixaria o código pior — fica o
        // aviso, que não quebra o build (o lint sai com código 0).
        setCarregando(false)
      }
    },
    [posicao.lat, posicao.lng, localizando],
  )

  useEffect(() => {
    const controle = new AbortController()
    void carregar(controle.signal)
    return () => controle.abort()
  }, [carregar])

  /** Recarrega por ação do usuário — aí sim mostrando o estado de carga. */
  const recarregar = useCallback(async () => {
    setCarregando(true)
    await carregar()
  }, [carregar])

  async function confirmar(dispositivoId: string, resultado: 'encontrado' | 'nao_encontrado') {
    setAviso(null)
    try {
      const resposta = await verificarDispositivo(dispositivoId, { resultado })
      setAviso(resposta.mensagem)
      await recarregar()
    } catch (e) {
      setAviso(
        e instanceof ErroApi ? e.message : 'Não foi possível registrar sua verificação.',
      )
    }
  }

  // Com o mapa em tela cheia, a página por baixo não rola: sem isto o gesto
  // que escapa do mapa (na borda, no rodapé) rolava a lista escondida atrás.
  useEffect(() => {
    if (!ampliado) return
    const anterior = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = anterior
    }
  }, [ampliado])

  /**
   * Botão "minha localização". Com posição, volta a ela — o GPS NÃO é pedido de
   * novo: enquanto busca, `posicao` cai no centro padrão e o mapa pularia para a
   * Praça da Sé. Sem posição, é o "tentar de novo" do aviso, dentro do mapa.
   */
  function irParaMinhaLocalizacao() {
    if (temPosicaoReal) {
      mapa.current?.centralizar(posicao)
      return
    }
    centralizarQuandoChegar.current = true
    solicitar()
  }

  useEffect(() => {
    if (!temPosicaoReal || !centralizarQuandoChegar.current) return
    centralizarQuandoChegar.current = false
    mapa.current?.centralizar(posicao)
  }, [temPosicaoReal, posicao])

  const selecionado = locais.find((l) => l.id === selecionadoId) ?? null
  const avisoLocalizacao = avisoDeLocalizacao(estado)
  const rodapeAmpliado = ampliado && (modo !== 'navegar' || selecionado !== null)

  return (
    <div className="mapa-page">
      <div className="titulo">
        <h1>Mapa de DEA</h1>
      </div>

      {/* Texto, sem link `tel:`, igual ao do metrônomo. Na homologação dentro do
          app da Waid (2026-09-24) o link não abriu o discador — provavelmente a
          webview do app não encaminha `tel:` —, e um link que não responde em
          plena parada é pior que nenhum. Decisão do Ruben. */}
      <p className="aviso-emergencia" role="note">
        Em parada cardiorrespiratória: <strong>ligue 192 (SAMU)</strong> e comece as
        compressões. Os registros são colaborativos e podem estar desatualizados.
      </p>

      {/* Todo estado sem posição real tem aviso — não só a permissão negada.
          Timeout de GPS caía aqui calado, com a lista de outra cidade na tela. */}
      {avisoLocalizacao && (
        <p className="aviso-localizacao" role="alert">
          {avisoLocalizacao.texto}{' '}
          {avisoLocalizacao.podeTentarDeNovo && (
            <button type="button" className="link" onClick={solicitar}>
              Tentar de novo
            </button>
          )}
        </p>
      )}

      <div className={ampliado ? 'mapa-wrapper mapa-wrapper--cheio' : 'mapa-wrapper'}>
        <MapaDea
          ref={mapa}
          locais={modo === 'navegar' ? locais : []}
          // Ao escolher um local na lista, o mapa vai até ele — senão o cartão
          // selecionado e o marcador ficam falando de lugares diferentes.
          centro={
            selecionado && modo === 'navegar'
              ? { lat: selecionado.latitude, lng: selecionado.longitude }
              : posicao
          }
          posicaoUsuario={temPosicaoReal ? posicao : null}
          selecionadoId={selecionadoId}
          aoSelecionar={setSelecionadoId}
          aoEscolherPonto={modo === 'navegar' ? undefined : setPonto}
          pontoEscolhido={modo === 'navegar' ? null : ponto}
          // Interativo: ampliado, no computador (o mouse não disputa com a
          // rolagem) e ao escolher o ponto do cadastro, onde mexer no mapa é a
          // tarefa. No resto, no celular, é prévia.
          interativo={ampliado || !toque || modo !== 'navegar'}
          ampliado={ampliado}
        />
        {modo === 'escolhendo-ponto' && !ampliado && (
          <p className="instrucao-mapa">Toque no mapa onde fica o DEA</p>
        )}
        {/* No cadastro também: acertar o pin na porta certa pede mapa grande. */}
        {!ampliado && (
          <button type="button" className="mapa-botao mapa-ampliar" onClick={() => setAmpliado(true)}>
            Ampliar mapa
          </button>
        )}
        <button
          type="button"
          className={rodapeAmpliado ? 'mapa-botao mapa-localizar mapa-localizar--acima' : 'mapa-botao mapa-localizar'}
          aria-label="Ir para a minha localização"
          title="Minha localização"
          aria-busy={localizando}
          onClick={irParaMinhaLocalizacao}
        >
          <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true">
            <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
            <circle cx="12" cy="12" r="3" fill="currentColor" />
            <path d="M12 1v4M12 19v4M1 12h4M19 12h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
          </svg>
        </button>
        {ampliado && (
          <>
            {/* O X é a saída: dentro do app da Waid o botão voltar do Android não
                chega à página, então ele precisa ser grande e óbvio. */}
            <button type="button" className="mapa-botao mapa-fechar" aria-label="Fechar mapa" onClick={() => setAmpliado(false)}>
              ✕
            </button>
            {modo === 'navegar' && selecionado && (
              <div className="mapa-cheio-rodape">
                <b>{selecionado.nome}</b>
                <button type="button" className="mapa-botao" onClick={() => setAmpliado(false)}>
                  Ver detalhes
                </button>
              </div>
            )}
            {/* No cadastro, o rodapé diz o que fazer e já confirma — sem ele era
                preciso fechar o mapa para achar o "Confirmar posição". */}
            {modo !== 'navegar' && (
              <div className="mapa-cheio-rodape">
                <span className="mapa-cheio-rodape__texto">
                  {modo === 'escolhendo-ponto'
                    ? 'Toque no mapa onde fica o DEA'
                    : 'Arraste o pin até o local exato'}
                </span>
                <button
                  type="button"
                  className="mapa-botao mapa-botao--primario"
                  onClick={() => {
                    setAmpliado(false)
                    if (modo === 'escolhendo-ponto') setModo('preenchendo')
                  }}
                >
                  {modo === 'escolhendo-ponto' ? 'Confirmar posição' : 'Usar esta posição'}
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {modo === 'navegar' && (
        <>
          <button
            type="button"
            className="botao botao--iniciar botao--largo"
            onClick={() => {
              setModo('escolhendo-ponto')
              setPonto(posicao)
              setSelecionadoId(null)
            }}
          >
            Cadastrar um DEA que eu conheço
          </button>

          {aviso && (
            <p className="aviso-troca" role="status">
              {aviso}
            </p>
          )}

          {localizando && <p className="estado">Obtendo sua localização...</p>}
          {!localizando && carregando && (
            <p className="estado">Procurando DEAs por perto...</p>
          )}

          {erro && (
            <p className="erro" role="alert">
              {erro}{' '}
              <button type="button" className="link" onClick={() => void recarregar()}>
                Tentar de novo
              </button>
            </p>
          )}

          {!localizando && !carregando && !erro && locais.length === 0 && (
            <div className="em-breve">
              <p>
                Nenhum DEA cadastrado num raio de {RAIO_KM} km.
                <br />
                Seja a primeira pessoa a mapear um.
              </p>
            </div>
          )}

          <ul className="lista">
            {locais.map((local) => (
              <li
                key={local.id}
                className={
                  local.id === selecionadoId ? 'cartao cartao--ativo' : 'cartao'
                }
                onClick={() => setSelecionadoId(local.id)}
              >
                <div className="cartao__topo">
                  <h2>{local.nome}</h2>
                  {/* Sem posição real a distância é até a Praça da Sé — um
                      número que parece informação e não é. */}
                  {temPosicaoReal && (
                    <span className="cartao__distancia">
                      {formatarDistancia(local.distancia_km)}
                    </span>
                  )}
                </div>

                {local.endereco && <p className="cartao__endereco">{local.endereco}</p>}

                {local.dispositivos.map((dispositivo) => (
                  <div key={dispositivo.id} className="dispositivo">
                    {dispositivo.descricao_localizacao && (
                      <p className="dispositivo__local">
                        {dispositivo.descricao_localizacao}
                      </p>
                    )}

                    <div className="etiquetas">
                      {/* A confiança em texto, nunca só por cor: o mapa usa cor,
                          mas quem não distingue verde de cinza lê aqui. */}
                      <span className={`etiqueta etiqueta--${dispositivo.confianca}`}>
                        {descreverConfianca(dispositivo)}
                      </span>
                      {dispositivo.remocao_relatada && (
                        <span className="etiqueta etiqueta--contestado">
                          Remoção relatada — pode não estar mais aqui
                        </span>
                      )}
                      <span className="etiqueta">{ROTULO_ACESSO[dispositivo.acesso]}</span>
                      {local.acesso_24h && <span className="etiqueta">24 horas</span>}
                    </div>

                    {local.horario_texto && !local.acesso_24h && (
                      <p className="dica">{local.horario_texto}</p>
                    )}

                    {/* O motor de manutenção da base: sem um jeito barato de
                        dizer "não achei", o mapa envelhece sem ninguém saber. */}
                    {local.id === selecionadoId && (
                      <div className="verificacao">
                        <p className="verificacao__titulo">Você está neste local?</p>
                        <div className="controles">
                          <button
                            type="button"
                            className="botao botao--secundario"
                            onClick={(e) => {
                              e.stopPropagation()
                              void confirmar(dispositivo.id, 'encontrado')
                            }}
                          >
                            Encontrei
                          </button>
                          <button
                            type="button"
                            className="botao botao--secundario"
                            onClick={(e) => {
                              e.stopPropagation()
                              void confirmar(dispositivo.id, 'nao_encontrado')
                            }}
                          >
                            Não encontrei
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </li>
            ))}
          </ul>
        </>
      )}

      {modo === 'escolhendo-ponto' && ponto && (
        <div className="controles">
          <button
            type="button"
            className="botao botao--iniciar"
            onClick={() => setModo('preenchendo')}
          >
            Confirmar posição
          </button>
          <button
            type="button"
            className="botao botao--secundario"
            onClick={() => {
              setModo('navegar')
              setPonto(null)
            }}
          >
            Cancelar
          </button>
        </div>
      )}

      {modo === 'preenchendo' && ponto && (
        <FormularioCadastro
          ponto={ponto}
          aoCancelar={() => setModo('escolhendo-ponto')}
          aoCadastrar={() => {
            setModo('navegar')
            setPonto(null)
            setAviso(
              'Registro recebido e já visível no mapa como não confirmado. ' +
                'Ele passa a confirmado quando outra pessoa verificar no local.',
            )
            void recarregar()
          }}
        />
      )}

      {selecionado && modo === 'navegar' && (
        <a
          className="botao botao--iniciar botao--largo"
          href={`https://www.google.com/maps/dir/?api=1&destination=${selecionado.latitude},${selecionado.longitude}`}
          target="_blank"
          rel="noopener noreferrer"
        >
          Traçar rota até {selecionado.nome}
        </a>
      )}
    </div>
  )
}
