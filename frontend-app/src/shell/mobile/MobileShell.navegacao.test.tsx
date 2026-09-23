/**
 * Histórico, Pastas e o botão voltar, na casca mobile.
 *
 * Dentro da Waid a navegação é uma gaveta; fora, abas. Nos dois a Consulta não
 * é desmontada, e voltar fecha a camada de cima. Estes testes travam os
 * caminhos que o médico faz com o polegar: achar a conversa, mover para uma
 * pasta, abrir uma pasta, e sair de tudo isso sem perder a resposta que estava
 * chegando.
 */
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../../App';
import { renderComProvedores } from '../../test/utils';
import { definirViewport, VIEWPORT_CELULAR } from '../../test/viewport';
import { reiniciarLayout } from '../layout';
import { streamQuery, type StreamEvent } from '../../api/orquestrador';
import { getConversation } from '../../api/conversations';
import { bulkMoveConversations, createFolder, moveConversation } from '../../api/folders';

const agora = new Date().toISOString();
const anteontem = new Date(Date.now() - 2 * 86400000).toISOString();

vi.mock('../../lib/auth', () => ({
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(),
  clearToken: vi.fn(),
  logout: vi.fn(),
}));

vi.mock('../../api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com',
    role: 'medico', crm: null, crm_state: null, med_status: 'especialista',
    intercom_user_hash: null,
  })),
}));

vi.mock('../../api/conversations', () => ({
  listConversations: vi.fn(async () => [
    { id: 'c1', title: 'DOAC em FA com ClCr 25', feature: 'ORQUESTRADOR', folder_id: 'p1', updated_at: agora, created_at: agora },
    { id: 'c2', title: 'Febre sem foco — lactente', feature: 'ORQUESTRADOR', folder_id: null, updated_at: agora, created_at: agora },
    { id: 'c3', title: 'Hiponatremia em idoso', feature: 'ORQUESTRADOR', folder_id: null, updated_at: anteontem, created_at: anteontem },
  ]),
  getConversation: vi.fn(async (id: string) => ({
    id, title: 'Febre sem foco — lactente', feature: 'ORQUESTRADOR', folder_id: null, folder_name: null,
    messages: [{ role: 'user', content: 'Lactente 5 meses, febre 39 °C' }, { role: 'assistant', content: 'Urina tipo 1 e urocultura.' }],
  })),
}));

vi.mock('../../api/folders', () => ({
  listFolders: vi.fn(async () => [
    { id: 'p1', name: 'Cardiologia', folder_kind: 'general', clinical_context: 'Revisão de arritmias', created_at: agora, updated_at: agora },
    { id: 'p2', name: 'Plantão UPA', folder_kind: 'general', clinical_context: null, created_at: agora, updated_at: agora },
  ]),
  createFolder: vi.fn(async (name: string) => ({ id: 'p9', name, folder_kind: 'clinical', clinical_context: null, created_at: agora, updated_at: agora })),
  renameFolder: vi.fn(), updateFolder: vi.fn(), deleteFolder: vi.fn(async () => {}),
  moveConversation: vi.fn(async () => {}), bulkMoveConversations: vi.fn(async () => {}),
  MAX_CHARS_EVOLUCAO: 8000,
}));

vi.mock('../../api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: true, usage_percentage: 68, week_reset_at: null })),
}));

vi.mock('../../api/orquestrador', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/orquestrador')>()),
  streamQuery: vi.fn(),
  queryOrquestrador: vi.fn(),
}));

async function abrirNoCelular({ dentroDaWaid = false } = {}) {
  if (dentroDaWaid) (window as { ReactNativeWebView?: unknown }).ReactNativeWebView = {};
  definirViewport(VIEWPORT_CELULAR);
  reiniciarLayout();
  renderComProvedores(<App />);
  await waitFor(() => expect(document.querySelector('[data-casca="mobile"]')).not.toBeNull());
  return userEvent.setup();
}

const aba = (nome: RegExp) => within(screen.getByRole('navigation', { name: 'Navegação' })).getByRole('button', { name: nome });

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubEnv('VITE_SHELL_MOVEL', 'on');
  window.history.replaceState(null, '', '/');
});

afterEach(() => {
  vi.unstubAllEnvs();
  delete (window as { ReactNativeWebView?: unknown }).ReactNativeWebView;
});

