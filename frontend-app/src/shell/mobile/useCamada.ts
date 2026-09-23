/**
 * Estado de uma camada (gaveta, folha, tela) ligado ao botão voltar.
 *
 * `abrir(v)` empilha no histórico só se a camada estava fechada; se já estava
 * aberta, troca o conteúdo sem mexer no histórico (ver `camadas.ts`, "TROCAR,
 * NÃO FECHAR-E-ABRIR"). `fechar()` volta pelo histórico, e é o `popstate` que
 * de fato zera o estado.
 *
 * Aberta-ou-não mora num ref, atualizado só nos eventos: decidir dentro do
 * updater do `setState` empilharia duas vezes sob o StrictMode, que roda
 * updaters em dobro — o mesmo tipo de impureza que já picotou o stream.
 */

import { useCallback, useRef, useState } from 'react';

import { abrirCamada, fecharCamada, trocarCamada } from './camadas';

export function useCamada<T>(): {
  valor: T | null;
  abrir: (v: T) => void;
  fechar: (depois?: () => void) => void;
} {
  const [valor, setValor] = useState<T | null>(null);
  const aberta = useRef(false);

  const abrir = useCallback((v: T) => {
    const zerar = () => {
      aberta.current = false;
      setValor(null);
    };
    if (aberta.current) trocarCamada(zerar);
    else abrirCamada(zerar);
    aberta.current = true;
    setValor(v);
  }, []);

  return { valor, abrir, fechar: fecharCamada };
}
