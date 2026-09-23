/**
 * Renovação da sessão ao voltar do segundo plano.
 *
 * O caso que originou isto: minimizar o aplicativo por mais de uma hora e
 * voltar para a tela de login. O que estes testes travam não é só o caminho
 * feliz — é sobretudo que uma renovação FALHA não derrube ninguém, porque
 * deslogar por causa de rede ruim seria criar o problema que viemos evitar.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useSessaoViva } from './useSessaoViva';
import * as auth from './auth';

function tokenQueVenceEm(ms: number): string {
  const exp = Math.floor((Date.now() + ms) / 1000);
  return `a.${btoa(JSON.stringify({ sub: 'u1', role: 'medico', exp }))}.c`;
}

function esconderEMostrar() {
  act(() => {
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

let setTokenSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  setTokenSpy = vi.spyOn(auth, 'setToken').mockImplementation(() => {});
  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe('quando renovar', () => {
  it('renova o token que está perto de vencer', async () => {
    localStorage.setItem('medico360_token', tokenQueVenceEm(2 * 60 * 1000));
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ access_token: 'jwt-novo' }),
    });
    vi.stubGlobal('fetch', fetchSpy);

    renderHook(() => useSessaoViva());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchSpy).toHaveBeenCalled();
    expect(setTokenSpy).toHaveBeenCalledWith('jwt-novo');
  });

  it('NÃO renova token novo em folha', () => {
    // Renovar a cada volta à tela seria gastar pedido à toa: o médico alterna
    // de app dezenas de vezes por plantão.
    localStorage.setItem('medico360_token', tokenQueVenceEm(50 * 60 * 1000));
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    renderHook(() => useSessaoViva());
    esconderEMostrar();

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('renova ao voltar do segundo plano', async () => {
    localStorage.setItem('medico360_token', tokenQueVenceEm(60 * 60 * 1000));
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ access_token: 'jwt-novo' }),
    });
    vi.stubGlobal('fetch', fetchSpy);
    renderHook(() => useSessaoViva());
    expect(fetchSpy).not.toHaveBeenCalled();

    // O app ficou parado: quando volta, o token já está na margem.
    localStorage.setItem('medico360_token', tokenQueVenceEm(3 * 60 * 1000));
    esconderEMostrar();
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(fetchSpy).toHaveBeenCalled();
  });

  it('não faz nada sem token: isso é caso de login, não de renovação', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);

    renderHook(() => useSessaoViva());
    esconderEMostrar();

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('falha na renovação não derruba ninguém', () => {
  it('mantém o token atual quando a rede falha', async () => {
    localStorage.setItem('medico360_token', tokenQueVenceEm(2 * 60 * 1000));
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));

    renderHook(() => useSessaoViva());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(setTokenSpy).not.toHaveBeenCalled();
    expect(localStorage.getItem('medico360_token')).not.toBeNull();
  });

  it('não limpa a sessão quando o servidor responde 401', async () => {
    // 401 aqui é sessão de 24h encerrada. Quem leva ao login é o fluxo normal,
    // com a mensagem certa — não um hook de manutenção apagando token calado.
    localStorage.setItem('medico360_token', tokenQueVenceEm(2 * 60 * 1000));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 401 }));

    renderHook(() => useSessaoViva());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(setTokenSpy).not.toHaveBeenCalled();
    expect(localStorage.getItem('medico360_token')).not.toBeNull();
  });
});

describe('limpeza', () => {
  it('para de ouvir e de contar ao desmontar', async () => {
    localStorage.setItem('medico360_token', tokenQueVenceEm(2 * 60 * 1000));
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ access_token: 'x' }),
    });
    vi.stubGlobal('fetch', fetchSpy);

    const { unmount } = renderHook(() => useSessaoViva());
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    unmount();
    const antes = fetchSpy.mock.calls.length;

    esconderEMostrar();
    await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60 * 1000); });

    expect(fetchSpy).toHaveBeenCalledTimes(antes);
  });
});
