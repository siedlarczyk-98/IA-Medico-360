/**
 * Cliente da API de notícias.
 *
 * Todas as chamadas vão autenticadas. A versão anterior deste app identificava
 * o aluno por `?email=` na query string — aceitável quando ele só listava posts
 * públicos do WordPress, inviável agora que o feed é personalizado: um
 * identificador forjável significaria ler e alterar os temas de outra pessoa.
 */
import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

export interface TemaCasado {
  slug: string;
  nome_pt: string;
}

export interface Tema {
  id: string;
  slug: string;
  nome_pt: string;
}

export interface Highlight {
  id: number;
  journal_slug: string;
  rewritten_title: string | null;
  /** Texto puro das primeiras linhas, para o card. O corpo só vem em /articles/{id}. */
  resumo: string | null;
  source_url: string | null;
  published_date: string | null;
  visible_at: string | null;
  /** Temas do usuário que casaram — o "por que estou vendo isto?" do card. */
  temas: TemaCasado[];
  /**
   * Item que entrou só para a tela não ficar vazia, vindo de temas adjacentes
   * à especialidade. Precisa ser exibido COMO TAL: é a diferença entre o
   * usuário confiar e não confiar no filtro.
   */
  preenchimento: boolean;
}

/** `sem_conteudo` = não publicaram nada. `sem_match` = os temas estão estreitos. */
export type MotivoVazio = 'sem_conteudo' | 'sem_match';

export interface Feed {
  itens: Highlight[];
  motivo_vazio: MotivoVazio | null;
}

export interface ArticleDetail {
  id: number;
  journal_slug: string;
  rewritten_title: string | null;
  rewritten_body: string | null;
  source_url: string | null;
  doi: string | null;
  authors: string | null;
  published_date: string | null;
  visible_at: string | null;
}

export interface MeusTemas {
  ja_escolheu: boolean;
  selecionados: Tema[];
  sugeridos: Tema[];
  disponiveis: Tema[];
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string> | undefined),
  };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}/api/v1${path}`, { ...init, headers });
  if (!res.ok) {
    const detalhe = await res.json().catch(() => null);
    throw new Error(detalhe?.detail ?? `Erro ${res.status}`);
  }
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

export function buscarFeed(limite = 30, todos = false): Promise<Feed> {
  return request<Feed>(`/news/highlights?limite=${limite}&todos=${todos}`);
}

export function buscarArtigo(id: number): Promise<ArticleDetail> {
  return request<ArticleDetail>(`/news/articles/${id}`);
}

export function buscarMeusTemas(): Promise<MeusTemas> {
  return request<MeusTemas>('/news/me/topics');
}

export function salvarMeusTemas(topicIds: string[]): Promise<MeusTemas> {
  return request<MeusTemas>('/news/me/topics', {
    method: 'PUT',
    body: JSON.stringify({ topic_ids: topicIds }),
  });
}

export function buscarPreferencias(): Promise<{ email: boolean }> {
  return request<{ email: boolean }>('/news/me/preferences');
}

export function salvarPreferencias(email: boolean): Promise<{ email: boolean }> {
  return request<{ email: boolean }>('/news/me/preferences', {
    method: 'PUT',
    body: JSON.stringify({ email }),
  });
}

export function buscarFavoritos(): Promise<{ article_ids: number[] }> {
  return request<{ article_ids: number[] }>('/news/favorites');
}

export function alternarFavorito(articleId: number): Promise<{ article_ids: number[] }> {
  return request<{ article_ids: number[] }>('/news/favorites/toggle', {
    method: 'POST',
    body: JSON.stringify({ article_id: articleId }),
  });
}

/**
 * "Não é do meu interesse". É a única fonte de dado real para corrigir o
 * mapeamento tema<->especialidade — sem ela, ajustar a taxonomia vira palpite.
 */
export function naoInteressa(articleId: number, topicSlug?: string): Promise<void> {
  return request<void>('/news/feedback/nao-interessa', {
    method: 'POST',
    body: JSON.stringify({ article_id: articleId, topic_slug: topicSlug ?? null }),
  });
}

export function autenticarEmbed(email: string): Promise<{ access_token: string }> {
  return request<{ access_token: string }>('/auth/embed/token', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}
