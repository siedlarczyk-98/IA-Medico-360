/**
 * Conversas e pastas do médico: leitura, agrupamento e as mutações otimistas.
 *
 * Vivia dentro da `Sidebar`, misturado com o que é só dela (fixar, hover,
 * arrastar). A casca mobile mostra os mesmos dados de outro jeito — histórico
 * numa gaveta, pastas numa tela própria — e precisa das mesmas mutações, com o
 * mesmo rollback. Duplicá-las seria ter duas regras de "mover conversa" que
 * podem divergir em silêncio.
 *
 * Os `handle*` devolvidos são estáveis: as listas memoizam os itens, e um
 * callback novo a cada render anularia o memo de toda a lista.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { listConversations, renameConversation, type ConversationSummary } from '../api/conversations';
import {
  bulkMoveConversations, createFolder, deleteFolder, listFolders, moveConversation,
  renameFolder, updateFolder, type Folder, type FolderKind,
} from '../api/folders';
import { groupByDate } from '../components/sidebar/groupByDate';

interface Opcoes {
  /** Conversa aberta. Se ela não está na lista, a lista está velha. */
  activeId?: string;
  /** Abre uma conversa nova — usado ao criar pasta (ver `onSuccess`). */
  onNew: (folderId?: string, folderName?: string) => void;
  /** Chamado quando um mover-em-lote começa, para a tela limpar a seleção. */
  onBulkMoved?: () => void;
}

