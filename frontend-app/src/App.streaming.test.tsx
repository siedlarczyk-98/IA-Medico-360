/**
 * Regressão do bug de resposta picotada.
 *
 * Sintoma relatado: a resposta começava, cortava, e recomeçava num balão novo —
 * em conversas longas até ~5 vezes. O fragmento ficava congelado e sem badge de
 * modo; só o último balão recebia o badge.
 *
 * Causa: `assistantIndex` era atribuído DENTRO do updater do `setMessages`, que
 * o React não executa de forma síncrona. Um segundo `token` chegando antes de a
 * atualização ser aplicada ainda via `-1` e criava outra mensagem.
 *
 * Estes testes alimentam vários `token` sem ceder o event loop entre eles, que é
 * exatamente a condição da corrida.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { renderComProvedores, streamEmLote, tokensEDone } from './test/utils';
import { streamQuery } from './api/orquestrador';

vi.mock('./lib/auth', () => ({
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('./api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com',
    role: 'medico', crm: null, crm_state: null, med_status: 'especialista',
    intercom_user_hash: null,
  })),
}));

vi.mock('./api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(async () => ({ id: 'conv-1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
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

const streamQueryMock = vi.mocked(streamQuery);

/** Digita no campo e envia, devolvendo o controle só depois do envio. */
async function enviarPergunta(texto = 'monte uma anamnese') {
  const user = userEvent.setup();
  const campo = await screen.findByPlaceholderText(/digite sua pergunta/i);
  await user.type(campo, texto);
  await user.click(screen.getByRole('button', { name: /enviar/i }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('streaming do orquestrador', () => {
  it('produz UMA mensagem quando os tokens chegam todos no mesmo lote', async () => {
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo', ' organizado', ' de anamnese.'])),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });

    // O coração da regressão: antes da correção saíam vários balões.
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
  });

  it('mantém a resposta inteira, sem perder o prefixo num fragmento', async () => {
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo', ' organizado', ' de anamnese.'])),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent(
        'Segue um modelo organizado de anamnese.',
      );
    });
  });

  it('aplica o badge de modo na mensagem que recebeu os tokens', async () => {
    // No print do bug, o fragmento saía SEM badge e só o último balão tinha.
    streamQueryMock.mockImplementation(() =>
      streamEmLote(tokensEDone(['Segue um', ' modelo'], { mode: 'PRODUCTIVITY' })),
    );

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent(/produtividade/i);
    });
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
  });

  it('não duplica mesmo com muitos tokens no mesmo lote', async () => {
    // 200 tokens: com o bug, cada token que perdia a corrida virava um balão.
    const muitos = Array.from({ length: 200 }, (_, i) => `t${i} `);
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(muitos)));

    renderComProvedores(<App />);
    await enviarPergunta();

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
    expect(screen.getByTestId('assistant-message')).toHaveTextContent('t199');
  });

  it('a pergunta do médico aparece uma vez só', async () => {
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['ok'])));

    renderComProvedores(<App />);
    await enviarPergunta('monte uma anamnese');

    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toBeInTheDocument();
    });
    expect(screen.getAllByTestId('user-message')).toHaveLength(1);
  });

  it('uma segunda pergunta não apaga a resposta da primeira', async () => {
    // A limpeza de stream abortado truncava a lista a partir de um índice
    // guardado. Com o id, ela remove só a mensagem parcial correspondente.
    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['primeira resposta'])));

    renderComProvedores(<App />);
    await enviarPergunta('primeira pergunta');
    await waitFor(() => {
      expect(screen.getByTestId('assistant-message')).toHaveTextContent('primeira resposta');
    });

    streamQueryMock.mockImplementation(() => streamEmLote(tokensEDone(['segunda resposta'])));
    await enviarPergunta('segunda pergunta');

    await waitFor(() => {
      expect(screen.getAllByTestId('assistant-message')).toHaveLength(2);
    });
    const respostas = screen.getAllByTestId('assistant-message');
    expect(respostas[0]).toHaveTextContent('primeira resposta');
    expect(respostas[1]).toHaveTextContent('segunda resposta');
  });
});
