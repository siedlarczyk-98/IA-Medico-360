/**
 * Item 7: o Agregador sai da interface e o produto passa a ser o Orquestrador.
 *
 * A remoção é só de superfície — backend, rotas `/agregador/*` e testes de
 * autorização continuam intactos, e as conversas antigas seguem no banco.
 * Estes testes travam a parte visível: nada de Agregador na tela, e conversas
 * antigas dele fora da lista (senão abririam uma tela que não existe mais).
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { Sidebar } from './components/Sidebar';
import { renderComProvedores, streamEmLote, tokensEDone } from './test/utils';
import { streamQuery } from './api/orquestrador';
import { listConversations } from './api/conversations';
import { APP_MODES } from './lib/appModes';

vi.mock('./lib/auth', () => ({
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  getToken: () => 'token-de-teste',
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  setToken: vi.fn(), clearToken: vi.fn(), logout: vi.fn(),
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
  getConversation: vi.fn(async () => ({ id: 'c1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(streamQuery).mockImplementation(() => streamEmLote(tokensEDone(['ok'])));
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
});

describe('Agregador oculto na interface', () => {
  it('não aparece entre os modos disponíveis', () => {
    expect(APP_MODES.map(m => m.key)).toEqual(['orquestrador']);
  });

  it('a tela principal não menciona o Agregador', async () => {
    renderComProvedores(<App />);

    // Espera a tela montar antes de afirmar ausência — senão o teste passaria
    // apenas por estar olhando cedo demais.
    await screen.findByPlaceholderText(/digite sua pergunta/i);

    expect(screen.queryByText(/agregador/i)).not.toBeInTheDocument();
  });

  it('não há seletor de modelos nem toggle de busca web', async () => {
    renderComProvedores(<App />);
    await screen.findByPlaceholderText(/digite sua pergunta/i);

    expect(screen.queryByText(/^web$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/selecione um modelo/i)).not.toBeInTheDocument();
  });

  it('vai direto ao chat, sem tela de escolha de modo', async () => {
    // A ModeIntro existia para escolher entre os dois modos. Com um só, ela
    // seria uma tela de escolha única entre o app e ele mesmo.
    renderComProvedores(<App />);

    expect(await screen.findByPlaceholderText(/digite sua pergunta/i)).toBeInTheDocument();
  });
});

describe('conversas antigas do Agregador', () => {
  const conversas = [
    { id: 'c-orq', title: 'Caso de cefaleia', feature: 'ORQUESTRADOR', folder_id: null, updated_at: '2026-08-20T10:00:00Z' },
    { id: 'c-agr', title: 'Comparação de modelos', feature: 'AGREGADOR', folder_id: null, updated_at: '2026-08-21T10:00:00Z' },
  ];

  it('ficam fora da lista da sidebar', async () => {
    vi.mocked(listConversations).mockResolvedValue(conversas as never);
    localStorage.setItem('m360_sidebar_pinned', '1');

    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open={false} onToggle={vi.fn()} />,
    );

    await waitFor(() => {
      expect(screen.getByText('Caso de cefaleia')).toBeInTheDocument();
    });
    expect(screen.queryByText('Comparação de modelos')).not.toBeInTheDocument();
  });

  it('a conversa do orquestrador continua selecionável', async () => {
    vi.mocked(listConversations).mockResolvedValue(conversas as never);
    localStorage.setItem('m360_sidebar_pinned', '1');
    const onSelect = vi.fn();
    const user = userEvent.setup();

    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={onSelect} open={false} onToggle={vi.fn()} />,
    );

    await user.click(await screen.findByText('Caso de cefaleia'));

    expect(onSelect).toHaveBeenCalledWith('c-orq');
  });

  it('some da lista mesmo sendo a conversa mais recente', async () => {
    // A do agregador tem updated_at mais novo: se o filtro dependesse da
    // ordenação, ela apareceria no topo em vez de sumir.
    vi.mocked(listConversations).mockResolvedValue(conversas as never);
    localStorage.setItem('m360_sidebar_pinned', '1');

    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open={false} onToggle={vi.fn()} />,
    );

    await screen.findByText('Caso de cefaleia');
    expect(screen.queryByText('Comparação de modelos')).not.toBeInTheDocument();
  });
});
