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

export function logout(): void {
  clearToken();
  window.location.href = '/login';
}
