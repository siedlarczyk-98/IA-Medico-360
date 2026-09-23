/**
 * A escolha de casca: histerese, flag e override.
 *
 * Cada regra aqui evita um incômodo concreto — o celular deitado virando
 * desktop no meio da leitura, a janela piscando entre as cascas perto do
 * limite, um override de teste grudando num médico de verdade.
 */
import { act, renderHook } from '@testing-library/react';

import { definirViewport, VIEWPORT_CELULAR, VIEWPORT_CELULAR_DEITADO, VIEWPORT_DESKTOP } from '../test/viewport';
import { reiniciarLayout, useCompacto, useLayout } from './layout';

function ligar(flag: 'on' | 'qa' | 'off') {
  vi.stubEnv('VITE_SHELL_MOVEL', flag);
  reiniciarLayout();
}

afterEach(() => {
  vi.unstubAllEnvs();
  window.history.replaceState(null, '', '/');
});

describe('escolha de casca com a flag ligada', () => {
  beforeEach(() => ligar('on'));

  it('segue o espaço: desktop largo, mobile estreito', () => {
    const { result } = renderHook(() => useLayout());
    expect(result.current).toBe('desktop');

    definirViewport(VIEWPORT_CELULAR);
    expect(result.current).toBe('mobile');

    definirViewport(VIEWPORT_DESKTOP);
    expect(result.current).toBe('desktop');
  });

  it('histerese: na faixa do meio, fica a casca que já estava', () => {
    const { result } = renderHook(() => useLayout());

    definirViewport({ largura: 700, altura: 800, ponteiro: 'fine' });
    expect(result.current).toBe('mobile');
    definirViewport({ largura: 760 }); // faixa do meio: continua mobile
    expect(result.current).toBe('mobile');
    definirViewport({ largura: 830 });
    expect(result.current).toBe('desktop');
    definirViewport({ largura: 760 }); // faixa do meio: continua desktop
    expect(result.current).toBe('desktop');
  });

  it('celular deitado continua mobile, mesmo com 844 px de largura', () => {
    const { result } = renderHook(() => useLayout());
    definirViewport(VIEWPORT_CELULAR);
    definirViewport(VIEWPORT_CELULAR_DEITADO);
    expect(result.current).toBe('mobile');
    // E um celular grande deitado (915×412) também.
    definirViewport({ largura: 915, altura: 412 });
    expect(result.current).toBe('mobile');
  });

  it('abrir já deitado no celular começa em mobile, sem passar pelo desktop', () => {
    definirViewport(VIEWPORT_CELULAR_DEITADO);
    reiniciarLayout();
    const { result } = renderHook(() => useLayout());
    expect(result.current).toBe('mobile');
  });

  it('`useIsMobile` concorda com a casca, inclusive na faixa da histerese', () => {
    const { result } = renderHook(() => ({ layout: useLayout(), compacto: useCompacto() }));
    definirViewport({ largura: 830, altura: 800, ponteiro: 'fine' });
    definirViewport({ largura: 760 }); // desktop pela histerese, mas ≤ 768
    expect(result.current).toEqual({ layout: 'desktop', compacto: false });
  });
});

describe('flag e override', () => {
  it('flag desligada: sempre desktop, e `useIsMobile` volta à regra antiga (≤ 768)', () => {
    ligar('off');
    const { result } = renderHook(() => ({ layout: useLayout(), compacto: useCompacto() }));
    definirViewport(VIEWPORT_CELULAR);
    expect(result.current).toEqual({ layout: 'desktop', compacto: true });
  });

  it('flag em qa: desktop mesmo no celular, até o `?layout=mobile`', () => {
    ligar('qa');
    definirViewport(VIEWPORT_DESKTOP);
    const { result } = renderHook(() => useLayout());
    definirViewport(VIEWPORT_CELULAR);
    expect(result.current).toBe('desktop');

    window.history.replaceState(null, '', '/embed-auth?layout=mobile');
    act(() => reiniciarLayout());
    expect(result.current).toBe('mobile');
  });

  it('o override sobrevive ao redirecionamento que perde a query, e só na sessão', () => {
    ligar('qa');
    window.history.replaceState(null, '', '/embed-auth?layout=mobile');
    reiniciarLayout();
    window.history.replaceState(null, '', '/'); // o /embed-auth redirecionou
    reiniciarLayout();

    const { result } = renderHook(() => useLayout());
    expect(result.current).toBe('mobile');
    expect(sessionStorage.getItem('m360_layout')).toBe('mobile');
    expect(localStorage.getItem('m360_layout')).toBeNull();
  });

  it('`?layout=auto` em qa liga o automático', () => {
    ligar('qa');
    window.history.replaceState(null, '', '/?layout=auto');
    reiniciarLayout();
    const { result } = renderHook(() => useLayout());
    definirViewport(VIEWPORT_CELULAR);
    expect(result.current).toBe('mobile');
  });

  it('com a flag desligada, nem o override monta a casca mobile', () => {
    ligar('off');
    window.history.replaceState(null, '', '/?layout=mobile');
    reiniciarLayout();
    const { result } = renderHook(() => useLayout());
    expect(result.current).toBe('desktop');
  });
});