describe('fora da Waid: abas', () => {
  it('Histórico lista TODAS as conversas por data — as de pasta também, com o nome dela', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/histórico/i));

    const tela = screen.getByRole('region', { name: 'Histórico' });
    const hoje = within(tela).getByRole('region', { name: 'Hoje' });
    expect(within(hoje).getByText('DOAC em FA com ClCr 25')).toBeInTheDocument();
    expect(within(hoje).getByText('Cardiologia')).toBeInTheDocument();
    expect(within(hoje).getByText('Febre sem foco — lactente')).toBeInTheDocument();
    expect(within(tela).getByRole('region', { name: 'Últimos 7 dias' })).toHaveTextContent('Hiponatremia em idoso');
  });

  it('tocar numa conversa abre ela e volta para a Consulta', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/histórico/i));
    await user.click(await screen.findByText('Febre sem foco — lactente'));

    expect(getConversation).toHaveBeenCalledWith('c2');
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Histórico' })).toBeNull());
    expect(await screen.findByText('Urina tipo 1 e urocultura.')).toBeInTheDocument();
  });

  it('voltar do Android fecha o Histórico e mantém a Consulta', async () => {
    const user = await abrirNoCelular();
    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'rascunho');
    await user.click(aba(/histórico/i));
    expect(screen.getByRole('region', { name: 'Histórico' })).toBeInTheDocument();

    act(() => window.history.back());

    await waitFor(() => expect(screen.queryByRole('region', { name: 'Histórico' })).toBeNull());
    expect(screen.getByPlaceholderText(/digite sua pergunta/i)).toHaveValue('rascunho');
  });

  it('a resposta segue chegando com o Histórico aberto, e a pílula leva de volta', async () => {
    let liberar!: () => void;
    const espera = new Promise<void>(r => { liberar = r; });
    vi.mocked(streamQuery).mockImplementation(() => (async function* (): AsyncGenerator<StreamEvent> {
      yield { type: 'token', text: 'Apixabana ' };
      await espera;
      yield { type: 'token', text: '2,5 mg 12/12h.' };
      yield { type: 'text_done', conversation_id: 'nova', mode: 'CLINICAL_REASONING', model_used: 'x', is_fallback: false };
      yield { type: 'done', conversation_id: 'nova', mode: 'CLINICAL_REASONING', model_used: 'x' };
    })());
    const user = await abrirNoCelular();
    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'DOAC');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    await screen.findByText(/Apixabana/);

    await user.click(aba(/histórico/i));
    // Na aba Consulta, o ponto verde avisa que ainda está respondendo.
    expect(aba(/consulta/i)).toHaveAccessibleName(/respondendo/i);
    expect(await screen.findByRole('button', { name: /^respondendo:/i })).toBeInTheDocument();

    // A resposta termina com o médico ainda no Histórico...
    await act(async () => { liberar(); });
    await waitFor(() => expect(screen.queryByRole('button', { name: /^respondendo:/i })).toBeNull());

    // ...e está inteira quando ele volta.
    await user.click(aba(/consulta/i));
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Histórico' })).toBeNull());
    expect(screen.getByTestId('assistant-message')).toHaveTextContent('Apixabana 2,5 mg 12/12h.');
    expect(screen.getAllByTestId('assistant-message')).toHaveLength(1);
  });

  it('a pílula "Respondendo" leva de volta à Consulta', async () => {
    vi.mocked(streamQuery).mockImplementation((_p, sinal) => (async function* (): AsyncGenerator<StreamEvent> {
      yield { type: 'token', text: 'Apixabana ' };
      await new Promise((_r, rej) => sinal?.addEventListener('abort', () =>
        rej(Object.assign(new Error('abort'), { name: 'AbortError' }))));
    })());
    const user = await abrirNoCelular();
    await user.type(screen.getByPlaceholderText(/digite sua pergunta/i), 'DOAC');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    await screen.findByText(/Apixabana/);
    await user.click(aba(/histórico/i));

    await user.click(await screen.findByRole('button', { name: /^respondendo:/i }));

    await waitFor(() => expect(screen.queryByRole('region', { name: 'Histórico' })).toBeNull());
    // Voltar para ver não interrompe: ainda está respondendo.
    expect(screen.getByRole('button', { name: 'Parar' })).toBeInTheDocument();
  });

  it('mover pela folha de ações: "…" → Mover para pasta → destino', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/histórico/i));
    await user.click(await screen.findByRole('button', { name: 'Ações: Febre sem foco — lactente' }));
    await user.click(screen.getByRole('button', { name: /mover para pasta/i }));

    const folha = screen.getByRole('dialog', { name: /mover conversa/i });
    await user.click(within(folha).getByRole('radio', { name: /plantão upa/i }));
    await user.click(within(folha).getByRole('button', { name: /mover para plantão upa/i }));

    expect(moveConversation).toHaveBeenCalledWith('c2', 'p2');
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    // Continua no Histórico: mover não é navegar.
    expect(screen.getByRole('region', { name: 'Histórico' })).toBeInTheDocument();
  });

  it('seleção: marcar duas e mover as duas de uma vez; depois sai da seleção', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/histórico/i));
    await user.click(await screen.findByRole('button', { name: 'Ações: Febre sem foco — lactente' }));
    await user.click(screen.getByRole('button', { name: /selecionar/i }));

    expect(await screen.findByText('1 selecionada')).toBeInTheDocument();
    await user.click(screen.getByText('Hiponatremia em idoso'));
    expect(screen.getByText('2 selecionadas')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /mover 2 para/i }));
    const folha = screen.getByRole('dialog', { name: /mover 2 conversas/i });
    await user.click(within(folha).getByRole('radio', { name: /cardiologia/i }));
    await user.click(within(folha).getByRole('button', { name: /mover para cardiologia/i }));

    expect(bulkMoveConversations).toHaveBeenCalledWith(['c2', 'c3'], 'p1');
    await waitFor(() => expect(screen.queryByText(/selecionadas?$/)).toBeNull());
  });

  it('Pastas: abrir uma pasta e começar uma consulta dentro dela', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/pastas/i));
    await user.click(await screen.findByText('Cardiologia'));

    expect(await screen.findByText('1 conversa')).toBeInTheDocument();
    expect(screen.getByText(/revisão de arritmias/i)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /nova consulta nesta pasta/i }));

    await waitFor(() => expect(screen.queryByRole('region', { name: 'Pastas' })).toBeNull());
    expect(screen.getByText(/nova consulta em/i)).toHaveTextContent('Cardiologia');
  });

  it('trocar de aba com uma pasta aberta mostra a aba nova, não a pasta', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/pastas/i));
    await user.click(await screen.findByText('Cardiologia'));
    await screen.findByText('1 conversa');

    await user.click(aba(/histórico/i));

    await waitFor(() => expect(screen.getByRole('region', { name: 'Histórico' })).toBeInTheDocument());
    expect(screen.queryByText('1 conversa')).toBeNull();
    // E o voltar agora sai do Histórico (a pasta não ficou esquecida na pilha).
    act(() => window.history.back());
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Histórico' })).toBeNull());
  });

  it('criar pasta leva para uma consulta nova dentro dela', async () => {
    const user = await abrirNoCelular();
    await user.click(aba(/pastas/i));
    await user.click(await screen.findByRole('button', { name: /nova pasta/i }));

    const folha = screen.getByRole('dialog', { name: 'Nova pasta' });
    await user.type(within(folha).getByPlaceholderText(/paciente jorge/i), 'Paciente Jorge');
    await user.click(within(folha).getByRole('button', { name: 'Criar pasta' }));

    expect(createFolder).toHaveBeenCalledWith('Paciente Jorge', '', 'clinical');
    await waitFor(() => expect(screen.queryByRole('region', { name: 'Pastas' })).toBeNull());
    expect(await screen.findByText(/nova consulta em/i)).toHaveTextContent('Paciente Jorge');
  });
});

