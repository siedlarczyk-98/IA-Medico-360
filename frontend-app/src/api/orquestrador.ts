const BASE  = import.meta.env.VITE_API_URL   ?? 'http://localhost:8000';
const TOKEN = import.meta.env.VITE_API_TOKEN ?? '';

function authHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
  };
}

export interface Message {
  role: 'user' | 'assistant';
  content: string;
  mode?: string;
  confidence?: number;
}

// Eventos tipados que o stream pode emitir
export type StreamEvent =
  | { type: 'start';         mode: string; triage_confidence: number }
  | { type: 'token';         text: string }
  | { type: 'clarification'; conversation_id: string; questions: string[] }
  | { type: 'done';          conversation_id: string; mode: string; model_used: string }
  | { type: 'error';         status?: string; message: string };

export interface StreamParams {
  prompt: string;
  conversation_id?: string;
  clarification_answers?: string;
  force?: boolean;
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
