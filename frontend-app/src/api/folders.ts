import { getToken } from '../lib/auth';

const BASE = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

function authHeaders(): HeadersInit {
  const token = getToken();
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export interface Folder {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export async function listFolders(): Promise<Folder[]> {
  const res = await fetch(`${BASE}/api/v1/folders`, { headers: authHeaders() });
  if (!res.ok) throw new Error('Erro ao carregar pastas');
  return res.json();
}

export async function createFolder(name: string): Promise<Folder> {
  const res = await fetch(`${BASE}/api/v1/folders`, {
    method: 'POST',
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Erro ao criar pasta');
  return res.json();
}

export async function renameFolder(id: string, name: string): Promise<Folder> {
  const res = await fetch(`${BASE}/api/v1/folders/${id}`, {
    method: 'PUT',
    headers: authHeaders(),
    body: JSON.stringify({ name }),
  });
  if (!res.ok) throw new Error('Erro ao renomear pasta');
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
