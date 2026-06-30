import { getToken } from '../lib/auth';

// Em dev (sem VITE_API_URL) usa caminho relativo → proxy Vite cuida do CORS.
// Em prod VITE_API_URL aponta para o domínio do backend.
const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';

export interface TokenResponse {
  access_token: string;
  token_type: string;
  onboarding_complete: boolean;
}

export interface UserResponse {
  id: string;
  email: string;
  name: string | null;
  crm: string | null;
  crm_state: string | null;
  role: string;
  onboarding_complete: boolean;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Erro desconhecido');
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function requestOTP(email: string): Promise<void> {
  return post<void>('/auth/otp/request', { email });
}

export function verifyOTP(email: string, code: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/otp/verify', { email, code });
}

export function embedToken(email: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/embed/token', { email });
}

export async function getMe(): Promise<UserResponse> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1/auth/me`, {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error('Unauthorized');
  return res.json() as Promise<UserResponse>;
}
