/**
 * Trocar de conversa e repetir um envio que falhou (itens 36 e 39 da varredura).
 *
 * - Clicar em duas conversas em sequência mostrava a que respondesse POR ÚLTIMO,
 *   não a do último clique — com a outra destacada na lateral.
 * - O clique não dava nenhum sinal até a rede responder.
 * - Todo erro era definitivo: o médico redigitava a pergunta.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { renderComProvedores, streamEmLote, tokensEDone } from './test/utils';
import { streamQuery } from './api/orquestrador';
import { getConversation } from './api/conversations';
import { ErroDeApi } from './api/erros';
import { consumirRetomada, sessaoExpirou } from './lib/auth';

vi.mock('./lib/auth', () => ({
  sessaoExpirou: vi.fn(), conferirSessao: vi.fn(), consumirRetomada: vi.fn(() => null),
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(), clearToken: vi.fn(), logout: vi.fn(),
}));
vi.mock('./api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com', role: 'medico',
    crm: null, crm_state: null, med_status: 'especialista', intercom_user_hash: null,
  })),
}));
vi.mock('./api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(),
}));
vi.mock('./api/folders', () => ({
  listFolders: vi.fn(async () => []),
  createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
}));
vi.mock('./api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: false, usage_percentage: null, week_reset_at: null })),
}));
vi.mock('./api/orquestrador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./api/orquestrador')>()),
  streamQuery: vi.fn(),
  queryOrquestrador: vi.fn(),
}));
// A lateral de verdade abre no hover e lista o que vem da API. Aqui interessa só
// o contrato dela com o App: `onSelect(id)` e o `activeId` que recebe de volta.
vi.mock('./components/Sidebar', () => ({
  Sidebar: ({ activeId, onSelect }: { activeId?: string; onSelect: (id: string) => void }) => (
    <nav>
      <button onClick={() => onSelect('conv-a')}>abrir A</button>
      <button onClick={() => onSelect('conv-b')}>abrir B</button>
      <span data-testid="conversa-ativa">{activeId ?? 'nenhuma'}</span>
    </nav>
  ),
}));

const getConversationMock = vi.mocked(getConversation);
const streamQueryMock = vi.mocked(streamQuery);

function conversa(id: string, texto: string) {
  return {
    id, title: texto, feature: 'ORQUESTRADOR', folder_name: null,
    messages: [{ role: 'user' as const, content: `pergunta de ${texto}` }, { role: 'assistant' as const, content: `resposta de ${texto}` }],
  };
}

/** Promessa que o teste resolve quando quiser — para escolher a ORDEM de chegada. */
function adiada<T>() {
  let resolver!: (v: T) => void;
  const promessa = new Promise<T>(r => { resolver = r; });
  return { promessa, resolver };
}

beforeEach(() => vi.clearAllMocks());

describe('trocar de conversa', () => {
  it('vale o ÚLTIMO clique, mesmo que a primeira conversa responda depois', async () => {
    const a = adiada<ReturnType<typeof conversa>>();
    const b = adiada<ReturnType<typeof conversa>>();
    getConversationMock.mockImplementation((id: string) => (id === 'conv-a' ? a.promessa : b.promessa) as never);
    const user = userEvent.setup();
    renderComProvedores(<App />);

    await user.click(await screen.findByText('abrir A'));
    await user.click(screen.getByText('abrir B'));
    b.resolver(conversa('conv-b', 'B'));   // a do último clique chega primeiro...
    await screen.findByText('resposta de B');
    a.resolver(conversa('conv-a', 'A'));   // ...e a antiga chega atrasada.
    await new Promise(r => setTimeout(r, 20));

    expect(screen.getByText('resposta de B')).toBeInTheDocument();
    expect(screen.queryByText('resposta de A')).not.toBeInTheDocument();
    expect(screen.getByTestId('conversa-ativa')).toHaveTextContent('conv-b');
  });

  it('o clique responde na hora: destaca a conversa e avisa que está carregando', async () => {
    const a = adiada<ReturnType<typeof conversa>>();
    getConversationMock.mockReturnValue(a.promessa as never);
    const user = userEvent.setup();
    renderComProvedores(<App />);

    await user.click(await screen.findByText('abrir A'));

    expect(screen.getByTestId('conversa-ativa')).toHaveTextContent('conv-a');
    expect(screen.getByRole('status')).toHaveTextContent(/carregando conversa/i);

    a.resolver(conversa('conv-a', 'A'));
    await screen.findByText('resposta de A');
    expect(screen.queryByText(/carregando conversa/i)).not.toBeInTheDocument();
  });
});

