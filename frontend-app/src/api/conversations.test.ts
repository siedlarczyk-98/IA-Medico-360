/**
 * A lista de conversas traz TODAS, não só a primeira página.
 *
 * Só se pedia a primeira página de 50: a 51ª conversa ficava inalcançável e sumia
 * da pasta onde estava.
 */
import { CONVERSAS_POR_PAGINA, listConversations } from './conversations';

vi.mock('../lib/auth', () => ({ sessaoExpirou: vi.fn(), conferirSessao: vi.fn(), consumirRetomada: () => null, getToken: () => 'token-de-teste' }));

const fetchMock = vi.fn();

function conversas(de: number, ate: number) {
  return Array.from({ length: ate - de }, (_, i) => ({ id: `conv-${de + i}`, title: `Conversa ${de + i}` }));
}

function responder(paginas: unknown[][]) {
  fetchMock.mockImplementation(async (url: string) => {
    const pagina = Number(new URL(url).searchParams.get('page'));
    return new Response(JSON.stringify(paginas[pagina - 1] ?? []), { status: 200 });
  });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('listConversations', () => {
  it('busca página a página até a última, e devolve tudo', async () => {
    responder([conversas(0, 100), conversas(100, 200), conversas(200, 237)]);

    const todas = await listConversations();

    expect(todas).toHaveLength(237);
    expect(todas.at(-1)?.id).toBe('conv-236');
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('pede o maior tamanho de página que a API aceita', async () => {
    responder([conversas(0, 3)]);

    await listConversations();

    const url = new URL(fetchMock.mock.calls[0][0]);
    expect(url.searchParams.get('page_size')).toBe(String(CONVERSAS_POR_PAGINA));
    expect(CONVERSAS_POR_PAGINA).toBe(100);
  });

  it('quem tem poucas conversas faz UMA requisição', async () => {
    responder([conversas(0, 12)]);

    await listConversations();

    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('página cheia exata não engana: pede a seguinte e para no vazio', async () => {
    responder([conversas(0, 100), []]);

    expect(await listConversations()).toHaveLength(100);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('conversa que mudou de posição entre duas páginas não aparece duas vezes', async () => {
    const repetida = [{ id: 'conv-99', title: 'Conversa 99' }, ...conversas(100, 140)];
    responder([conversas(0, 100), repetida]);

    const todas = await listConversations();

    expect(todas.filter(c => c.id === 'conv-99')).toHaveLength(1);
    expect(todas).toHaveLength(140);
  });

  it('falha em qualquer página é erro, não lista pela metade', async () => {
    fetchMock.mockImplementation(async (url: string) =>
      new URL(url).searchParams.get('page') === '1'
        ? new Response(JSON.stringify(conversas(0, 100)), { status: 200 })
        : new Response('{}', { status: 500 }));

    await expect(listConversations()).rejects.toThrow(/histórico/i);
  });
});
