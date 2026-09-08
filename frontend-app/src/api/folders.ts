import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

function authHeaders(): HeadersInit {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

/** "clinical" = pasta de um paciente; "general" = estudo, gestão, tema. */
export type FolderKind = 'clinical' | 'general';

export interface Folder {
  id: string;
  name: string;
  folder_kind: FolderKind;
  /**
   * Contexto declarado pelo médico: a evolução do paciente numa pasta clínica,
   * o objetivo/escopo numa pasta geral. O nome do campo vem da migration que o
   * criou, quando só existiam pastas clínicas.
   */
  clinical_context: string | null;
  created_at: string;
  updated_at: string;
}

/** Teto do texto de evolução — espelha MAX_CHARS_EVOLUCAO na API, que devolve 422 acima disso. */
export const MAX_CHARS_EVOLUCAO = 8000;

export async function listFolders(): Promise<Folder[]> {
  const res = await fetch(`${BASE}/api/v1/folders`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Erro ao carregar pastas');
  return res.json();
}

export async function createFolder(
  name: string,
  clinicalContext?: string,
  folderKind: FolderKind = 'clinical',
): Promise<Folder> {
  const res = await fetch(`${BASE}/api/v1/folders`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({
      name,
      folder_kind: folderKind,
      ...(clinicalContext ? { clinical_context: clinicalContext } : {}),
    }),
  });
  if (!res.ok) throw new Error('Erro ao criar pasta');
  return res.json();
}

/**
 * Renomeia a pasta SEM tocar na evolução.
 *
 * O campo é omitido de propósito: a API trata ausente como "não mexa". Mandar
 * `clinical_context: undefined` daqui seria o mesmo, mas mandar `null` ou `''`
 * APAGARIA a evolução do paciente — use `updateFolder` para editá-la.
 */
export async function renameFolder(id: string, name: string): Promise<Folder> {
  const res = await fetch(`${BASE}/api/v1/folders/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Erro ao renomear pasta');
  return res.json();
}

/**
 * Atualiza nome e evolução juntos.
 *
 * `clinicalContext` como string vazia LIMPA a evolução — é assim que o médico
 * apaga o que escreveu. Para não mexer nela, use `renameFolder`.
 */
export async function updateFolder(
  id: string,
  name: string,
  clinicalContext: string,
  folderKind: FolderKind,
): Promise<Folder> {
  const res = await fetch(`${BASE}/api/v1/folders/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify({ name, clinical_context: clinicalContext, folder_kind: folderKind }),
  });
  if (!res.ok) throw new Error('Erro ao salvar pasta');
  return res.json();
}

export async function deleteFolder(id: string): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/folders/${id}`, {
    method: 'DELETE',
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error('Erro ao excluir pasta');
}

export async function moveConversation(conversationId: string, folderId: string | null): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/folders/conversations/${conversationId}/folder`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ folder_id: folderId }),
  });
  if (!res.ok) throw new Error('Erro ao mover conversa');
}

export async function bulkMoveConversations(conversationIds: string[], folderId: string | null): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/folders/conversations/bulk`, {
    method: 'PATCH',
    headers: authHeaders(),
    body: JSON.stringify({ conversation_ids: conversationIds, folder_id: folderId }),
  });
  if (!res.ok) throw new Error('Erro ao mover conversas');
}