describe('tentar novamente', () => {
  async function enviar(texto: string) {
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText(/digite sua pergunta/i), texto);
    await user.click(screen.getByRole('button', { name: /enviar/i }));
    return user;
  }

  it('queda de rede oferece repetir o envio, sem redigitar', async () => {
    // Falha ASSÍNCRONA, como a rede de verdade: um `throw` síncrono faria o aviso
    // de erro entrar na lista antes da pergunta do médico.
    streamQueryMock.mockImplementationOnce(() => ({
      [Symbol.asyncIterator]: () => ({ next: () => Promise.reject(new TypeError('Failed to fetch')) }),
    }) as never);
    renderComProvedores(<App />);
    const user = await enviar('dose de amoxicilina');
    const botao = await screen.findByRole('button', { name: /tentar novamente/i });

    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['500 mg de 8/8h'])));
    await user.click(botao);

    await screen.findByText('500 mg de 8/8h');
    expect(streamQueryMock).toHaveBeenCalledTimes(2);
    expect(streamQueryMock.mock.calls[1][0]).toMatchObject({ prompt: 'dose de amoxicilina' });
    // O aviso de erro sai; a pergunta do médico aparece uma vez só.
    expect(screen.queryByText(/erro ao conectar/i)).not.toBeInTheDocument();
    expect(screen.getAllByText('dose de amoxicilina')).toHaveLength(1);
  });

  it.each([
    [401, 'Sua sessão expirou. Entrando de novo…'],
    [429, 'Limite semanal de uso atingido.'],
  ])('%i NÃO oferece o botão: repetir bateria na mesma parede', async (status, mensagem) => {
    streamQueryMock.mockImplementation(() => { throw new ErroDeApi(status, mensagem); });
    renderComProvedores(<App />);
    await enviar('qualquer pergunta');

    await screen.findByText(new RegExp(mensagem.slice(0, 20)));
    await waitFor(() => expect(screen.getByRole('button', { name: /enviar/i })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /tentar novamente/i })).not.toBeInTheDocument();
  });
});

describe('sessão recusada no meio do uso (item 60)', () => {
  // "Sair" em outro aparelho revoga todos. Antes, o 401 no chat era um balão sem
  // saída; ao abrir uma conversa, virava "Nova consulta" vazia em silêncio.

  it('401 ao enviar leva à reentrada levando a pergunta, que não chegou ao servidor', async () => {
    streamQueryMock.mockImplementation(() => { throw new ErroDeApi(401, 'Sua sessão expirou. Entrando de novo…'); });
    const user = userEvent.setup();
    renderComProvedores(<App />);

    await user.type(await screen.findByPlaceholderText(/digite sua pergunta/i), 'dose de amoxicilina');
    await user.click(screen.getByRole('button', { name: /enviar/i }));

    await waitFor(() => expect(sessaoExpirou).toHaveBeenCalledWith(
      expect.objectContaining({ pergunta: 'dose de amoxicilina' }),
    ));
  });

  it('401 ao abrir uma conversa leva à reentrada levando a conversa, sem esvaziar a tela antes', async () => {
    getConversationMock.mockRejectedValue(new ErroDeApi(401, 'Sua sessão expirou. Entrando de novo…'));
    const user = userEvent.setup();
    renderComProvedores(<App />);

    await user.click(await screen.findByText('abrir A'));

    await waitFor(() => expect(sessaoExpirou).toHaveBeenCalledWith({ conversaId: 'conv-a' }));
    expect(screen.getByTestId('conversa-ativa')).toHaveTextContent('conv-a');
  });

  it('erro que não é 401 ao abrir conversa continua voltando para uma consulta nova', async () => {
    getConversationMock.mockRejectedValue(new ErroDeApi(404, 'Conversa não encontrada'));
    const user = userEvent.setup();
    renderComProvedores(<App />);

    await user.click(await screen.findByText('abrir A'));

    await waitFor(() => expect(screen.getByTestId('conversa-ativa')).toHaveTextContent('nenhuma'));
    expect(sessaoExpirou).not.toHaveBeenCalled();
  });

  it('depois da reentrada, a conversa reabre e a pergunta volta para o campo', async () => {
    vi.mocked(consumirRetomada).mockReturnValueOnce({ pergunta: 'dose de amoxicilina', conversaId: 'conv-a' });
    getConversationMock.mockResolvedValue(conversa('conv-a', 'A') as never);
    renderComProvedores(<App />);

    await screen.findByText('resposta de A');
    expect(getConversationMock).toHaveBeenCalledWith('conv-a');
    expect(screen.getByPlaceholderText(/digite sua pergunta/i)).toHaveValue('dose de amoxicilina');
    // Volta para o campo; reenviar sozinho poderia mandar a pergunta duas vezes.
    expect(streamQueryMock).not.toHaveBeenCalled();
  });
});
