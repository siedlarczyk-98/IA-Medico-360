/**
 * Handshake de identidade com a Waid.
 *
 * Vive aqui, e não em `shared/`, porque é onde o Vitest já está configurado (o
 * `shared/` não é um pacote com runner próprio). O alvo do teste é o código
 * compartilhado — quando `calculadoras-app` e `noticias-app` migrarem, é este
 * arquivo que continua garantindo o contrato para os três.
 *
 * Até agora havia ZERO teste de autenticação no frontend. O handshake é o pior
 * lugar possível para essa lacuna: ele tem ordem que importa (ouvinte antes do
 * pedido), retentativa, e um caminho de erro que precisa distinguir "peça outro
 * token" de "desista" — e nada disso é visível olhando a tela.
 */

import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useIdentidadeWaid } from '@shared/embed/identidade';

const WAID = 'https://waid.exemplo.com';
const API = 'https://api.exemplo.com';

/**
 * Deixa as promessas pendentes rodarem, sob timers falsos.
 *
 * `waitFor` do Testing Library faz polling com timer, e com `useFakeTimers` ele
 * nunca avança sozinho — os testes ficavam pendurados até estourar. Avançar 0ms
 * de forma assíncrona drena a fila de microtasks, que é o que o handshake
 * precisa (o `fetch` da troca).
 */
async function aguardar() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0);
  });
}

function despachar(dados: unknown, origin = WAID) {
  act(() => {
    window.dispatchEvent(new MessageEvent('message', { data: dados, origin }));
  });
}

function montar(aoAutenticar = vi.fn()) {
  const resultado = renderHook(() =>
    useIdentidadeWaid({ apiBase: API, waidOrigin: WAID, aoAutenticar }),
  );
  return { ...resultado, aoAutenticar };
}

let postMessage: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.useFakeTimers();
  postMessage = vi.fn();
  vi.spyOn(window, 'parent', 'get').mockReturnValue({ postMessage } as unknown as Window);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

describe('pedido da identidade', () => {
  it('pede assim que monta', () => {
    montar();
    expect(postMessage).toHaveBeenCalledWith({ type: 'waid:identity-request' }, WAID);
  });

  it('repete a cada 2s enquanto não recebe', () => {
    // A doc pede isto: a ordem de carregamento varia, e um pedido que sai antes
    // do outro lado estar ouvindo é simplesmente perdido — não fica em fila.
    montar();
    expect(postMessage).toHaveBeenCalledTimes(1);

    act(() => void vi.advanceTimersByTime(2000));
    expect(postMessage).toHaveBeenCalledTimes(2);

    act(() => void vi.advanceTimersByTime(4000));
    expect(postMessage).toHaveBeenCalledTimes(4);
  });

  it('para de pedir depois de receber', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'jwt', onboarding_complete: true }),
    }));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await aguardar();
    expect(result.current.fase).toBe('pronto');

    const antes = postMessage.mock.calls.length;
    act(() => void vi.advanceTimersByTime(6000));
    expect(postMessage).toHaveBeenCalledTimes(antes);
  });
});

describe('filtragem das mensagens', () => {
  it('ignora mensagem de outra origem', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    montar();

    // A doc chama a checagem de origem de opcional. Não é: é a única barreira
    // contra outra janela injetar um token que não é nosso.
    despachar({ type: 'waid:identity', token: 'abc' }, 'https://invasor.exemplo.com');

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('ignora mensagem de outro tipo', () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    montar();

    // A mesma janela recebe eventos de várias origens e bibliotecas.
    despachar({ type: 'outra-coisa', token: 'abc' });

    expect(fetchSpy).not.toHaveBeenCalled();
  });
});

describe('troca do token', () => {
  it('entrega a sessão ao app quando a troca dá certo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'jwt-novo', onboarding_complete: false }),
    }));
    const { result, aoAutenticar } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });

    await aguardar();
    expect(result.current.fase).toBe('pronto');
    expect(aoAutenticar).toHaveBeenCalledWith({
      access_token: 'jwt-novo',
      onboarding_complete: false,
    });
  });

  it('pede outro token quando o anterior queimou', async () => {
    // Ocorrência normal: recarregar a página invalida o token em voo. O médico
    // não pode ver tela de erro por causa disso.
    const fetchSpy = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 401,
      json: async () => ({ detail: { codigo: 'token_expirado' } }),
    });
    vi.stubGlobal('fetch', fetchSpy);
    const { result } = montar();

    const antes = postMessage.mock.calls.length;
    despachar({ type: 'waid:identity', token: 'velho' });

    await aguardar();
    expect(result.current.fase).toBe('pedindo');
    expect(postMessage.mock.calls.length).toBeGreaterThan(antes);
  });

  it('desiste quando o erro é de credencial nossa', async () => {
    // 503 significa api_key errada, endpoint sem permissão liberada, ou Waid
    // fora do ar. Pedir outro token não conserta — insistir viraria laço.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({ detail: 'indisponível' }),
    }));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });

    await aguardar();
    expect(result.current.fase).toBe('erro');
    expect(result.current.erro?.tipo).toBe('indisponivel');
  });

  it('trata falha de rede como indisponibilidade', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });

    await aguardar();
    expect(result.current.fase).toBe('erro');
  });
});

describe('timeout', () => {
  it('desiste com mensagem legível se a Waid nunca responde', () => {
    // O cenário real: "Enviar identidade por token" não foi ligado no admin da
    // Waid. Sem este teto a tela gira para sempre e ninguém sabe por quê.
    const { result } = montar();

    act(() => void vi.advanceTimersByTime(30_000));

    expect(result.current.fase).toBe('erro');
    expect(result.current.erro?.tipo).toBe('timeout');
    expect(result.current.erro?.mensagem).toContain('identidade');
  });

  it('não dispara se a identidade chegou antes', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'jwt', onboarding_complete: true }),
    }));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await aguardar();
    expect(result.current.fase).toBe('pronto');

    act(() => void vi.advanceTimersByTime(60_000));
    expect(result.current.fase).toBe('pronto');
  });
});

describe('limpeza', () => {
  it('para de pedir e de ouvir ao desmontar', () => {
    const remover = vi.spyOn(window, 'removeEventListener');
    const { unmount } = montar();

    unmount();
    const antes = postMessage.mock.calls.length;
    act(() => void vi.advanceTimersByTime(10_000));

    expect(postMessage).toHaveBeenCalledTimes(antes);
    expect(remover).toHaveBeenCalledWith('message', expect.any(Function));
  });
});

describe('fora de um iframe', () => {
  it('falha na hora, sem esperar o timeout', () => {
    // Medido nos aplicativos da Waid: a seção abre num webview direto, sem
    // iframe. `window.parent === window`, então nossos próprios pedidos voltam
    // para nós e a resposta nunca vem. Esperar 30s por algo impossível é a
    // pior experiência possível.
    vi.spyOn(window, 'parent', 'get').mockReturnValue(window);

    const { result } = montar();

    expect(result.current.fase).toBe('erro');
    expect(result.current.erro?.tipo).toBe('sem_iframe');
  });

  it('nem chega a pedir identidade', () => {
    vi.spyOn(window, 'parent', 'get').mockReturnValue(window);

    montar();
    act(() => void vi.advanceTimersByTime(10_000));

    expect(postMessage).not.toHaveBeenCalled();
  });
});
