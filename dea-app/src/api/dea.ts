const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export type Acesso = 'publico_livre' | 'balcao_recepcao' | 'restrito_funcionarios'
export type Confianca = 'alta' | 'media' | 'baixa' | 'contestado'
export type StatusDispositivo =
  | 'pendente'
  | 'ativo'
  | 'nao_encontrado'
  | 'removido'
  | 'spam'

export type Dispositivo = {
  id: string
  descricao_localizacao: string | null
  acesso: Acesso
  foto_url: string | null
  status: StatusDispositivo
  /** Rótulo derivado do histórico — nunca um número. Ver `confianca.py`. */
  confianca: Confianca
  confirmacoes: number
  contestacoes: number
  dias_desde_ultima_verificacao: number | null
}

export type Local = {
  id: string
  nome: string
  endereco: string | null
  cidade: string | null
  uf: string | null
  latitude: number
  longitude: number
  horario_texto: string | null
  acesso_24h: boolean
  distancia_km: number
  dispositivos: Dispositivo[]
}

export type BuscaResposta = {
  locais: Local[]
  total: number
  raio_km: number
  aviso: string
}

export type CadastroPayload = {
  nome: string
  latitude: number
  longitude: number
  endereco?: string | null
  cidade?: string | null
  uf?: string | null
  descricao_localizacao?: string | null
  acesso: Acesso
  horario_texto?: string | null
  acesso_24h: boolean
  /** Honeypot: fica escondido por CSS. Humano não vê, bot preenche. */
  website?: string
  /** Quanto tempo o formulário ficou aberto — menos de 3s o backend trata como bot. */
  segundos_de_preenchimento?: number
}

export type CadastroResposta = {
  local_id: string
  dispositivo_id: string
  status: StatusDispositivo
  mensagem: string
}

export type ResultadoVerificacao = 'encontrado' | 'nao_encontrado' | 'removido'

export type VerificacaoResposta = {
  dispositivo_id: string
  status: StatusDispositivo
  confianca: Confianca
  confirmacoes: number
  contestacoes: number
  mensagem: string
}

/**
 * Erro da API com a mensagem que o backend escreveu.
 *
 * As mensagens de 429 do módulo são acionáveis ("muitos cadastros nesta região
 * na última hora"), então repassá-las é melhor que um "erro" genérico.
 */
export class ErroApi extends Error {
  // Campo declarado e atribuído no corpo, em vez de parâmetro-propriedade: o
  // projeto compila com `erasableSyntaxOnly`, que proíbe sintaxe de TS sem
  // equivalente direto em JS.
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ErroApi'
    this.status = status
  }
}

async function tratar<T>(resposta: Response): Promise<T> {
  if (resposta.ok) return resposta.json() as Promise<T>

  let mensagem = `Falha na requisição (${resposta.status}).`
  try {
    const corpo = await resposta.json()
    if (typeof corpo?.detail === 'string') mensagem = corpo.detail
  } catch {
    // Resposta sem corpo JSON (502 de proxy, por exemplo). Fica a mensagem padrão.
  }
  throw new ErroApi(mensagem, resposta.status)
}

export async function buscarLocais(params: {
  latitude: number
  longitude: number
  raioKm?: number
  limite?: number
  sinal?: AbortSignal
}): Promise<BuscaResposta> {
  const query = new URLSearchParams({
    latitude: String(params.latitude),
    longitude: String(params.longitude),
  })
  if (params.raioKm !== undefined) query.set('raio_km', String(params.raioKm))
  if (params.limite !== undefined) query.set('limite', String(params.limite))

  const resposta = await fetch(`${BASE}/api/v1/dea/locais?${query}`, {
    signal: params.sinal,
  })
  return tratar<BuscaResposta>(resposta)
}

export async function cadastrarLocal(dados: CadastroPayload): Promise<CadastroResposta> {
  const resposta = await fetch(`${BASE}/api/v1/dea/locais`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(dados),
  })
  return tratar<CadastroResposta>(resposta)
}

export async function verificarDispositivo(
  dispositivoId: string,
  dados: { resultado: ResultadoVerificacao; observacao?: string; website?: string },
): Promise<VerificacaoResposta> {
  const resposta = await fetch(
    `${BASE}/api/v1/dea/dispositivos/${dispositivoId}/verificacoes`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    },
  )
  return tratar<VerificacaoResposta>(resposta)
}

// ── Apresentação ─────────────────────────────────────────────────────────

export const ROTULO_ACESSO: Record<Acesso, string> = {
  publico_livre: 'Acesso livre',
  balcao_recepcao: 'Pedir na recepção',
  restrito_funcionarios: 'Só funcionários',
}

/**
 * Como a confiança é dita ao usuário.
 *
 * A regra que governa o módulo inteiro: nunca afirmamos "há um DEA aqui".
 * Dizemos o que se sabe e há quanto tempo — a responsabilidade fica no dado, e
 * quem decide correr até lá decide sabendo.
 */
export function descreverConfianca(d: Dispositivo): string {
  const dias = d.dias_desde_ultima_verificacao

  if (d.confianca === 'contestado') {
    return d.contestacoes === 1
      ? 'Alguém não encontrou este DEA'
      : `${d.contestacoes} pessoas não encontraram este DEA`
  }
  if (d.confirmacoes === 0) {
    return 'Ainda não confirmado por ninguém'
  }

  const confirmacoes =
    d.confirmacoes === 1 ? 'Confirmado por 1 pessoa' : `Confirmado por ${d.confirmacoes} pessoas`

  if (dias === null) return confirmacoes
  if (dias === 0) return `${confirmacoes} · verificado hoje`
  if (dias === 1) return `${confirmacoes} · verificado ontem`
  if (dias < 60) return `${confirmacoes} · há ${dias} dias`

  const meses = Math.round(dias / 30)
  if (meses < 24) return `${confirmacoes} · há ${meses} meses`
  return `${confirmacoes} · há mais de 2 anos`
}

export function formatarDistancia(km: number): string {
  if (km < 1) return `${Math.round(km * 1000)} m`
  return `${km.toFixed(1).replace('.', ',')} km`
}
