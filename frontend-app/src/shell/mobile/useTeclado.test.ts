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
  scale = 1;
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
  Object.defineProperty(window, 'scrollY', { value: 0, configurable: true, writable: true });
  vi.mocked(window.scrollTo).mockClear();
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

/*
 * iPhone, app da Waid (2026-10-13): ao tocar no campo, o iOS rolava a página
 * quase inteira para cima — sobrava o campo colado no cabeçalho do app e o
 * fundo escuro do webview embaixo. A casca cabe na área visível; rolagem do
 * documento é sempre o iOS empurrando, e é desfeita.
 */
it('iOS: a rolagem que o teclado causa na página é desfeita', () => {
  montar();

  act(() => {
    (window as { scrollY: number }).scrollY = 340;
    window.dispatchEvent(new Event('scroll'));
  });

  expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
});

it('iOS: o deslocamento da área visível também é desfeito', () => {
  montar();

  act(() => {
    vv.height = 450;
    vv.offsetTop = 340;
    vv.dispatchEvent(new Event('resize'));
  });

  expect(window.scrollTo).toHaveBeenCalledWith(0, 0);
});

it('com zoom de pinça o deslocamento é do usuário e fica', () => {
  montar();

  act(() => {
    vv.scale = 2;
    vv.offsetTop = 200;
    vv.dispatchEvent(new Event('scroll'));
  });

  expect(window.scrollTo).not.toHaveBeenCalled();
});

it('página parada não é mexida', () => {
  montar();

  mudar({ altura: 450, janela: 450 });

  expect(window.scrollTo).not.toHaveBeenCalled();
});
