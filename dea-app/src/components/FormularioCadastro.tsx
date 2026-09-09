import { useEffect, useRef, useState } from 'react'

import { ErroApi, type Acesso, cadastrarLocal } from '../api/dea'
import type { Coordenada } from '../hooks/useLocalizacao'

type Props = {
  ponto: Coordenada
  aoCancelar: () => void
  aoCadastrar: () => void
}

const OPCOES_ACESSO: { valor: Acesso; rotulo: string; ajuda: string }[] = [
  {
    valor: 'publico_livre',
    rotulo: 'Livre',
    ajuda: 'Qualquer pessoa pega, sem pedir a ninguém',
  },
  {
    valor: 'balcao_recepcao',
    rotulo: 'Na recepção',
    ajuda: 'Precisa pedir a um funcionário',
  },
  {
    valor: 'restrito_funcionarios',
    rotulo: 'Restrito',
    ajuda: 'Só funcionários têm acesso',
  },
]

export function FormularioCadastro({ ponto, aoCancelar, aoCadastrar }: Props) {
  const [nome, setNome] = useState('')
  const [descricao, setDescricao] = useState('')
  const [endereco, setEndereco] = useState('')
  const [acesso, setAcesso] = useState<Acesso>('publico_livre')
  const [horario, setHorario] = useState('')
  const [aberto24h, setAberto24h] = useState(false)
  const [website, setWebsite] = useState('') // honeypot
  const [enviando, setEnviando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  // Marca quando o formulário abriu. O backend trata menos de 3s como bot —
  // ninguém digita nome e localização nesse tempo.
  //
  // `Date.now()` no efeito, não no render: sob StrictMode o componente renderiza
  // duas vezes, e ler o relógio durante o render é impuro.
  const abertoEm = useRef<number | null>(null)
  useEffect(() => {
    abertoEm.current = Date.now()
  }, [])

  async function enviar(evento: React.FormEvent) {
    evento.preventDefault()
    setErro(null)
    setEnviando(true)
    try {
      await cadastrarLocal({
        nome: nome.trim(),
        latitude: ponto.lat,
        longitude: ponto.lng,
        endereco: endereco.trim() || null,
        descricao_localizacao: descricao.trim() || null,
        acesso,
        horario_texto: horario.trim() || null,
        acesso_24h: aberto24h,
        website: website || undefined,
        segundos_de_preenchimento:
          abertoEm.current === null ? undefined : (Date.now() - abertoEm.current) / 1000,
      })
      aoCadastrar()
    } catch (e) {
      // A API escreve mensagens acionáveis nos 429 ("muitos cadastros nesta
      // região na última hora"), então repassá-las é melhor que um genérico.
      setErro(
        e instanceof ErroApi
          ? e.message
          : 'Não foi possível enviar. Verifique sua conexão e tente de novo.',
      )
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form className="formulario" onSubmit={enviar}>
      <p className="formulario__coordenada">
        Posição escolhida: {ponto.lat.toFixed(5)}, {ponto.lng.toFixed(5)}
        <br />
        <span className="dica">Arraste o pin no mapa para ajustar.</span>
      </p>

      <div className="campo">
        <label htmlFor="nome">Nome do local *</label>
        <input
          id="nome"
          type="text"
          required
          minLength={2}
          maxLength={160}
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Shopping, estação, academia..."
        />
      </div>

      <div className="campo">
        <label htmlFor="descricao">Onde exatamente está o DEA?</label>
        <textarea
          id="descricao"
          rows={2}
          maxLength={500}
          value={descricao}
          onChange={(e) => setDescricao(e.target.value)}
          placeholder="Térreo, parede ao lado do caixa 3"
        />
        {/* Este campo economiza mais segundos que a coordenada: quem chegou ao
            prédio precisa saber onde procurar dentro dele. */}
        <p className="dica">
          É o que mais ajuda quem chega correndo — mais que o endereço.
        </p>
      </div>

      <div className="campo">
        <label htmlFor="acesso">Como se pega o aparelho?</label>
        <div className="opcoes" id="acesso" role="radiogroup" aria-label="Tipo de acesso">
          {OPCOES_ACESSO.map((opcao) => (
            <button
              key={opcao.valor}
              type="button"
              role="radio"
              aria-checked={acesso === opcao.valor}
              className={acesso === opcao.valor ? 'opcao opcao--ativa' : 'opcao'}
              onClick={() => setAcesso(opcao.valor)}
            >
              {opcao.rotulo}
            </button>
          ))}
        </div>
        <p className="dica">{OPCOES_ACESSO.find((o) => o.valor === acesso)?.ajuda}</p>
      </div>

      <div className="campo campo--linha">
        <label htmlFor="aberto24h">Disponível 24 horas</label>
        <input
          id="aberto24h"
          type="checkbox"
          checked={aberto24h}
          onChange={(e) => setAberto24h(e.target.checked)}
        />
      </div>

      {!aberto24h && (
        <div className="campo">
          <label htmlFor="horario">Horário de funcionamento</label>
          <input
            id="horario"
            type="text"
            maxLength={200}
            value={horario}
            onChange={(e) => setHorario(e.target.value)}
            placeholder="Seg-Sáb 10h-22h, Dom 14h-20h"
          />
        </div>
      )}

      <div className="campo">
        <label htmlFor="endereco">Endereço (opcional)</label>
        <input
          id="endereco"
          type="text"
          maxLength={240}
          value={endereco}
          onChange={(e) => setEndereco(e.target.value)}
          placeholder="Av. Paulista, 900"
        />
      </div>

      {/* Honeypot: escondido por CSS, fora da ordem de tabulação e invisível ao
          leitor de tela. Só automação preenche. */}
      <div className="honeypot" aria-hidden="true">
        <label htmlFor="website">Não preencha este campo</label>
        <input
          id="website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
        />
      </div>

      {erro && (
        <p className="erro" role="alert">
          {erro}
        </p>
      )}

      <div className="controles">
        <button type="submit" className="botao botao--iniciar" disabled={enviando}>
          {enviando ? 'Enviando...' : 'Cadastrar DEA'}
        </button>
        <button
          type="button"
          className="botao botao--secundario"
          onClick={aoCancelar}
          disabled={enviando}
        >
          Cancelar
        </button>
      </div>
    </form>
  )
}
