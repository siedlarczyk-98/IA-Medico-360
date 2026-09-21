/**
 * Contrato dos eventos SSE de `POST /api/v1/orquestrador/stream`.
 *
 * Conferido nas DUAS pontas:
 *  - `tests/test_contrato_sse.py`: o backend só emite o que está aqui;
 *  - `frontend-app/src/api/orquestrador.sse.test.ts`: o chat trata tudo que está
 *    marcado `tratado`.
 *
 * Evento novo entra AQUI primeiro; os dois testes quebram até cada lado
 * acompanhar. Sem isto, um evento novo no backend não quebrava nada visível: o
 * leitor o repassa, ninguém o trata, e a informação some em silêncio.
 *
 * FORMATO: uma entrada por linha, `nome: 'papel',`. O teste do backend lê este
 * arquivo como texto — mantenha assim.
 */
export const CONTRATO_SSE = {
  start: 'informativo',
  token: 'tratado',
  cache_hit: 'tratado',
  clarification: 'tratado',
  text_done: 'tratado',
  done: 'tratado',
  error: 'tratado',
} as const;
