import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

function authHeaders(): HeadersInit {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface PubmedValidation {
  cited_verified: Array<{ title: string; pmid: string | null; verified: boolean }>;
  newer_guidelines: Array<{ pmid: string; article_title: string; abstract_snippet: string }>;
}

export interface Message {
  /**
   * Identidade estável da mensagem enquanto ela está sendo transmitida.
   * Existe para que os handlers de streaming localizem a mensagem por id e não
   * por índice: o índice é resolvido de forma assíncrona pelo React e produzia
   * mensagens duplicadas/congeladas. Ausente em mensagens vindas do histórico,
   * que nunca são atualizadas em vôo.
   */
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  mode?: string;
  confidence?: number;
  citations?: string[];
  pubmed_validation?: PubmedValidation;
  attachmentName?: string;
}

// Eventos tipados que o stream pode emitir
export type StreamEvent =
  | { type: 'start';         mode: string; triage_confidence: number }
  | { type: 'token';         text: string }
  | { type: 'cache_hit';     response_text: string; conversation_id: string; mode: string; model_used: string }
  | { type: 'clarification'; conversation_id: string; questions: string[] }
  | { type: 'done';          conversation_id: string; mode: string; model_used: string; citations?: string[] }
  | { type: 'error';         status?: string; message: string };

export interface StreamParams {
  prompt: string;
  conversation_id?: string;
  clarification_answers?: string;
  force?: boolean;
  effort?: 'rápido' | 'detalhado';
  mode?: string;
  history?: { role: 'user' | 'assistant'; content: string }[];
  folder_id?: string;
  file_id?: string;
}

export async function queryOrquestrador(params: StreamParams): Promise<{ response: string; mode: string; conversation_id: string }> {
  const res = await fetch(`${BASE}/api/v1/orquestrador/query`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      prompt: params.prompt,
      ...(params.conversation_id       ? { conversation_id: params.conversation_id }           : {}),
      ...(params.clarification_answers ? { clarification_answers: params.clarification_answers } : {}),
      ...(params.force                 ? { force: params.force }                               : {}),
      effort: params.effort ?? 'detalhado',
      ...(params.mode                  ? { mode: params.mode }                                 : {}),
      history: params.history ?? [],
      ...(params.folder_id             ? { folder_id: params.folder_id }                       : {}),
      ...(params.file_id               ? { file_id: params.file_id }                           : {}),
    }),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  const data = await res.json();
  return {
    response: data.response ?? data.response_text ?? JSON.stringify(data),
    mode: data.mode ?? 'PHARMA_CHECK',
    conversation_id: data.conversation_id ?? '',
  };
}

export async function* streamQuery(
  params: StreamParams,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const res = await fetch(`${BASE}/api/v1/orquestrador/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      prompt: params.prompt,
      ...(params.conversation_id     ? { conversation_id: params.conversation_id }         : {}),
      ...(params.clarification_answers ? { clarification_answers: params.clarification_answers } : {}),
      ...(params.force               ? { force: params.force }                             : {}),
      effort: params.effort ?? 'detalhado',
      ...(params.mode                ? { mode: params.mode }                               : {}),
      history: params.history ?? [],
      ...(params.folder_id           ? { folder_id: params.folder_id }                     : {}),
      ...(params.file_id             ? { file_id: params.file_id }                         : {}),
    }),
    signal,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    console.error(`API ${res.status}:`, detail);
    throw new Error(`API error ${res.status}: ${detail}`);
  }
  if (!res.body) throw new Error('No response body');

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') return;
        try {
          const data = JSON.parse(raw);
          yield { type: currentEvent, ...data } as StreamEvent;
        } catch {
          // ignorar linha malformada
        }
        currentEvent = '';
      }
    }
  }
}
