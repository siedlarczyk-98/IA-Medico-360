/**
 * Girar o celular no meio de uma resposta.
 *
 * A troca de casca desmonta a árvore inteira da tela e monta outra. O estado do
 * chat fica acima dela (`useChatController` em `MainApp`), e é isto que estes
 * testes travam: a resposta que está chegando continua chegando, no mesmo
 * balão, sem pedir de novo ao modelo — e o que o médico estava digitando fica.
 */
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { renderComProvedores, streamComEsperaAntesDoDone, tokensTextDoneEDone } from './test/utils';
import { definirViewport, VIEWPORT_CELULAR, VIEWPORT_CELULAR_DEITADO } from './test/viewport';
import { reiniciarLayout } from './shell/layout';
import { streamQuery, type StreamEvent } from './api/orquestrador';

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

const casca = () => document.querySelector('[data-casca]')?.getAttribute('data-casca');

/** Stream que para NO MEIO dos tokens, até o teste liberar o resto. */
function streamPausadoNoMeio() {
  let liberar!: () => void;
  const espera = new Promise<void>(resolve => { liberar = resolve; });
  async function* gerador(): AsyncGenerator<StreamEvent> {
    yield { type: 'token', text: 'Apixabana 2,5 mg ' };
    await espera;
    yield* tokensTextDoneEDone(['12/12h.']);
  }
  return { gerador, liberar };
}

async function enviar(texto: string) {
  const user = userEvent.setup();
  const campo = await screen.findByPlaceholderText(/digite sua pergunta/i);
  await user.type(campo, texto);
  await user.click(screen.getByRole('button', { name: /enviar/i }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('VITE_SHELL_MOVEL', 'on');
  reiniciarLayout();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('troca de casca', () => {
  it('girar no MEIO dos tokens: a resposta continua no mesmo balão, sem pedir de novo', async () => {
    const stream = streamPausadoNoMeio();
    streamQueryMock.mockImplementation(() => stream.gerador());
    renderComProvedores(<App />);
    expect(casca()).toBe('desktop');

    await enviar('DOAC em FA com ClCr 25');
    await waitFor(() => expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana 2,5 mg'));

    definirViewport(VIEWPORT_CELULAR);
    await waitFor(() => expect(casca()).toBe('mobile'));
    // Ainda respondendo na casca nova: o Parar está lá, o texto parcial também.
    expect(screen.getByRole('button', { name: /parar/i })).toBeInTheDocument();
    expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana 2,5 mg');

    await act(async () => { stream.liberar(); });

    await waitFor(() => expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana 2,5 mg 12/12h.'));
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
    expect(streamQueryMock).toHaveBeenCalledTimes(1);
    expect(streamQueryMock.mock.calls[0][1]?.aborted).toBe(false);
  });

  it('girar entre text_done e done: os metadados chegam na casca nova', async () => {
    const stream = streamComEsperaAntesDoDone(tokensTextDoneEDone(['Resposta completa.'], { mode: 'CLINICAL_REASONING' }));
    streamQueryMock.mockImplementation(() => stream.gerador());
    renderComProvedores(<App />);

    await enviar('caso');
    await waitFor(() => expect(screen.getByTestId('assistant-message')).toHaveTextContent('Resposta completa.'));

    definirViewport(VIEWPORT_CELULAR);
    await waitFor(() => expect(casca()).toBe('mobile'));
    await act(async () => { stream.liberar(); });

    await waitFor(() => expect(screen.getByTestId('assistant-message')).toHaveTextContent(/racioc/i));
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
    expect(streamQueryMock).toHaveBeenCalledTimes(1);
  });

  it('o que o médico estava digitando sobrevive à rotação', async () => {
    renderComProvedores(<App />);
    const user = userEvent.setup();
    await user.type(await screen.findByPlaceholderText(/digite sua pergunta/i), 'paciente 82 anos');

    definirViewport(VIEWPORT_CELULAR);
    await waitFor(() => expect(casca()).toBe('mobile'));

    expect(await screen.findByPlaceholderText(/digite sua pergunta/i)).toHaveValue('paciente 82 anos');
  });

  it('deitar o celular não devolve o desktop', async () => {
    renderComProvedores(<App />);
    definirViewport(VIEWPORT_CELULAR);
    await waitFor(() => expect(casca()).toBe('mobile'));

    definirViewport(VIEWPORT_CELULAR_DEITADO);
    await act(async () => {});
    expect(casca()).toBe('mobile');
  });

  it('com a flag desligada, o celular continua na casca de desktop (como hoje)', async () => {
    vi.stubEnv('VITE_SHELL_MOVEL', 'off');
    reiniciarLayout();
    renderComProvedores(<App />);
    await screen.findByPlaceholderText(/digite sua pergunta/i);

    definirViewport(VIEWPORT_CELULAR);
    await act(async () => {});
    expect(casca()).toBe('desktop');
  });
});
