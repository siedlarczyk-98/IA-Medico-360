/**
 * Perda de sessão no celular — o que vale para os três apps.
 *
 * O caso que originou isto: nas calculadoras, depois de uma hora de app aberto,
 * alternar entre a lista e uma calculadora mostrava "Calculadora não
 * encontrada". Era o token vencido (401) caindo no ramo do 404. As calculadoras
 * e as notícias não têm suíte própria de unidade; o código compartilhado
 * (`shared/embed/sessao.ts`) e a regra de descarte do embed são travados aqui.
 */

import { act, render, renderHook, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { reservarReentradaPelaWaid, useSessaoViva } from '@shared/embed/sessao';

import { EmbedAuthPage } from '../pages/EmbedAuthPage';

const CHAVE_TOKEN = 'medico360_token';

function tokenQueVenceEm(ms: number): string {
  const exp = Math.floor((Date.now() + ms) / 1000);
  return `a.${btoa(JSON.stringify({ sub: 'u1', role: 'medico', exp }))}.c`;
}

function voltarDoSegundoPlano() {
  act(() => {
    Object.defineProperty(document, 'hidden', { value: false, configurable: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
}

function instalarPonteNativa() {
  (window as unknown as { ReactNativeWebView?: unknown }).ReactNativeWebView = {};
}

beforeEach(() => {
  vi.useFakeTimers();
  Object.defineProperty(document, 'hidden', { value: false, configurable: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  delete (window as unknown as { ReactNativeWebView?: unknown }).ReactNativeWebView;
  localStorage.clear();
  sessionStorage.clear();
});

function usarSessao(aoExpirar: () => void) {
  return renderHook(() => useSessaoViva({
    apiBase: 'http://api',
    getToken: () => localStorage.getItem(CHAVE_TOKEN),
    setToken: t => localStorage.setItem(CHAVE_TOKEN, t),
    aoExpirar,
  }));
}

describe('token que venceu com o app em segundo plano', () => {
  it('avisa o app na volta, para ele entrar de novo', () => {
    // Renovar não serve mais: o backend só troca token ainda válido.
    vi.stubGlobal('fetch', vi.fn());
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(30 * 60 * 1000));
    const aoExpirar = vi.fn();
    usarSessao(aoExpirar);

    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(-60 * 1000));
    voltarDoSegundoPlano();

    expect(aoExpirar).toHaveBeenCalledTimes(1);
    expect(fetch).not.toHaveBeenCalled();
  });

  it('não avisa na montagem: token vencido ao abrir é assunto da rota', () => {
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(-60 * 1000));
    const aoExpirar = vi.fn();
    usarSessao(aoExpirar);
    expect(aoExpirar).not.toHaveBeenCalled();
  });

  it('não avisa pelo timer: não tira o médico da tela sem ele estar olhando', async () => {
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(-60 * 1000));
    const aoExpirar = vi.fn();
    usarSessao(aoExpirar);
    await act(async () => { await vi.advanceTimersByTimeAsync(20 * 60 * 1000); });
    expect(aoExpirar).not.toHaveBeenCalled();
  });

  it('token perto de vencer é renovado, não tratado como vencido', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ access_token: 'jwt-novo' }) });
    vi.stubGlobal('fetch', fetchSpy);
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(3 * 60 * 1000));
    const aoExpirar = vi.fn();
    usarSessao(aoExpirar);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });

    expect(aoExpirar).not.toHaveBeenCalled();
    expect(localStorage.getItem(CHAVE_TOKEN)).toBe('jwt-novo');
  });
});

describe('reentrada pela Waid', () => {
  it('fora da Waid não há handshake: vai para o login', () => {
    expect(reservarReentradaPelaWaid()).toBe(false);
  });

  it('no app nativo, entra de novo pela Waid', () => {
    instalarPonteNativa();
    expect(reservarReentradaPelaWaid()).toBe(true);
  });

  it('não tenta duas vezes seguidas — trava contra laço', () => {
    // Se o token recém-chegado também leva 401, voltar ao handshake giraria
    // para sempre.
    instalarPonteNativa();
    expect(reservarReentradaPelaWaid()).toBe(true);
    expect(reservarReentradaPelaWaid()).toBe(false);

    vi.advanceTimersByTime(61_000);
    expect(reservarReentradaPelaWaid()).toBe(true);
  });
});

describe('entrada do embed quando a Waid não responde', () => {
  function renderizarEntrada() {
    return render(
      <MemoryRouter initialEntries={['/embed-auth']}>
        <Routes>
          <Route path="/embed-auth" element={<EmbedAuthPage />} />
          <Route path="/" element={<p>tela inicial</p>} />
        </Routes>
      </MemoryRouter>,
    );
  }

  it('no app nativo, NÃO apaga o login por e-mail do aparelho e segue com ele', () => {
    // A regressão: desde que a ponte responde no app, o erro ali é `timeout`,
    // não `sem_iframe` — e a regra antiga apagava o token do dono do aparelho.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    instalarPonteNativa();
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(40 * 60 * 1000));

    renderizarEntrada();
    act(() => void vi.advanceTimersByTime(30_000));

    expect(localStorage.getItem(CHAVE_TOKEN)).not.toBeNull();
    expect(screen.getByText('tela inicial')).toBeInTheDocument();
  });

  it('dentro do iframe, descarta a sessão que estava no navegador', () => {
    // Estação compartilhada: a sessão pode ser de outro médico.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }));
    vi.spyOn(window, 'parent', 'get').mockReturnValue({ postMessage: vi.fn() } as unknown as Window);
    localStorage.setItem(CHAVE_TOKEN, tokenQueVenceEm(40 * 60 * 1000));

    renderizarEntrada();
    act(() => void vi.advanceTimersByTime(30_000));

    expect(localStorage.getItem(CHAVE_TOKEN)).toBeNull();
    expect(screen.queryByText('tela inicial')).not.toBeInTheDocument();
  });
});
