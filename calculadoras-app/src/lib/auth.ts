const TOKEN_KEY = 'calc360_token';

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

export function logout(): void {
  const token = getToken();
  clearToken();
  void encerrarSessaoNoServidor(token).finally(() => {
    window.location.href = '/login';
  });
}
