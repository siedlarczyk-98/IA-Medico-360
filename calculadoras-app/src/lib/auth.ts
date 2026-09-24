import { guardarFormulariosAbertos } from '@shared/embed/formulario';
import { reservarReentradaPelaWaid } from '@shared/embed/sessao';

const TOKEN_KEY = 'calc360_token';
const DESTINO_KEY = 'calc360_destino';

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

// Mesma regra de `api/auth.ts`: sem VITE_API_URL o caminho é relativo (proxy do Vite).
const API_BASE = import.meta.env.VITE_API_URL ? import.meta.env.VITE_API_URL.replace(/\/$/, '') : '';

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

/**
 * A sessão acabou (token vencido ou recusado com 401): entra de novo.
 *
 * Dentro da Waid, pelo handshake — silencioso, o médico só vê a tela de espera
 * por um instante. Fora dela, ou se a reentrada pela Waid acabou de ser
 * tentada (trava contra laço em `reservarReentradaPelaWaid`), pelo login.
 *
 * Antes disto o 401 não levava a lugar nenhum: a tela da calculadora lia só
 * `data`, e um token vencido virava "Calculadora não encontrada". As que já
 * estavam em cache seguiam abrindo, e o defeito parecia intermitente.
 *
 * Guarda onde o médico estava para devolvê-lo à mesma calculadora depois, e o
 * que ele tinha preenchido nela (`shared/embed/formulario.ts`) — antes, o
 * assistente de risco com quinze campos voltava vazio. Navegação completa (`location.replace`), e não do roteador, de propósito:
 * zera o cache do react-query, que ainda guardava o usuário da sessão morta.
 */
export function sessaoExpirou(): void {
  const { pathname, search } = window.location;
  if (saindo || pathname === '/login' || pathname === '/embed-auth') return;
  saindo = true;
  // ANTES de limpar o token: o dono do formulário guardado é o `sub` dele, e é
  // o que impede os dados do paciente de aparecerem para outro médico na volta.
  guardarFormulariosAbertos(getTokenPayload()?.sub);
  clearToken();
  try {
    sessionStorage.setItem(DESTINO_KEY, pathname + search);
  } catch {
    /* sem sessionStorage volta para a lista, que também serve */
  }
  window.location.replace(reservarReentradaPelaWaid() ? '/embed-auth' : '/login');
}

/** Chamado por quem faz `fetch` com o token: 401 é sessão que acabou. */
export function conferirSessao(res: Response): void {
  if (res.status === 401) sessaoExpirou();
}

/**
 * Para onde ir depois de entrar: a tela onde a sessão caiu, ou a lista.
 * Consome o valor — chamar em handler, não no corpo de um render.
 */
export function destinoAposEntrar(): string {
  try {
    const destino = sessionStorage.getItem(DESTINO_KEY);
    sessionStorage.removeItem(DESTINO_KEY);
    // Só caminho interno: `//outro.site` também começa com barra.
    if (destino && destino.startsWith('/') && !destino.startsWith('//')) return destino;
  } catch {
    /* segue para a lista */
  }
  return '/';
}

export function logout(): void {
  const token = getToken();
  clearToken();
  void encerrarSessaoNoServidor(token).finally(() => {
    window.location.href = '/login';
  });
}

/** O médico desta sessão, para restaurar só o formulário que era dele. */
export function donoDaSessao(): string | undefined {
  return getTokenPayload()?.sub;
}
