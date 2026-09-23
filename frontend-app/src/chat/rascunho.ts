/**
 * O que o médico está escrevendo, fora da árvore React.
 *
 * POR QUE NÃO É `useState` NO CAMPO
 * Girar o celular troca a casca inteira (desktop ↔ mobile), e o campo de
 * digitação é remontado. Com estado local, o texto sumia — e, pior, um anexo
 * no meio do upload terminava de subir para um componente que já não existia:
 * o arquivo era processado (e pago) e não aparecia em lugar nenhum, e o
 * "enviando…" voltava a "pronto", liberando o envio sem o exame.
 *
 * POR QUE NÃO É ESTADO DO `MainApp`
 * Cada tecla re-renderizaria o chat inteiro, Markdown incluído. Aqui só quem
 * assina (o campo) re-renderiza.
 *
 * Um só rascunho por aba: só existe um campo de pergunta montado por vez.
 */

import { useSyncExternalStore } from 'react';

import type { Attachment, Effort } from '../components/InputBar';

export interface Rascunho {
  texto: string;
  esforco: Effort;
  anexos: Attachment[];
  envio: 'idle' | 'loading' | 'error';
  erroDeEnvio: string;
  /**
   * Lote inteiro pendente enquanto o aceite de imagem não vem: basta uma
   * imagem entre os arquivos para o consentimento ser necessário.
   */
  imagensPendentes: File[] | null;
}

const INICIAL: Rascunho = {
  texto: '',
  esforco: 'detalhado',
  anexos: [],
  envio: 'idle',
  erroDeEnvio: '',
  imagensPendentes: null,
};

let atual: Rascunho = INICIAL;
const ouvintes = new Set<() => void>();

function assinar(fn: () => void): () => void {
  ouvintes.add(fn);
  return () => { ouvintes.delete(fn); };
}

function ler(): Rascunho {
  return atual;
}

/** Aceita um objeto parcial ou uma função do estado anterior, como `setState`. */
export function alterarRascunho(mudanca: Partial<Rascunho> | ((r: Rascunho) => Partial<Rascunho>)): void {
  const parcial = typeof mudanca === 'function' ? mudanca(atual) : mudanca;
  atual = { ...atual, ...parcial };
  for (const fn of ouvintes) fn();
}

export function lerRascunho(): Rascunho {
  return atual;
}

export function useRascunho(): Rascunho {
  return useSyncExternalStore(assinar, ler, ler);
}

/** Só para testes: o store é de módulo e vazaria de um teste para o outro. */
export function reiniciarRascunho(): void {
  atual = INICIAL;
  for (const fn of ouvintes) fn();
}
