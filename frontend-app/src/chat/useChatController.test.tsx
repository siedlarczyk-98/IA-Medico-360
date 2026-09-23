/**
 * As invariantes do chat, testadas SEM casca nenhuma.
 *
 * Os testes `App.*` verificam o mesmo pela tela de desktop. Estes existem para
 * que a casca mobile não precise provar tudo de novo: se o controller garante,
 * qualquer casca que só o consuma herda a garantia. Cada caso aqui é um bug que
 * já aconteceu em produção.
 */
import type { ReactNode } from 'react';
import { act, renderHook, waitFor } from '@testing-library/react';
import { QueryClientProvider } from '@tanstack/react-query';

import { getConversation } from '../api/conversations';
import { streamQuery, type Message, type StreamEvent } from '../api/orquestrador';
import { makeQueryClient, streamComEsperaAntesDoDone, streamEmLote, tokensEDone, tokensTextDoneEDone } from '../test/utils';
import { useChatController } from './useChatController';

vi.mock('../api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(),
}));

vi.mock('../api/orquestrador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/orquestrador')>()),
  streamQuery: vi.fn(),
  queryOrquestrador: vi.fn(),
}));

const streamQueryMock = vi.mocked(streamQuery);
const getConversationMock = vi.mocked(getConversation);

function montar() {
  const queryClient = makeQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return renderHook(() => useChatController(), { wrapper });
}

const respostas = (msgs: Message[]) => msgs.filter(m => m.role === 'assistant');

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useChatController', () => {
  it('tokens em lote viram UMA resposta, com o texto inteiro e o modo', async () => {
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['Segue', ' um', ' modelo.'])));
    const { result } = montar();

    act(() => result.current.sendMessage('anamnese'));

    await waitFor(() => expect(result.current.streaming).toBe(false));
    const r = respostas(result.current.messages);
    expect(r).toHaveLength(1);
    expect(r[0].content).toBe('Segue um modelo.');
    expect(r[0].mode).toBe('produtividade');
  });

  it('pergunta enviada entre text_done e done NÃO apaga a resposta anterior', async () => {
    const primeiro = streamComEsperaAntesDoDone(tokensTextDoneEDone(['Primeira resposta.']));
    streamQueryMock
      .mockImplementationOnce(() => primeiro.gerador())
      .mockImplementationOnce(() => streamEmLote(tokensEDone(['Segunda resposta.'])));
    const { result } = montar();

    act(() => result.current.sendMessage('um'));
    // text_done chegou: campo liberado, `done` ainda pendente.
    await waitFor(() => expect(result.current.streaming).toBe(false));
    expect(result.current.sendBlocked).toBe(false);

    act(() => result.current.sendMessage('dois'));
    await act(async () => { primeiro.liberar(); });

    await waitFor(() => expect(respostas(result.current.messages)).toHaveLength(2));
    expect(respostas(result.current.messages).map(m => m.content))
      .toEqual(['Primeira resposta.', 'Segunda resposta.']);
    // E a segunda foi na MESMA conversa: o text_done fixou o id antes do done.
    expect(streamQueryMock.mock.calls[1][0]).toMatchObject({ conversation_id: 'conv-1' });
  });

  it('o finally de um stream abortado não desliga o streaming do novo', async () => {
    // O primeiro stream fica pendurado até ser abortado.
    streamQueryMock.mockImplementationOnce((_p, signal) => (async function* (): AsyncGenerator<StreamEvent> {
      yield { type: 'token', text: 'parcial' };
      await new Promise((_r, rej) => signal?.addEventListener('abort', () =>
        rej(Object.assign(new Error('abort'), { name: 'AbortError' }))));
    })());
    const segundo = streamComEsperaAntesDoDone([{ type: 'token', text: 'nova' }, ...tokensEDone([])]);
    streamQueryMock.mockImplementationOnce(() => segundo.gerador());
    const { result } = montar();

    act(() => result.current.sendMessage('um'));
    await waitFor(() => expect(respostas(result.current.messages)).toHaveLength(1));

    act(() => result.current.sendMessage('dois'));
    await waitFor(() => expect(streamQueryMock).toHaveBeenCalledTimes(2));

    // O `finally` do primeiro já rodou; o segundo ainda está no ar.
    expect(result.current.streaming).toBe(true);
    // E a parcial do stream abortado saiu da tela.
    expect(result.current.messages.some(m => m.content === 'parcial')).toBe(false);

    await act(async () => { segundo.liberar(); });
    await waitFor(() => expect(result.current.streaming).toBe(false));
  });

  it('corrida: a conversa do ÚLTIMO clique ganha, mesmo respondendo antes', async () => {
    let liberarA!: () => void;
    getConversationMock
      .mockImplementationOnce(() => new Promise(r => { liberarA = () => r({
        id: 'A', title: 'A', feature: 'ORQUESTRADOR', folder_name: null,
        messages: [{ role: 'user', content: 'pergunta A' }],
      } as never); }))
      .mockImplementationOnce(async () => ({
        id: 'B', title: 'B', feature: 'ORQUESTRADOR', folder_name: null,
        messages: [{ role: 'user', content: 'pergunta B' }],
      } as never));
    const { result } = montar();

    act(() => { void result.current.handleSelectConversation('A'); });
    act(() => { void result.current.handleSelectConversation('B'); });
    await waitFor(() => expect(result.current.carregandoConversa).toBe(false));
    await act(async () => { liberarA(); });

    expect(result.current.activeConvId).toBe('B');
    expect(result.current.messages.map(m => m.content)).toEqual(['pergunta B']);
  });

  it('as ações devolvidas são estáveis entre renders (o memo da Sidebar depende)', async () => {
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['ok'])));
    const { result } = montar();
    const antes = result.current;

    act(() => result.current.sendMessage('x'));
    await waitFor(() => expect(result.current.streaming).toBe(false));

    expect(result.current.handleNew).toBe(antes.handleNew);
    expect(result.current.handleSelectConversation).toBe(antes.handleSelectConversation);
    expect(result.current.handleStop).toBe(antes.handleStop);
  });
});
