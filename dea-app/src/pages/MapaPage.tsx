import { useCallback, useEffect, useState } from 'react'

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
import { MapaDea } from '../components/MapaDea'
import { type Coordenada, useLocalizacao } from '../hooks/useLocalizacao'

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

  /**
   * Busca os locais em volta.
   *
   * Não seta `carregando` no início de propósito: o estado já nasce `true`, e
   * setá-lo aqui seria uma atualização síncrona disparada pelo efeito. Quem
   * recarrega por ação do usuário chama `recarregar`, abaixo.
   */
  const carregar = useCallback(
    async (sinal?: AbortSignal) => {
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
    [posicao.lat, posicao.lng],
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

  const selecionado = locais.find((l) => l.id === selecionadoId) ?? null

  return (
    <div className="mapa-page">
      <div className="titulo">
        <h1>Mapa de DEA</h1>
      </div>

      <p className="aviso-emergencia" role="note">
        Em parada cardiorrespiratória: <strong>ligue 192 (SAMU)</strong> e comece as
        compressões. Os registros são colaborativos e podem estar desatualizados.
      </p>

      {estado.situacao === 'negada' && (
        <p className="aviso-localizacao">
          Sem acesso à sua localização — mostrando o centro de São Paulo.{' '}
          <button type="button" className="link" onClick={solicitar}>
            Tentar de novo
          </button>
        </p>
      )}

      <div className="mapa-wrapper">
        <MapaDea
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
        />
        {modo === 'escolhendo-ponto' && (
          <p className="instrucao-mapa">Toque no mapa onde fica o DEA</p>
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

          {carregando && <p className="estado">Procurando DEAs por perto...</p>}

          {erro && (
            <p className="erro" role="alert">
              {erro}{' '}
              <button type="button" className="link" onClick={() => void recarregar()}>
                Tentar de novo
              </button>
            </p>
          )}

          {!carregando && !erro && locais.length === 0 && (
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
                  <span className="cartao__distancia">
                    {formatarDistancia(local.distancia_km)}
                  </span>
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
