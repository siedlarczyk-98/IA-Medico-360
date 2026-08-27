import { getToken } from '../lib/auth';
import type { Message } from './orquestrador';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

function authHeaders(): HeadersInit {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface ConversationSummary {
  id: string;
  title: string | null;
  feature: 'ORQUESTRADOR' | 'AGREGADOR';
  folder_id: string | null;
  updated_at: string;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  title: string | null;
  feature: 'ORQUESTRADOR' | 'AGREGADOR';
  /**
   * Pasta da conversa. Presente para que a interface avise o médico de que
   * respostas aqui podem trazer material de outras conversas da mesma pasta.
   */
  folder_id: string | null;
  folder_name: string | null;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

export async function listConversations(): Promise<ConversationSummary[]> {
  const res = await fetch(`${BASE}/api/v1/conversations`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Erro ao carregar histórico');
  return res.json();
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${BASE}/api/v1/conversations/${id}`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Conversa não encontrada');
  return res.json();
}
