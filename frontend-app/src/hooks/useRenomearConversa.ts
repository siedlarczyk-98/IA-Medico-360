/**
 * Renomear conversa, com a troca otimista do título.
 *
 * Separado de `useConversasEPastas` porque tem dois donos: a lista (menu da
 * conversa) e o cabeçalho do desktop (o lápis ao lado do título). Uma mutação
 * só, para as duas portas não divergirem no rollback.
 *
 * Só a LISTA muda — a ordem não, porque renomear não é atividade (o servidor
 * também não mexe em `updated_at`). Se o servidor recusar, o título volta.
 */
import { useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';

import { renameConversation, type ConversationSummary } from '../api/conversations';

export function useRenomearConversa(): (convId: string, title: string) => void {
  const queryClient = useQueryClient();
  const { mutate } = useMutation({
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
  return useCallback((convId: string, title: string) => mutate({ convId, title }), [mutate]);
}
