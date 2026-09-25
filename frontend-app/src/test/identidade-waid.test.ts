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

import { montarOrigensWaid, useIdentidadeWaid } from '@shared/embed/identidade';

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

  it('recusa do servidor mostra a frase dele e NÃO pede outro token (item 65)', async () => {
    // Conta desativada: antes virava "a verificação está indisponível", e o
    // médico esperava por algo que não ia mudar.
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({
        detail: {
          codigo: 'conta_inativa',
          mensagem: 'Sua conta no Médico 360 está desativada. Fale com o suporte.',
        },
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await aguardar();
    const pedidosAteAqui = postMessage.mock.calls.length;
    act(() => void vi.advanceTimersByTime(10_000));

    expect(result.current.fase).toBe('erro');
    expect(result.current.erro).toEqual({
      tipo: 'recusado',
      mensagem: 'Sua conta no Médico 360 está desativada. Fale com o suporte.',
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(postMessage.mock.calls.length).toBe(pedidosAteAqui);
  });

  it('403 sem código (origem não autorizada, configuração nossa) segue genérico', async () => {
    // A frase do servidor só aparece quando ele marca que é para o médico ler.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'Origem não autorizada para embed' }),
    }));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await aguardar();

    expect(result.current.erro?.tipo).toBe('indisponivel');
    expect(result.current.erro?.mensagem).not.toMatch(/origem/i);
  });

  it('trata falha de rede como indisponibilidade', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });

    await aguardar();
    expect(result.current.fase).toBe('erro');
  });
});

describe('limite de requisições (429) — o evento no mesmo Wi-Fi', () => {
  const LIMITE = { ok: false, status: 429, json: async () => ({ detail: 'Muitas requisições' }) };
  const SUCESSO = {
    ok: true,
    status: 200,
    json: async () => ({ access_token: 'jwt-novo', onboarding_complete: true }),
  };

  beforeEach(() => {
    vi.spyOn(Math, 'random').mockReturnValue(0);
  });

  it('espera e repete com o MESMO token, sem cair no login por código', async () => {
    // Desistir aqui mandava o médico para o código por e-mail, que tem limite
    // menor ainda. O limitador recusa antes da rota: o token não foi gasto.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(LIMITE)
      .mockResolvedValueOnce(LIMITE)
      .mockResolvedValueOnce(SUCESSO);
    vi.stubGlobal('fetch', fetchMock);
    const { result, aoAutenticar } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await aguardar();
    expect(result.current.fase).toBe('trocando');

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 + 5000);
    });

    expect(result.current.fase).toBe('pronto');
    expect(aoAutenticar).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    const corpos = fetchMock.mock.calls.map(([, init]) => JSON.parse(init.body).token);
    expect(corpos).toEqual(['abc', 'abc', 'abc']);
  });

  it('não repete para sempre: esgotadas as esperas, desiste', async () => {
    const fetchMock = vi.fn().mockResolvedValue(LIMITE);
    vi.stubGlobal('fetch', fetchMock);
    const { result } = montar();

    despachar({ type: 'waid:identity', token: 'abc' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 + 5000 + 10_000);
    });

    expect(fetchMock).toHaveBeenCalledTimes(4);
    expect(result.current.fase).toBe('erro');
    expect(result.current.erro?.tipo).toBe('indisponivel');
  });

  it('o timeout de 30 s do handshake não corta a espera', async () => {
    // O teto do handshake é para a Waid que não responde; aqui ela já respondeu.
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(LIMITE)
      .mockResolvedValueOnce(LIMITE)
      .mockResolvedValueOnce(LIMITE)
      .mockResolvedValueOnce(SUCESSO);
    vi.stubGlobal('fetch', fetchMock);
    const { result } = montar();

    act(() => void vi.advanceTimersByTime(20_000));
    despachar({ type: 'waid:identity', token: 'abc' });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000 + 5000 + 10_000);
    });

    expect(result.current.fase).toBe('pronto');
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

/**
 * O app nativo da Waid NÃO usa iframe.
 *
 * Medido em 22/09/2026 na página de diagnóstico, app 1.58.9 (Android): o
 * relatório mostrou `Dentro de iframe: NAO` e, ainda assim, duas mensagens
 * `waid:identity` com token, vindas de `https://www.medico360.app`.
 *
 * Antes disso o handshake abortava com `sem_iframe` antes de registrar o
 * ouvinte — a resposta chegava e não havia ninguém escutando. Estes testes
 * existem para que a correção não seja desfeita por quem só conheça o caso
 * do navegador.
 */
describe('app nativo (webview, sem iframe)', () => {
  const APP = 'https://www.medico360.app';

  function montarNativo(aoAutenticar = vi.fn()) {
    // Sem pai: é o que caracteriza o webview.
    vi.spyOn(window, 'parent', 'get').mockReturnValue(window);
    (window as unknown as { ReactNativeWebView?: unknown }).ReactNativeWebView = {};
    const resultado = renderHook(() =>
      useIdentidadeWaid({
        apiBase: API,
        waidOrigin: montarOrigensWaid(WAID, APP),
        aoAutenticar,
      }),
    );
    return { ...resultado, aoAutenticar };
  }

  afterEach(() => {
    delete (window as unknown as { ReactNativeWebView?: unknown }).ReactNativeWebView;
  });

  it('não aborta com sem_iframe quando há ponte nativa', () => {
    const { result } = montarNativo();
    expect(result.current.fase).toBe('pedindo');
  });

  it('aceita o token vindo da origem do app nativo', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: 'jwt', onboarding_complete: true }),
    }));
    const { result, aoAutenticar } = montarNativo();

    despachar({ type: 'waid:identity', token: 'abc' }, APP);

    await aguardar();
    expect(result.current.fase).toBe('pronto');
    expect(aoAutenticar).toHaveBeenCalled();
  });

  it('continua rejeitando origem desconhecida no app', () => {
    // Aceitar duas origens não pode virar aceitar qualquer uma: esta é a
    // barreira que impede outra janela de injetar um token que não é nosso.
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    montarNativo();

    despachar({ type: 'waid:identity', token: 'abc' }, 'https://invasor.exemplo.com');

    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('desiste quando não há iframe NEM ponte', () => {
    vi.spyOn(window, 'parent', 'get').mockReturnValue(window);
    const { result } = renderHook(() =>
      useIdentidadeWaid({ apiBase: API, waidOrigin: WAID, aoAutenticar: vi.fn() }),
    );
    expect(result.current.fase).toBe('erro');
    expect(result.current.erro?.tipo).toBe('sem_iframe');
  });
});

describe('montarOrigensWaid', () => {
  it('não duplica quando portal e app coincidem', () => {
    expect(montarOrigensWaid(WAID, WAID)).toEqual([WAID]);
  });

  it('mantém o portal em primeiro e ignora valor vazio', () => {
    expect(montarOrigensWaid(WAID, '')).toEqual([WAID]);
  });
});
