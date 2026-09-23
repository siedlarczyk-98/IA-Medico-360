/**
 * `matchMedia` de mentira, mas que AVALIA a consulta.
 *
 * O jsdom não implementa `matchMedia`. Até aqui cada teste que precisava dele
 * fazia um stub à mão que respondia a UMA consulta (ver `ConvItem.test.tsx`).
 * A casca mobile escolhe o layout combinando largura, altura, ponteiro e
 * orientação — um stub de consulta fixa não serve. Este avalia o subconjunto de
 * media query que o app usa, contra um viewport que o teste controla.
 *
 * O padrão é um desktop (1280×800, mouse): os testes que existiam antes deste
 * arquivo seguem vendo a casca de desktop sem mudar nada.
 */

import { act } from '@testing-library/react';

import { aplicarLayoutAgora } from '../shell/layout';

export interface Viewport {
  largura: number;
  altura: number;
  ponteiro: 'fine' | 'coarse';
}

export const VIEWPORT_DESKTOP: Viewport = { largura: 1280, altura: 800, ponteiro: 'fine' };
/** iPhone 14 em pé. */
export const VIEWPORT_CELULAR: Viewport = { largura: 390, altura: 844, ponteiro: 'coarse' };
/** O mesmo iPhone deitado: largo, mas baixo e de dedo. */
export const VIEWPORT_CELULAR_DEITADO: Viewport = { largura: 844, altura: 390, ponteiro: 'coarse' };

let atual: Viewport = { ...VIEWPORT_DESKTOP };

interface ListaFalsa {
  consulta: string;
  ouvintes: Set<(e: MediaQueryListEvent) => void>;
  ultimo: boolean;
}
const listas = new Set<ListaFalsa>();

function px(valor: string): number {
  return parseFloat(valor);
}

/** Uma condição entre parênteses, ex. `max-width: 720px` ou `pointer: coarse`. */
function avaliarCondicao(condicao: string, v: Viewport): boolean {
  const [nomeCru, valorCru = ''] = condicao.split(':').map(s => s.trim());
  const nome = nomeCru.toLowerCase();
  const valor = valorCru.toLowerCase();
  switch (nome) {
    case 'min-width': return v.largura >= px(valor);
    case 'max-width': return v.largura <= px(valor);
    case 'min-height': return v.altura >= px(valor);
    case 'max-height': return v.altura <= px(valor);
    case 'pointer': return valor === v.ponteiro;
    case 'any-pointer': return valor === v.ponteiro;
    case 'hover': return valor === (v.ponteiro === 'fine' ? 'hover' : 'none');
    case 'any-hover': return valor === (v.ponteiro === 'fine' ? 'hover' : 'none');
    case 'orientation': return valor === (v.altura >= v.largura ? 'portrait' : 'landscape');
    case 'prefers-reduced-motion': return valor === 'no-preference';
    default: return false;
  }
}

/** Avalia `(a) and (b), (c)` — vírgula é OU, `and` é E. `not` não é suportado. */
export function avaliarConsulta(consulta: string, v: Viewport = atual): boolean {
  return consulta.split(',').some(parte => {
    const condicoes = [...parte.matchAll(/\(([^)]+)\)/g)].map(m => m[1]);
    if (condicoes.length === 0) return /^\s*(all|screen)\s*$/i.test(parte);
    return condicoes.every(c => avaliarCondicao(c, v));
  });
}

function criarLista(consulta: string): MediaQueryList {
  const lista: ListaFalsa = { consulta, ouvintes: new Set(), ultimo: avaliarConsulta(consulta) };
  listas.add(lista);
  const mql = {
    get matches() { return avaliarConsulta(consulta); },
    media: consulta,
    onchange: null,
    addEventListener: (_tipo: string, fn: (e: MediaQueryListEvent) => void) => { lista.ouvintes.add(fn); },
    removeEventListener: (_tipo: string, fn: (e: MediaQueryListEvent) => void) => { lista.ouvintes.delete(fn); },
    // API antiga, ainda usada por Safari < 14.
    addListener: (fn: (e: MediaQueryListEvent) => void) => { lista.ouvintes.add(fn); },
    removeListener: (fn: (e: MediaQueryListEvent) => void) => { lista.ouvintes.delete(fn); },
    dispatchEvent: () => true,
  };
  return mql as unknown as MediaQueryList;
}

/** Instala o `matchMedia` falso e o viewport de desktop. Chamado pelo `setup.ts`. */
export function instalarMatchMedia(): void {
  atual = { ...VIEWPORT_DESKTOP };
  listas.clear();
  Object.defineProperty(window, 'matchMedia', { configurable: true, writable: true, value: criarLista });
  aplicarDimensoes();
}

function aplicarDimensoes(): void {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: atual.largura });
  Object.defineProperty(window, 'innerHeight', { configurable: true, writable: true, value: atual.altura });
}

/**
 * Muda o viewport como o navegador faria ao girar ou redimensionar: atualiza
 * as dimensões, dispara `change` em cada consulta cujo resultado virou, e
 * `resize` na janela — e aplica a escolha de casca sem a espera do debounce.
 * Tudo dentro de `act`, porque os ouvintes mexem em estado.
 */
export function definirViewport(parcial: Partial<Viewport>): void {
  atual = { ...atual, ...parcial };
  act(() => {
    aplicarDimensoes();
    for (const lista of listas) {
      const agora = avaliarConsulta(lista.consulta);
      if (agora === lista.ultimo) continue;
      lista.ultimo = agora;
      const evento = { matches: agora, media: lista.consulta } as MediaQueryListEvent;
      for (const fn of lista.ouvintes) fn(evento);
    }
    window.dispatchEvent(new Event('resize'));
    // A troca de casca espera o fim da rajada de `resize` (ver `shell/layout`).
    // Aqui não há rajada: aplica já.
    aplicarLayoutAgora();
  });
}

export function viewportAtual(): Viewport {
  return { ...atual };
}
