import { reservarReentradaPelaWaid } from '@shared/embed/sessao';

const TOKEN_KEY = 'medico360_token';
const RETOMADA_KEY = 'medico360_retomada';

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

export function logout(): void {
  const token = getToken();
  clearToken();
  void encerrarSessaoNoServidor(token).finally(() => {
    window.location.href = '/login';
  });
}

/** O que o médico estava fazendo quando a sessão caiu, para devolver depois de entrar. */
export interface Retomada {
  /** Pergunta que não chegou ao servidor: volta para o campo, não é reenviada sozinha. */
  pergunta?: string;
  conversaId?: string;
}

let saindo = false;
let donoDaSessao: string | null = null;

/**
 * A sessão acabou (401): entra de novo.
 *
 * Dentro da Waid, pelo handshake — silencioso, o médico só vê a tela de espera
 * por um instante. Fora dela, ou se a reentrada pela Waid acabou de ser tentada
 * (trava contra laço em `reservarReentradaPelaWaid`), pelo login.
 *
 * Antes disto o 401 no chat era beco sem saída: virava o balão "Sua sessão
 * expirou. Entre novamente" sem botão nem redirecionamento. E o gatilho é comum:
 * "Sair" em QUALQUER aparelho revoga todos (`token_version`), então sair nas
 * calculadoras ou no computador deixava o chat do celular com um token ainda
 * dentro do prazo, recusado em toda chamada, por até uma hora.
 *
 * O token é LIMPO antes de sair, e não é detalhe: fora do iframe, a
 * `EmbedAuthPage` devolve para "/" quem tem token não vencido quando a Waid não
 * responde. Com o token revogado ainda aqui, isso giraria entre as duas telas.
 *
 * Navegação completa (`location.replace`), e não do roteador: zera o cache do
 * react-query, que guardava as conversas da sessão morta.
 *
 * Pode ser chamada mais de uma vez no mesmo instante (o envio e a lista levam
 * 401 juntos): só a primeira navega, mas todas acrescentam à retomada.
 */
export function sessaoExpirou(retomar?: Retomada): void {
  if (!saindo) donoDaSessao = getTokenPayload()?.sub ?? null;
  if (retomar && donoDaSessao) guardarRetomada(donoDaSessao, retomar);
  const { pathname } = window.location;
  if (saindo || pathname === '/login' || pathname === '/embed-auth') return;
  saindo = true;
  clearToken();
  window.location.replace(reservarReentradaPelaWaid() ? '/embed-auth' : '/login');
}

/** Para quem faz `fetch` com o token e não tem o que retomar: 401 é sessão que acabou. */
export function conferirSessao(res: Response): void {
  if (res.status === 401) sessaoExpirou();
}

function guardarRetomada(dono: string, retomar: Retomada): void {
  try {
    const anterior = JSON.parse(sessionStorage.getItem(RETOMADA_KEY) ?? 'null') as
      (Retomada & { dono?: string }) | null;
    const base = anterior?.dono === dono ? anterior : {};
    const junto = { ...base, dono };
    if (retomar.pergunta?.trim()) junto.pergunta = retomar.pergunta;
    if (retomar.conversaId) junto.conversaId = retomar.conversaId;
    sessionStorage.setItem(RETOMADA_KEY, JSON.stringify(junto));
  } catch {
    /* sem sessionStorage a reentrada funciona igual; só não devolve o que havia */
  }
}

/**
 * A retomada guardada, se for DESTE médico. Consome o valor — chamar em efeito
 * ou handler, nunca no corpo de um render.
 *
 * A conferência do dono é o que impede a pergunta de um médico aparecer no campo
 * de outro: a `sessionStorage` é da aba, e numa estação compartilhada quem entra
 * pelo login depois da queda pode ser outra pessoa.
 */
export function consumirRetomada(): Retomada | null {
  try {
    const bruto = sessionStorage.getItem(RETOMADA_KEY);
    sessionStorage.removeItem(RETOMADA_KEY);
    if (!bruto) return null;
    const { dono, pergunta, conversaId } = JSON.parse(bruto) as Retomada & { dono?: string };
    if (!dono || dono !== getTokenPayload()?.sub) return null;
    return {
      ...(typeof pergunta === 'string' && pergunta ? { pergunta } : {}),
      ...(typeof conversaId === 'string' && conversaId ? { conversaId } : {}),
    };
  } catch {
    return null;
  }
}
