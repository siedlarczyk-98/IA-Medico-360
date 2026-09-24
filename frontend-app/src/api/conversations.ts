import { conferirSessao, getToken } from '../lib/auth';
import { erroDeResposta } from './erros';
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

/** Maior página que a API aceita (`page_size` tem `le=100` no backend). */
export const CONVERSAS_POR_PAGINA = 100;
/** Teto de segurança: 2000 conversas. Além disso a lateral precisa de busca, não de lista. */
const MAX_PAGINAS = 20;

/**
 * TODAS as conversas do médico, não só as 50 mais recentes.
 *
 * A API sempre paginou, mas aqui só se pedia a primeira página, com o tamanho
 * padrão: a 51ª conversa ficava inalcançável — sumia da lista e de dentro da
 * pasta onde estava. O médico mais assíduo era justamente quem perdia acesso ao
 * próprio histórico.
 *
 * Busca página a página e devolve a lista INTEIRA, de propósito: a lateral trata
 * o cache de `['conversations']` como uma lista única em meia dúzia de mutações
 * otimistas (mover, renomear, apagar), e as pastas contam as conversas a partir
 * dela. Uma consulta infinita exigiria reescrever tudo isso para ganhar pouco — um
 * resumo de conversa são ~200 bytes.
 */
export async function listConversations(): Promise<ConversationSummary[]> {
  const todas: ConversationSummary[] = [];
  const vistas = new Set<string>();

  for (let pagina = 1; pagina <= MAX_PAGINAS; pagina++) {
    const res = await fetch(
      `${BASE}/api/v1/conversations?page=${pagina}&page_size=${CONVERSAS_POR_PAGINA}`,
      { headers: authHeaders() },
    );
    conferirSessao(res);
    if (!res.ok) throw new Error('Erro ao carregar histórico');
    const lote: ConversationSummary[] = await res.json();

    // A ordem é por `updated_at`: uma conversa atualizada ENTRE duas páginas muda
    // de posição e pode vir repetida. Fica a primeira ocorrência.
    for (const conversa of lote) {
      if (!vistas.has(conversa.id)) {
        vistas.add(conversa.id);
        todas.push(conversa);
      }
    }
    if (lote.length < CONVERSAS_POR_PAGINA) break;
  }
  return todas;
}

export async function getConversation(id: string): Promise<ConversationDetail> {
  const res = await fetch(`${BASE}/api/v1/conversations/${id}`, { headers: authHeaders() });
  // O status segue no erro: é o controller quem trata o 401, porque só ele sabe
  // qual conversa devolver ao médico depois da reentrada.
  if (!res.ok) throw erroDeResposta(res.status, await res.text().catch(() => ''));
  return res.json();
}

/** Maior título que a API aceita (`ConversationRename.title`, `max_length=120`). */
export const MAX_TITULO_CONVERSA = 120;

/**
 * Renomeia a conversa. Não mexe na data dela: o histórico continua ordenado por
 * quando o médico conversou, não por quando renomeou (ver a rota no backend).
 */
export async function renameConversation(id: string, title: string): Promise<ConversationSummary> {
  const res = await fetch(`${BASE}/api/v1/conversations/${id}`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ title }),
  });
  conferirSessao(res);
  if (!res.ok) throw new Error('Erro ao renomear conversa');
  return res.json();
}

