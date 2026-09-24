import { getToken } from '../lib/auth';
import { erroDeResposta } from './erros';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export interface ExtractResult {
  file_id: string;
  file_name: string;
  file_type: string;
  /**
   * Aviso quando a extração não rendeu conteúdo útil — PDF digitalizado, por
   * exemplo. O upload não falha; o anexo é aceito e o médico decide. Mas sem
   * mostrar isto ele recebe uma resposta pobre sobre um exame que nunca chegou
   * ao modelo, e não tem como saber por quê.
   */
  warning?: string | null;
}

export const ACCEPTED_FILE_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  'image/jpeg',
  'image/png',
  'image/webp',
].join(',');

export async function extractFile(file: File): Promise<ExtractResult> {
  const token = getToken();
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${BASE}/api/v1/uploads/extract`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });

  // 401 com o status: é o composer quem trata, porque só ele tem o texto que o
  // médico estava escrevendo para devolver depois da reentrada.
  if (res.status === 401) throw erroDeResposta(401, '');
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(body?.detail ?? `Erro ${res.status} ao processar arquivo.`);
  }

  return res.json();
}
