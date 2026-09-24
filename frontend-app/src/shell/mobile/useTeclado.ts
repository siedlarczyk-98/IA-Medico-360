/**
 * Mantém a casca do tamanho da área VISÍVEL quando o teclado abre.
 *
 * Os navegadores discordam sobre o que o teclado faz com a página:
 *
 * - Chrome Android com `interactive-widget=resizes-content` (que a casca liga
 *   no meta viewport) encolhe o layout: `100dvh` já é a área acima do teclado.
 * - Safari e o WKWebView do iOS NÃO encolhem o layout: o teclado cobre a parte
 *   de baixo da página, e o iOS ainda rola a página para mostrar o campo. Com
 *   só `100dvh`, o campo de pergunta ficava atrás do teclado.
 *
 * O `visualViewport` diz, nos dois, qual retângulo está de fato visível. A
 * casca é posicionada nele: altura = altura visível, topo = deslocamento da
 * rolagem que o iOS fez. No Android os dois valores coincidem com o layout e
 * nada muda.
 *
 * Escreve direto em variáveis CSS do elemento, sem estado React: o evento
 * dispara a cada quadro da animação do teclado, e um re-render por quadro
 * redesenharia o chat inteiro.
 *
 * COMO SE SABE QUE O TECLADO ABRIU
 * Comparando a altura visível com a MAIOR altura já vista nesta largura — a da
 * tela sem teclado. Era `innerHeight - visualViewport.height`, que funciona no
 * iOS (só a área visível encolhe) mas não no Android: com `resizes-content` o
 * layout encolhe junto, as duas medidas caem juntas e a diferença fica em zero.
 * O teclado nunca era detectado, e a saudação ficava na tela ocupando metade do
 * espaço acima dele (item 64 de `docs/pitacos-do-fable-2.md`, visto no app da
 * Waid em 2026-09-24).
 */

import { useCallback } from 'react';

/**
 * Devolve um ref callback para a raiz da casca. É ref, e não efeito sobre um
 * `RefObject`, porque a configuração pertence ao elemento: nasce quando ele
 * monta e é desfeita (pela função de limpeza do ref, React 19) quando sai.
 */
export function useTeclado(): (el: HTMLElement | null) => (() => void) | undefined {
  return useCallback((el: HTMLElement | null) => {
    const vv = window.visualViewport;
    if (!vv || !el) return undefined;

    // A altura da tela SEM teclado, por largura. Girar o aparelho muda as duas
    // medidas; aí a referência recomeça da altura atual.
    let largura = vv.width;
    let alturaSemTeclado = Math.max(window.innerHeight, vv.height);

    function aplicar() {
      if (!vv || !el) return;
      if (Math.abs(vv.width - largura) > 1) {
        largura = vv.width;
        alturaSemTeclado = vv.height;
      }
      alturaSemTeclado = Math.max(alturaSemTeclado, vv.height);
      el.style.setProperty('--altura-visivel', `${vv.height}px`);
      el.style.setProperty('--topo-visivel', `${vv.offsetTop}px`);
      // Teclado aberto = a área visível perdeu boa parte da altura sem teclado.
      // 120 px fica acima da barra de endereço que aparece e some (~56 px) e bem
      // abaixo de qualquer teclado. Serve para esconder o que é dispensável
      // enquanto se digita.
      el.dataset.teclado = alturaSemTeclado - vv.height > 120 ? 'aberto' : 'fechado';
    }

    aplicar();
    vv.addEventListener('resize', aplicar);
    vv.addEventListener('scroll', aplicar);
    return () => {
      vv.removeEventListener('resize', aplicar);
      vv.removeEventListener('scroll', aplicar);
    };
  }, []);
}
