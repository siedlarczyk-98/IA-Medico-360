const BASE  = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');
const TOKEN = import.meta.env.VITE_API_TOKEN ?? '';

function authHeaders(): HeadersInit {
  return {
    'Content-Type': 'application/json',
    ...(TOKEN ? { Authorization: `Bearer ${TOKEN}` } : {}),
  };
}

export interface AIModel {
  model_id: string;
  display_name: string;
  provider: string;
  available: boolean;
}

export async function fetchModels(): Promise<AIModel[]> {
  const res = await fetch(`${BASE}/api/v1/agregador/models`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`fetchModels error ${res.status}`);
  return res.json();
}

export type AgregadorStreamEvent =
  | { type: 'delta';    model_id: string; delta: string }
  | { type: 'complete'; model_id: string; response_time_ms: number; tokens_in?: number; tokens_out?: number }
  | { type: 'error';    model_id?: string; error?: string; message?: string };

export async function* streamAgregador(
  prompt: string,
  models: string[],
  signal?: AbortSignal,
): AsyncGenerator<AgregadorStreamEvent> {
  const res = await fetch(`${BASE}/api/v1/agregador/stream`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ prompt, models }),
    signal,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    console.error(`Agregador API ${res.status}:`, detail);
    throw new Error(`API error ${res.status}`);
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
      const line = rawLine.trimEnd(); // remove \r de line endings \r\n
      if (line.startsWith('event: ')) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const raw = line.slice(6).trim();
        if (raw === '[DONE]') return;
        try {
          const data = JSON.parse(raw);
          yield { type: currentEvent, ...data } as AgregadorStreamEvent;
        } catch { /* ignorar */ }
        currentEvent = '';
      }
    }
  }
}
