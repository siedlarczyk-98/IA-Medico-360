/**
 * Detecção do teclado virtual na casca mobile (item 64).
 *
 * Era `innerHeight - visualViewport.height > 120`. No Android, com
 * `interactive-widget=resizes-content`, o layout encolhe junto com a área
 * visível — as duas medidas caem juntas e o teclado nunca era detectado. Visto
 * no app da Waid: teclado aberto e a saudação ainda na tela.
 */
import { act, renderHook } from '@testing-library/react';

import { useTeclado } from './useTeclado';

class ViewportFalso extends EventTarget {
  width = 400;
  height = 800;
  offsetTop = 0;
}

let vv: ViewportFalso;
let original: PropertyDescriptor | undefined;

function mudar({ altura, largura, janela }: { altura: number; largura?: number; janela?: number }) {
  act(() => {
    vv.height = altura;
    if (largura !== undefined) vv.width = largura;
    if (janela !== undefined) Object.defineProperty(window, 'innerHeight', { value: janela, configurable: true });
    vv.dispatchEvent(new Event('resize'));
  });
}

function montar(): HTMLElement {
  const el = document.createElement('div');
  const { result } = renderHook(() => useTeclado());
  result.current(el); // é o que o React faz com o ref callback na montagem
  return el;
}

beforeEach(() => {
  vv = new ViewportFalso();
  original = Object.getOwnPropertyDescriptor(window, 'visualViewport');
  Object.defineProperty(window, 'visualViewport', { value: vv, configurable: true });
  Object.defineProperty(window, 'innerHeight', { value: 800, configurable: true });
});

afterEach(() => {
  if (original) Object.defineProperty(window, 'visualViewport', original);
});

it('Android (resizes-content): layout e área visível encolhem juntos, e o teclado é detectado', () => {
  const el = montar();
  expect(el.dataset.teclado).toBe('fechado');

  mudar({ altura: 450, janela: 450 });

  expect(el.dataset.teclado).toBe('aberto');
});

it('iOS: só a área visível encolhe, e o teclado é detectado', () => {
  const el = montar();

  mudar({ altura: 450 });

  expect(el.dataset.teclado).toBe('aberto');
});

it('fechar o teclado volta ao normal', () => {
  const el = montar();
  mudar({ altura: 450, janela: 450 });

  mudar({ altura: 800, janela: 800 });

  expect(el.dataset.teclado).toBe('fechado');
});

it('a barra de endereço que aparece e some não conta como teclado', () => {
  const el = montar();

  mudar({ altura: 744, janela: 744 });

  expect(el.dataset.teclado).toBe('fechado');
});

it('girar o aparelho não é confundido com teclado', () => {
  // Deitado, a altura cai para menos da metade — sem teclado nenhum.
  const el = montar();

  mudar({ altura: 360, largura: 800, janela: 360 });
  expect(el.dataset.teclado).toBe('fechado');

  // E deitado o teclado continua sendo detectado.
  mudar({ altura: 180, janela: 180 });
  expect(el.dataset.teclado).toBe('aberto');
});

it('expõe a altura visível para o CSS posicionar a casca', () => {
  const el = montar();

  mudar({ altura: 450, janela: 450 });

  expect(el.style.getPropertyValue('--altura-visivel')).toBe('450px');
});
