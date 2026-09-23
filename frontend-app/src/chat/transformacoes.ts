/**
 * Conversões puras entre o que o orquestrador manda e o que a tela mostra.
 *
 * Viviam dentro de `App.tsx`. Saíram para cá quando a lógica do chat foi
 * separada da casca (desktop / mobile): as duas cascas usam o mesmo
 * `useChatController`, e ele usa estas funções. Nenhuma depende de React.
 */

import type { PubmedValidation, StreamEvent } from '../api/orquestrador';

/** Intervalo entre atualizações do texto em streaming. Ver `scheduleFlush`. */
export const INTERVALO_DE_FLUSH_MS = 100;

const BACKEND_TO_CHIP: Record<string, string> = {
  QUICK_SEARCH:      'busca',
  CLINICAL_REASONING:'raciocinio',
  PHARMA_CHECK:      'farmaco',
  PHARMA_BULA:       'farmaco',
  PHARMA_RECEITA:    'farmaco',
  PHARMA_GENERICO:   'farmaco',
  PRODUCTIVITY:      'produtividade',
  EXAM_REVIEW:       'exames',
  DATA_OCEAN:        'dados',
};

// Identidade da mensagem em streaming. Contador de módulo, e não crypto.randomUUID(),
// porque o valor precisa ser gerado de forma síncrona em qualquer ambiente (o
// jsdom dos testes inclusive) e só precisa ser único dentro da aba.
let streamMsgSeq = 0;
export function nextStreamMsgId(): string {
  streamMsgSeq += 1;
  return `stream-${streamMsgSeq}`;
}

// OFF_TOPIC (saudações/mensagens triviais) não ganha badge — é só uma resposta simples.
export function chipModeFor(mode: string): string | undefined {
  if (mode === 'OFF_TOPIC') return undefined;
  return BACKEND_TO_CHIP[mode] ?? mode;
}

/**
 * Converte as listas do PubMed do formato do evento `done` para o formato que
 * a ChatView consome. Devolve undefined quando não há nada — um bloco
 * "Referências verificadas" vazio é pior que bloco nenhum.
 *
 * Sem isto o orquestrador nunca exibia PubMed: o dado vinha no `done`, mas só
 * o agregador o convertia. O bloco existia na ChatView sem ninguém alimentá-lo.
 */
export function pubmedFromDone(
  event: Extract<StreamEvent, { type: 'done' | 'cache_hit' }>,
): PubmedValidation | undefined {
  const cited = (event.cited_guidelines_verified ?? []).map(c => ({
    title: c.title, pmid: c.pmid, verified: c.verified,
  }));
  const newer = (event.newer_guidelines_found ?? []).map(a => ({
    pmid: a.pmid,
    article_title: a.article_title ?? a.title ?? '',
    abstract_snippet: a.abstract_snippet ?? '',
  }));
  if (cited.length === 0 && newer.length === 0) return undefined;
  return { cited_verified: cited, newer_guidelines: newer };
}

export interface PendingClarification {
  conversationId: string;
  questions: string[];
}
