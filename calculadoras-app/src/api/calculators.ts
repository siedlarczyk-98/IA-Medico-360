import { getToken } from '../lib/auth';

const BASE = import.meta.env.VITE_API_URL
  ? import.meta.env.VITE_API_URL.replace(/\/$/, '')
  : '';

export interface CalculatorField {
  key: string;
  label: string;
  field_type: 'number' | 'integer' | 'boolean' | 'select' | 'multiselect' | 'text';
  unit: string | null;
  required: boolean;
  min_value: number | null;
  max_value: number | null;
  options: Array<{ value: string; label: string }> | null;
  display_order: number;
}

export interface CalculatorListItem {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  specialty_slug: string;
}

export interface CalculatorDetail {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  engine_type: string;
  specialty_slug: string;
  fields: CalculatorField[];
}

export interface RiscoCvResult {
  categoria: 'BAIXO' | 'INTERMEDIARIO' | 'ALTO' | 'MUITO_ALTO' | 'EXTREMO';
  prevent: {
    ascvd_10a?: number;
    cvd_10a?: number;
    hf_10a?: number;
    ascvd_30a?: number;
    cvd_30a?: number;
  };
  passo_determinante: number | null;
  fatores_agravantes: string[];
  meta_ldl_recomendada: string;
}

export interface ExecuteResponse {
  id: string;
  version_id: string;
  inputs: Record<string, unknown>;
  result: Record<string, unknown>;
  interpretation: string | null;
  createdat: string;
}

export interface ExtractResponse {
  suggested_inputs: Record<string, unknown>;
  fields_extracted: string[];
  interaction_id: string | null;
}

export class ValidationError extends Error {
  fieldErrors: Record<string, string>;
  constructor(fieldErrors: Record<string, string>) {
    super('Erro de validação');
    this.fieldErrors = fieldErrors;
  }
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    credentials: 'include',
    headers: authHeaders(),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Erro desconhecido');
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}/api/v1${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });

  if (res.status === 422) {
    const data = await res.json().catch(() => ({ detail: [] }));
    const fieldErrors: Record<string, string> = {};
    if (Array.isArray(data.detail)) {
      for (const e of data.detail) {
        const key = e.loc?.[e.loc.length - 1] as string | undefined;
        if (key) fieldErrors[key] = e.msg as string;
      }
    }
    throw new ValidationError(fieldErrors);
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(typeof err.detail === 'string' ? err.detail : 'Erro desconhecido');
  }
  return res.json() as Promise<T>;
}

export function listCalculators(specialty?: string): Promise<CalculatorListItem[]> {
  const qs = specialty ? `?specialty=${encodeURIComponent(specialty)}` : '';
  return get<CalculatorListItem[]>(`/calculators${qs}`);
}

export function getCalculator(slug: string): Promise<CalculatorDetail> {
  return get<CalculatorDetail>(`/calculators/${slug}`);
}

export function executeCalculator(slug: string, inputs: Record<string, unknown>): Promise<ExecuteResponse> {
  return post<ExecuteResponse>(`/calculators/${slug}/execute`, { inputs });
}

export function extractFields(slug: string, text: string): Promise<ExtractResponse> {
  return post<ExtractResponse>(`/calculators/${slug}/extract`, { text });
}
