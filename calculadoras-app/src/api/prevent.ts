import { getToken } from '../lib/auth';

const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';

export interface PreventCalculateRequest {
  sexo: 'M' | 'F';
  idade: number;
  ct_mgdl: number;
  hdl_mgdl: number;
  sbp_mmhg: number;
  bmi: number;
  egfr: number;
  diabetes: boolean;
  fumante: boolean;
  antihtn_use: boolean;
  statin_use: boolean;
}

/** Por que um conjunto de desfechos não foi calculado, vindo do backend. */
export interface PreventAviso {
  codigo: string;
  mensagem: string;
  desfechos: string[];
}

export interface PreventCalculateResponse {
  cvd_10a: number | null;
  ascvd_10a: number | null;
  chd_10a: number | null;
  stroke_10a: number | null;
  hf_10a: number | null;
  cvd_30a: number | null;
  ascvd_30a: number | null;
  chd_30a: number | null;
  stroke_30a: number | null;
  hf_30a: number | null;
  avisos: PreventAviso[];
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Escore PREVENT (AHA, Khan et al. 2024) — endpoint dedicado, sem persistir execução/audit log. */
export async function calculatePrevent(body: PreventCalculateRequest): Promise<PreventCalculateResponse> {
  const res = await fetch(`${BASE}/api/v1/prevent/calculate`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Erro desconhecido');
  }
  return res.json() as Promise<PreventCalculateResponse>;
}
