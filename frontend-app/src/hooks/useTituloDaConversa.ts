/**
 * O título da conversa aberta, para o cabeçalho.
 *
 * O cabeçalho mostrava sempre o começo da primeira pergunta (`chat.topbarTitle`).
 * Com renomear conversa (2026-09-24), isso deixaria o título novo só na lista: o
 * médico renomeava e o topo da tela continuava com o texto antigo.
 *
 * Lê a MESMA consulta de `useConversasEPastas` (mesma chave, função e validade):
 * o react-query não busca de novo, e a troca otimista do título aparece aqui na
 * hora. Sem título na lista (conversa que acabou de nascer e ainda não voltou
 * do servidor), cai no texto da primeira pergunta.
 */
import { useQuery } from '@tanstack/react-query';

import { listConversations, type ConversationSummary } from '../api/conversations';

export function useTituloDaConversa(conversaId: string | undefined, reserva: string): string {
  const { data } = useQuery<ConversationSummary[]>({
    queryKey: ['conversations'],
    queryFn: listConversations,
    staleTime: 60_000,
  });
  const titulo = conversaId ? data?.find(c => c.id === conversaId)?.title : null;
  return titulo || reserva;
}
