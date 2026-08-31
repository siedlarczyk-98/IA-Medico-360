const TOKEN_KEY = 'medico360_token';

// De quem é o token guardado. O JWT carrega `sub` (id) e `role`, não o e-mail,
// então sem este registro não há como saber se o token em localStorage pertence
// à pessoa que o LMS está identificando agora na URL.
const EMAIL_KEY = 'medico360_noticias_email';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string, email?: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  if (email) localStorage.setItem(EMAIL_KEY, email.trim().toLowerCase());
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(EMAIL_KEY);
}

/**
 * O token guardado é de outra pessoa?
 *
 * Importa porque o feed é PERSONALIZADO. Num navegador compartilhado — uma
 * estação de clínica, um plantão — o segundo usuário a abrir o LMS herdaria a
 * sessão do primeiro e veria o feed dele, incluindo favoritos e temas, até o
 * token expirar. Enquanto o conteúdo era o mesmo para todos, isso não aparecia.
 */
export function tokenEhDeOutroEmail(email: string): boolean {
  const guardado = localStorage.getItem(EMAIL_KEY);
  return guardado !== null && guardado !== email.trim().toLowerCase();
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

export function logout(): void {
  clearToken();
  window.location.href = '/login';
}
