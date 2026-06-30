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

export function logout(): void {
  clearToken();
  window.location.href = '/login';
}
