import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

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
  phone_number: string | null;
  role: string;
  med_status: string | null;
  onboarding_complete: boolean;
}

export interface OnboardingData {
  name: string;
  phone_number: string;
  med_status: string;
  crm?: string;
  crm_state?: string;
  specialty?: string;
  enrollment_year?: number;
}

async function post<T>(path: string, body: unknown, auth = false): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (auth) {
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(`${BASE}/api/v1${path}`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Erro desconhecido');
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function patch<T>(path: string, body: unknown): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1${path}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Erro desconhecido');
  }
  return res.json() as Promise<T>;
}

async function del(path: string, body: unknown): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1${path}`, {
    method: 'DELETE',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Erro desconhecido');
  }
}

async function get<T>(path: string): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}/api/v1${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Erro desconhecido');
  }
  return res.json() as Promise<T>;
}

export function registerBeta(email: string): Promise<void> {
  return post<void>('/auth/register', { email });
}

export function requestOTP(email: string): Promise<void> {
  return post<void>('/auth/otp/request', { email });
}

export function verifyOTP(email: string, code: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/otp/verify', { email, code });
}

export function acceptInvite(token: string, email?: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/invite/accept', { token, email });
}

export function completeOnboarding(data: OnboardingData): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/onboarding', data, true);
}

export function getMe(): Promise<UserResponse> {
  return get<UserResponse>('/auth/me');
}

export function updateProfile(data: { name?: string; email?: string }): Promise<TokenResponse> {
  return patch<TokenResponse>('/auth/me', data);
}

export function deleteAccount(confirmName: string): Promise<void> {
  return del('/auth/me', { confirm_name: confirmName });
}

export function embedToken(email: string): Promise<TokenResponse> {
  return post<TokenResponse>('/auth/embed/token', { email });
}
