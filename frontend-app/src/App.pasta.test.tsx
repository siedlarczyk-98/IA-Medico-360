/**
 * Aviso de contexto cruzado entre conversas da mesma pasta (Fase 6 / item 8).
 *
 * A recuperação acontece no backend. O que a interface precisa garantir é
 * TRANSPARÊNCIA: uma resposta pode trazer material de outra conversa da mesma
 * pasta, possivelmente de outro paciente, e o médico tem que saber disso antes
 * de ler a resposta — não depois.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';
import { renderComProvedores, streamEmLote, tokensEDone } from './test/utils';
import { streamQuery } from './api/orquestrador';
import { getConversation, listConversations } from './api/conversations';

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

const CONVERSA = {
  id: 'c1',
  title: 'Acompanhamento do caso',
  feature: 'ORQUESTRADOR',
  messages: [
    { role: 'user', content: 'como evoluiu?' },
    { role: 'assistant', content: 'evoluiu bem', mode: 'CLINICAL_REASONING' },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(streamQuery).mockImplementation(() => streamEmLote(tokensEDone(['ok'])));
  // `folder_id: null` no RESUMO de propósito: a sidebar agrupa por pasta e uma
  // conversa apontando para pasta ausente da lista não renderiza. O que está
  // sob teste é o aviso, que vem do DETALHE da conversa — não o agrupamento.
  vi.mocked(listConversations).mockResolvedValue([
    { id: 'c1', title: 'Acompanhamento do caso', feature: 'ORQUESTRADOR', folder_id: null, updated_at: '2026-08-27T10:00:00Z' },
  ] as never);
  localStorage.setItem('m360_sidebar_pinned', '1');
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
});

describe('aviso de contexto de pasta', () => {
  it('avisa quando a conversa aberta está numa pasta', async () => {
    vi.mocked(getConversation).mockResolvedValue({
      ...CONVERSA, folder_id: 'f1', folder_name: 'Paciente Julia',
    } as never);

    const user = userEvent.setup();
    renderComProvedores(<App />);
    await user.click(await screen.findByText('Acompanhamento do caso'));

    await waitFor(() => {
      expect(screen.getByText(/pode usar outras conversas da pasta/i)).toBeInTheDocument();
    });
    expect(screen.getByText('Paciente Julia')).toBeInTheDocument();
  });

  it('não avisa quando a conversa está fora de pasta', async () => {
    // Avisar sempre treinaria o médico a ignorar o aviso.
    vi.mocked(getConversation).mockResolvedValue({
      ...CONVERSA, folder_id: null, folder_name: null,
    } as never);

    const user = userEvent.setup();
    renderComProvedores(<App />);
    await user.click(await screen.findByText('Acompanhamento do caso'));

    await waitFor(() => {
      expect(screen.getByText('evoluiu bem')).toBeInTheDocument();
    });
    expect(screen.queryByText(/pode usar outras conversas da pasta/i)).not.toBeInTheDocument();
  });
});
