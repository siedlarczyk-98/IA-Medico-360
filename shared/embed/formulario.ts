/**
 * Formulário que sobrevive à reentrada.
 *
 * O PROBLEMA
 * Quando a sessão cai (401, token vencido na volta do segundo plano), o app
 * entra de novo com `location.replace` — navegação completa, de propósito: zera
 * o cache que ainda guardava o usuário da sessão morta. Só que zera também o
 * formulário: o assistente de risco CV com quinze campos preenchidos voltava
 * vazio depois da reentrada, e o médico digitava tudo de novo (item 63 de
 * `docs/pitacos-do-fable-2.md`).
 *
 * COMO FUNCIONA
 *  1. o formulário aberto registra o próprio estado (`usePreservarFormulario`);
 *  2. quem dispara a reentrada chama `guardarFormulariosAbertos(dono)` ANTES de
 *     navegar — é o único momento em que se sabe que a página vai morrer;
 *  3. na volta, o formulário lê o que foi guardado (`useFormularioSalvo`).
 *
 * O QUE ISTO NÃO FAZ, DE PROPÓSITO
 * Não guarda o formulário continuamente. Reabrir uma calculadora depois de usar
 * outra tem que mostrá-la VAZIA: preenchida, traria os dados do paciente
 * anterior, e um número calculado com a idade ou o colesterol de outra pessoa é
 * pior do que nenhum. Só a reentrada devolve o que havia.
 *
 * E só ao mesmo médico, e por pouco tempo: a `sessionStorage` é da aba, e numa
 * estação compartilhada quem entra pelo login depois da queda pode ser outro.
 */

import { useEffect, useState } from 'react';

const PREFIXO = 'm360_formulario:';

/**
 * Depois disto o que foi guardado não volta mais. A reentrada leva segundos
 * (handshake) ou poucos minutos (código por e-mail); meia hora cobre os dois
 * com folga, e passado isso o médico já está em outro paciente.
 */
const VALIDADE_MS = 30 * 60 * 1000;

interface Guardado {
  dono: string;
  em: number;
  estado: unknown;
}

/** Estado atual de cada formulário montado, por chave. */
const abertos = new Map<string, unknown>();

/**
 * Registra o estado deste formulário para ser guardado se a sessão cair.
 *
 * A chave distingue formulários (`generico:curb65`, `prevent`). O estado precisa
 * sobreviver a `JSON.stringify` — `Set` e `Date` viram outra coisa; converta.
 */
export function usePreservarFormulario(chave: string, estado: unknown): void {
  useEffect(() => {
    abertos.set(chave, estado);
    return () => { abertos.delete(chave); };
  });
}

/**
 * Grava na `sessionStorage` todo formulário aberto. Chamar logo antes de sair
 * para a reentrada, com o `sub` do token que está caindo.
 */
export function guardarFormulariosAbertos(dono: string | null | undefined): void {
  if (!dono) return;
  for (const [chave, estado] of abertos) {
    try {
      const guardado: Guardado = { dono, em: Date.now(), estado };
      sessionStorage.setItem(PREFIXO + chave, JSON.stringify(guardado));
    } catch {
      /* sem sessionStorage (ou cheia) a reentrada funciona igual; só volta vazio */
    }
  }
}

function ler<T>(chave: string, dono: string | null | undefined): T | null {
  try {
    const bruto = sessionStorage.getItem(PREFIXO + chave);
    if (!bruto) return null;
    const guardado = JSON.parse(bruto) as Partial<Guardado>;
    if (!dono || guardado.dono !== dono) return null;
    if (typeof guardado.em !== 'number' || Date.now() - guardado.em > VALIDADE_MS) return null;
    return (guardado.estado ?? null) as T | null;
  } catch {
    return null;
  }
}

/**
 * O que foi guardado para este formulário na última reentrada, ou `null`.
 *
 * Lê no inicializador do `useState` (puro, e o StrictMode o chama duas vezes) e
 * apaga no efeito: guardado é consumido uma vez só. Sem apagar, sair e voltar à
 * mesma calculadora mais tarde traria de novo os dados daquele paciente.
 *
 * O valor vem como foi gravado, possivelmente por uma versão anterior do app:
 * mescle sobre os valores iniciais em vez de usá-lo cru.
 */
export function useFormularioSalvo<T>(chave: string, dono: string | null | undefined): T | null {
  const [salvo] = useState(() => ler<T>(chave, dono));
  useEffect(() => {
    try {
      sessionStorage.removeItem(PREFIXO + chave);
    } catch {
      /* nada a apagar */
    }
  }, [chave]);
  return salvo;
}
