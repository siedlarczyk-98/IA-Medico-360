/**
 * Chamadas do onboarding.
 *
 * Recebem `apiBase` e `token` por parâmetro em vez de lerem de um módulo: os
 * três apps divergem nas duas coisas — o `calculadoras-app` usa caminho
 * relativo em dev (proxy do Vite) e guarda o token em `calc360_token`, os
 * outros dois usam `medico360_token`. Um módulo compartilhado que assumisse uma
 * convenção só quebraria em algum deles.
 */

import type { DadosOnboarding, Especialidade, Perfil, RespostaOnboarding } from './tipos';

async function json<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    // O FastAPI devolve `detail` como string ou como lista de erros de
    // validação; sem este tratamento a tela mostraria "[object Object]".
    let detalhe = `Erro ${resp.status}`;
    try {
      const corpo = await resp.json();
      if (typeof corpo?.detail === 'string') detalhe = corpo.detail;
      else if (Array.isArray(corpo?.detail) && corpo.detail[0]?.msg) detalhe = corpo.detail[0].msg;
    } catch {
      /* resposta sem corpo JSON — fica a mensagem genérica */
    }
    throw new Error(detalhe);
  }
  return resp.json() as Promise<T>;
}

export function buscarPerfil(apiBase: string, token: string): Promise<Perfil> {
  return fetch(`${apiBase}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
    credentials: 'include',
  }).then(json<Perfil>);
}

/** Lista canônica servida pelo backend — não mais hardcoded em nenhum app. */
export function buscarEspecialidades(apiBase: string): Promise<Especialidade[]> {
  return fetch(`${apiBase}/api/v1/meta/especialidades`).then(json<Especialidade[]>);
}

export function enviarOnboarding(
  apiBase: string,
  token: string,
  dados: DadosOnboarding,
): Promise<RespostaOnboarding> {
  return fetch(`${apiBase}/api/v1/auth/onboarding`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    credentials: 'include',
    body: JSON.stringify(dados),
  }).then(json<RespostaOnboarding>);
}
