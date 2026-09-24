import { formularioAberto, guardarFormulariosAbertos } from '@shared/embed/formulario';
import { hospedadoNaWaid, reservarReentradaPelaWaid } from '@shared/embed/sessao';

const TOKEN_KEY = 'medico360_token';

// Este arquivo tinha também um `EMAIL_KEY` e um `tokenPertenceA(email)`, que
// registravam DE QUEM era o token guardado.
//
// Existiam porque a identidade vinha no `?email=` da URL e a sessão era
// reaproveitada entre carregamentos: num navegador compartilhado — estação de
// clínica, plantão — o segundo médico herdava o feed, os temas e os favoritos
// do primeiro até o token expirar. Era a única proteção do tipo entre os três
// apps, e os outros dois tinham o problema em aberto.
//
// Saíram porque o problema deixou de existir: com o handshake da Waid a
// autenticação acontece a CADA carregamento, e o `clearToken()` roda antes da
// troca. O token do médico anterior nunca sobrevive, então não é preciso
// guardar de quem ele era para descobrir. A proteção virou propriedade do
// desenho, e passou a valer para os três apps em vez de um.
//
// Se algum dia a sessão voltar a ser reaproveitada entre carregamentos, isto
// aqui precisa voltar — de preferência pelo `waid_uuid`, que é a chave estável,
// e não pelo e-mail.

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function isAuthenticated(): boolean {
  return getToken() !== null;
}

interface TokenPayload {
  sub: string;
  role: string;
  exp: number;
}

export function getTokenPayload(): TokenPayload | null {
  const token = getToken();
  if (!token) return null;
  try {
    const payload = token.split('.')[1];
    return JSON.parse(atob(payload)) as TokenPayload;
  } catch {
    return null;
  }
}

export function isTokenExpired(): boolean {
  const payload = getTokenPayload();
  if (!payload) return true;
  return Date.now() / 1000 > payload.exp;
}

const API_BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

/**
 * Encerra a sessão NO SERVIDOR. Nunca rejeita: sair não pode falhar.
 *
 * Limpar o `localStorage` não basta. A sessão também vive num cookie `HttpOnly`,
 * que o JavaScript não alcança, e o JWT seguia válido por até uma hora — em
 * estação compartilhada de hospital, o próximo usuário lia o histórico do
 * anterior. O servidor apaga o cookie e revoga o token (`token_version`).
 *
 * `keepalive` deixa o pedido terminar mesmo com a página indo embora; o teto de
 * 3 s impede que uma rede ruim prenda o médico na tela depois de clicar em Sair.
 */
export async function encerrarSessaoNoServidor(
  token: string | null,
  { revogar = true }: { revogar?: boolean } = {},
): Promise<void> {
  try {
    await fetch(`${API_BASE}/api/v1/auth/logout${revogar ? '' : '?revogar=false'}`, {
      method: 'POST',
      credentials: 'include',
      keepalive: true,
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      signal: AbortSignal.timeout(3000),
    });
  } catch {
    // Sem rede o token local já foi limpo; o do servidor expira sozinho.
  }
}

/**
 * Descarta a sessão que estava NESTE navegador, sem revogar as outras.
 *
 * Para a entrada do embed quando a Waid deveria ter dito quem é o médico e não
 * disse (timeout, troca indisponível). Seguir adiante com o token e o cookie que
 * já estavam aqui é herdar a sessão de quem usou a máquina antes — em estação
 * compartilhada, outro médico. Não vale para `sem_iframe`: ali é o app móvel,
 * aparelho pessoal, e a sessão do login por e-mail é a do próprio usuário.
 */
export function descartarSessaoDesteNavegador(): void {
  const token = getToken();
  clearToken();
  void encerrarSessaoNoServidor(token, { revogar: false });
}

let saindo = false;
let pedirLogin: (() => void) | null = null;

/**
 * O `App` diz como mostrar a tela de código. É uma FASE dele, e não uma rota —
 * este módulo não tem como chegar lá sozinho.
 */
export function aoPrecisarDeLogin(mostrar: (() => void) | null): void {
  pedirLogin = mostrar;
}

/**
 * A sessão acabou (token vencido ou recusado com 401): entra de novo.
 *
 * Aqui entrar de novo é RECARREGAR — o handshake com a Waid roda a cada
 * carregamento, e fora da Waid o recarregamento sem token cai na tela de
 * código. A URL fica como está, então um `/artigo/153` aberto volta aberto.
 *
 * Antes disto o 401 não levava a lugar nenhum: o modal do destaque mostrava
 * "Token expirado" cru, e o médico só saía dali fechando e reabrindo a seção.
 *
 * QUEM ESTAVA EDITANDO OS TEMAS NÃO PERDE A EDIÇÃO (item 68). O que estava
 * marcado é guardado (`shared/embed/formulario.ts`) e a URL passa a ser
 * `/preferencias`, que reabre a tela de temas depois do recarregamento. Sem
 * isto, a volta caía no feed e as marcações sumiam.
 *
 * TRAVA CONTRA LAÇO, dentro da Waid (`reservarReentradaPelaWaid`): se o token
 * que acabou de chegar também leva 401, não recarrega de novo — vai para a tela
 * de código. Antes a trava só limpava o token e parava ali: o app ficava na
 * mesma tela, sem sessão, com toda chamada recusada e nada respondendo por um
 * minuto.
 */
export function sessaoExpirou(): void {
  if (saindo) return;
  const dono = getTokenPayload()?.sub;
  clearToken();
  if (hospedadoNaWaid() && !reservarReentradaPelaWaid()) {
    if (pedirLogin) {
      pedirLogin();
      return;
    }
    // Sem o `App` montado não há fase para trocar; recarregar sem token é o que
    // leva à tela de código.
  }
  saindo = true;
  guardarFormulariosAbertos(dono);
  if (formularioAberto('temas') && window.location.pathname !== '/preferencias') {
    window.history.replaceState(null, '', '/preferencias');
  }
  window.location.reload();
}

export function logout(): void {
  const token = getToken();
  clearToken();
  void encerrarSessaoNoServidor(token).finally(() => {
    // A RAIZ, e não `/login`: este app não tem essa rota — a tela de código é
    // uma FASE, decidida pelo `App` quando não há sessão. Mandar para `/login`
    // caía no catch-all e trazia o médico de volta ao feed, agora deslogado.
    //
    // Ir para a raiz também limpa um `/artigo/153` que tenha sobrado na barra,
    // que depois de sair não leva a lugar nenhum.
    window.location.href = '/';
  });
}