describe('dentro da Waid: gaveta', () => {
  it('não tem barra de abas; o ☰ abre a gaveta com histórico, pastas e uso', async () => {
    const user = await abrirNoCelular({ dentroDaWaid: true });
    expect(screen.queryByRole('navigation', { name: 'Navegação' })).toBeNull();

    await user.click(screen.getByRole('button', { name: /histórico, pastas e conta/i }));
    const gaveta = screen.getByRole('complementary', { name: /histórico e pastas/i });
    expect(within(gaveta).getByText('DOAC em FA com ClCr 25')).toBeInTheDocument();
    expect(await within(gaveta).findByText('68% do limite semanal')).toBeInTheDocument();

    await user.click(within(gaveta).getByRole('tab', { name: 'Pastas' }));
    expect(within(gaveta).getByText('Plantão UPA')).toBeInTheDocument();
  });

  it('voltar fecha primeiro a folha, depois a gaveta', async () => {
    const user = await abrirNoCelular({ dentroDaWaid: true });
    await user.click(screen.getByRole('button', { name: /histórico, pastas e conta/i }));
    await user.click(screen.getByRole('button', { name: 'Ações: Febre sem foco — lactente' }));
    expect(screen.getByRole('dialog', { name: 'Ações' })).toBeInTheDocument();

    act(() => window.history.back());
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(screen.getByRole('complementary', { name: /histórico e pastas/i })).toBeInTheDocument();

    act(() => window.history.back());
    await waitFor(() => expect(screen.queryByRole('complementary', { name: /histórico e pastas/i })).toBeNull());
  });

  it('a folha aberta de dentro da gaveta cobre a tela inteira, não só a gaveta', async () => {
    const user = await abrirNoCelular({ dentroDaWaid: true });
    await user.click(screen.getByRole('button', { name: /histórico, pastas e conta/i }));
    await user.click(screen.getByRole('button', { name: 'Ações: Febre sem foco — lactente' }));

    const folha = screen.getByRole('dialog', { name: 'Ações' });
    expect(folha.parentElement).toBe(document.querySelector('.shell-movel'));
  });
});
