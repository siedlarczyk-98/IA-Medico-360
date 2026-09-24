/**
 * Erro HTTP com a mensagem que o médico vai ler.
 *
 * Existe porque todo erro do orquestrador virava `new Error("API error 429: ...")`
 * e o chat mostrava sempre "Erro ao conectar com o servidor" — para cota
 * semanal esgotada, sessão expirada e queda de rede, a MESMA frase. O médico
 * beta que batia no limite achava que o produto tinha caído, e redigitava.
 */
export class ErroDeApi extends Error {
  readonly status: number;

  constructor(status: number, mensagem: string) {
    super(mensagem);
    this.name = 'ErroDeApi';
    this.status = status;
  }
}

/** Queda de rede, DNS, CORS: o `fetch` nem chegou a ter resposta. */
export const MENSAGEM_SEM_CONEXAO = 'Erro ao conectar com o servidor. Verifique sua conexão e tente de novo.';

// Aparece por um instante, enquanto `sessaoExpirou` leva o médico à reentrada —
// que é automática. "Entre novamente" pedia uma ação que não havia como fazer.
const MENSAGEM_SESSAO_EXPIRADA = 'Sua sessão expirou. Entrando de novo…';
const MENSAGEM_MUITAS_REQUISICOES = 'Muitas perguntas em pouco tempo. Aguarde um minuto e tente de novo.';
const MENSAGEM_SERVIDOR = 'O servidor não conseguiu responder agora. Tente novamente em instantes.';

/** `detail` do FastAPI, quando é texto. Erro de validação vem como lista — não serve de frase. */
function detalheLegivel(corpo: string): string | null {
  try {
    const json: unknown = JSON.parse(corpo);
    if (json && typeof json === 'object' && 'detail' in json) {
      const detail = (json as { detail: unknown }).detail;
      if (typeof detail === 'string' && detail.trim()) return detail;
    }
  } catch {
    // corpo não-JSON (HTML de proxy, texto puro): não é frase para o médico
  }
  return null;
}

/**
 * Traduz status + corpo na frase certa.
 *
 * O `detail` do backend tem prioridade quando existe: é ele que diz "limite
 * semanal atingido, reinicia em 7 dias", que nenhuma frase genérica substitui.
 */
export function erroDeResposta(status: number, corpo: string): ErroDeApi {
  const detail = detalheLegivel(corpo);
  if (status === 401) return new ErroDeApi(status, MENSAGEM_SESSAO_EXPIRADA);
  if (status === 429) return new ErroDeApi(status, detail ?? MENSAGEM_MUITAS_REQUISICOES);
  if (status >= 500) return new ErroDeApi(status, MENSAGEM_SERVIDOR);
  return new ErroDeApi(status, detail ?? MENSAGEM_SERVIDOR);
}

/**
 * Repetir a mesma pergunta pode dar certo? Sim para queda de rede e erro do
 * servidor. Não para sessão expirada (precisa entrar de novo) nem para cota
 * (precisa esperar): oferecer o botão ali só faria o médico bater na mesma parede.
 */
export function valeTentarDeNovo(err: unknown): boolean {
  if (!(err instanceof ErroDeApi)) return true;
  return err.status >= 500;
}

/** A frase para QUALQUER coisa que caia no `catch` do chat. */
export function mensagemDeErro(err: unknown): string {
  return err instanceof ErroDeApi ? err.message : MENSAGEM_SEM_CONEXAO;
}