export function useConversasEPastas({ activeId, onNew, onBulkMoved }: Opcoes) {
  const queryClient = useQueryClient();

  /**
   * Pasta criada agora, para nascer aberta na lista. É só o estado INICIAL da
   * linha da pasta: depois disso, abrir e fechar é do usuário.
   */
  const [pastaRecemCriadaId, setPastaRecemCriadaId] = useState<string | null>(null);

  const { data: todasConversas = [], isLoading: carregandoConversas } = useQuery<ConversationSummary[]>({
    queryKey: ['conversations'],
    queryFn: listConversations,
    staleTime: 60_000,
  });

  // Conversas antigas do Agregador saem da lista junto com o modo. Sem este
  // filtro elas continuariam abríveis, e abrir uma delas levaria a uma tela
  // que não existe mais. O dado permanece no banco — isto é só a vista.
  const conversations = useMemo(
    () => todasConversas.filter(c => c.feature !== 'AGREGADOR'),
    [todasConversas],
  );

  const { data: folders = [] } = useQuery<Folder[]>({
    queryKey: ['folders'],
    queryFn: listFolders,
    staleTime: 60_000,
  });

  const createFolderMutation = useMutation({
    mutationFn: ({ name, clinicalContext, folderKind }: { name: string; clinicalContext: string; folderKind: FolderKind }) =>
      createFolder(name, clinicalContext, folderKind),
    onMutate: async ({ name, clinicalContext, folderKind }) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      const previous = queryClient.getQueryData<Folder[]>(['folders']);
      const optimistic: Folder = {
        id: `optimistic-${Date.now()}`,
        name,
        folder_kind: folderKind,
        clinical_context: clinicalContext || null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) => [...old, optimistic]);
      return { previous };
    },
    onError: (_err, _name, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['folders'], ctx.previous);
    },
    /**
     * Criar uma pasta é um ato de intenção: quem acabou de criar "Paciente
     * Jorge" quer a próxima conversa lá dentro, não na raiz. Antes, a `Folder`
     * devolvida pelo POST era descartada e a conversa seguinte nascia fora —
     * silenciosamente, e com consequência clínica: a pasta injeta a evolução do
     * paciente em toda mensagem, então nascer fora dela é perder a evolução sem
     * nenhum sinal na tela.
     *
     * Aqui e não no `onMutate`: o id otimista (`optimistic-<timestamp>`) não é
     * um UUID, e mandá-lo como `folder_id` faria a API recusar o envio. Só o id
     * real serve, e ele só existe depois da resposta.
     */
    onSuccess: (pasta) => {
      setPastaRecemCriadaId(pasta.id);
      onNew(pasta.id, pasta.name);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const renameFolderMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => renameFolder(id, name),
    onMutate: async ({ id, name }) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      const previous = queryClient.getQueryData<Folder[]>(['folders']);
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) =>
        old.map(f => f.id === id ? { ...f, name } : f)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['folders'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  // Separada de `renameFolderMutation` de propósito: aquela omite
  // `clinical_context` para não tocar na evolução ao renomear inline. Esta
  // manda os dois porque veio do modal, onde o médico viu e editou o texto.
  const updateFolderMutation = useMutation({
    mutationFn: ({ id, name, clinicalContext, folderKind }: { id: string; name: string; clinicalContext: string; folderKind: FolderKind }) =>
      updateFolder(id, name, clinicalContext, folderKind),
    onMutate: async ({ id, name, clinicalContext, folderKind }) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      const previous = queryClient.getQueryData<Folder[]>(['folders']);
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) =>
        old.map(f => f.id === id ? { ...f, name, folder_kind: folderKind, clinical_context: clinicalContext || null } : f)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['folders'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['folders'] }),
  });

  const deleteFolderMutation = useMutation({
    mutationFn: (id: string) => deleteFolder(id),
    onMutate: async (id: string) => {
      await queryClient.cancelQueries({ queryKey: ['folders'] });
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previousFolders = queryClient.getQueryData<Folder[]>(['folders']);
      const previousConvs = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      queryClient.setQueryData<Folder[]>(['folders'], (old = []) => old.filter(f => f.id !== id));
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => c.folder_id === id ? { ...c, folder_id: null } : c)
      );
      return { previousFolders, previousConvs };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previousFolders) queryClient.setQueryData(['folders'], ctx.previousFolders);
      if (ctx?.previousConvs) queryClient.setQueryData(['conversations'], ctx.previousConvs);
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['folders'] });
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    },
  });

  const moveConvMutation = useMutation({
    mutationFn: ({ convId, folderId }: { convId: string; folderId: string | null }) =>
      moveConversation(convId, folderId),
    onMutate: async ({ convId, folderId }) => {
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previous = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => c.id === convId ? { ...c, folder_id: folderId } : c)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['conversations'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  // Otimista, como mover: o título novo aparece na hora, e volta se o servidor
  // recusar. Só a LISTA muda — a ordem não, porque renomear não é atividade.
  const renameConvMutation = useMutation({
    mutationFn: ({ convId, title }: { convId: string; title: string }) => renameConversation(convId, title),
    onMutate: async ({ convId, title }) => {
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previous = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => c.id === convId ? { ...c, title } : c)
      );
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['conversations'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  const bulkMoveMutation = useMutation({
    mutationFn: ({ ids, folderId }: { ids: string[]; folderId: string | null }) =>
      bulkMoveConversations(ids, folderId),
    onMutate: async ({ ids, folderId }) => {
      await queryClient.cancelQueries({ queryKey: ['conversations'] });
      const previous = queryClient.getQueryData<ConversationSummary[]>(['conversations']);
      const idSet = new Set(ids);
      queryClient.setQueryData<ConversationSummary[]>(['conversations'], (old = []) =>
        old.map(c => idSet.has(c.id) ? { ...c, folder_id: folderId } : c)
      );
      onBulkMoved?.();
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) queryClient.setQueryData(['conversations'], ctx.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  });

  // Conversa aberta que não aparece na lista: a lista está velha (a conversa
  // acabou de nascer, ou veio de outro aparelho). Recarrega.
  useEffect(() => {
    if (activeId && !conversations.some(c => c.id === activeId)) {
      queryClient.invalidateQueries({ queryKey: ['conversations'] });
    }
  }, [activeId, conversations, queryClient]);

  const groups = useMemo(() => groupByDate(conversations), [conversations]);

  const convsByFolder = useMemo(() => {
    const map: Record<string, ConversationSummary[]> = {};
    for (const f of folders) map[f.id] = [];
    for (const c of conversations) {
      if (c.folder_id && map[c.folder_id]) map[c.folder_id].push(c);
    }
    return map;
  }, [folders, conversations]);

  const criarPasta = createFolderMutation.mutate;
  const atualizarPasta = updateFolderMutation.mutate;
  const moverVarias = bulkMoveMutation.mutate;

  const handleMoveConv = useCallback(
    (convId: string, folderId: string | null) => moveConvMutation.mutate({ convId, folderId }),
    [moveConvMutation.mutate],
  );
  const handleRenameConversation = useCallback(
    (convId: string, title: string) => renameConvMutation.mutate({ convId, title }),
    [renameConvMutation.mutate],
  );
  const handleRenameFolder = useCallback(
    (id: string, name: string) => renameFolderMutation.mutate({ id, name }),
    [renameFolderMutation.mutate],
  );
  const handleDeleteFolder = useCallback(
    (id: string) => deleteFolderMutation.mutate(id),
    [deleteFolderMutation.mutate],
  );

  return {
    conversations,
    carregandoConversas,
    folders,
    groups,
    convsByFolder,
    pastaRecemCriadaId,
    criarPasta,
    atualizarPasta,
    moverVarias,
    handleMoveConv,
    handleRenameConversation,
    handleRenameFolder,
    handleDeleteFolder,
  };
}
