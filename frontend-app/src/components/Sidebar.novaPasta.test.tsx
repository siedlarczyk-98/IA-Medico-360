/**
 * Acesso à criação de pasta na sidebar.
 *
 * O bug de usabilidade que isto trava: antes havia DOIS caminhos, e o melhor
 * deles desaparecia com o uso. Sem nenhuma pasta, um botão largo tracejado
 * convidava a criar a primeira; assim que ela existia, o botão sumia e sobrava
 * um "+" de 11px no cabeçalho "PASTAS". A ação encolhia justamente para quem
 * já tinha demonstrado que usa o recurso.
 *
 * Agora é um botão só, largo, sempre presente, logo abaixo de "Nova consulta".
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Sidebar, SIDEBAR_PINNED_KEY } from './Sidebar';
import { renderComProvedores } from '../test/utils';

vi.mock('../lib/auth', () => ({
  sessaoExpirou: vi.fn(), conferirSessao: vi.fn(), consumirRetomada: () => null,
  logout: vi.fn(),
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  getToken: () => 'token-de-teste',
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  setToken: vi.fn(),
  clearToken: vi.fn(),
}));

vi.mock('../api/auth', () => ({
  getMe: vi.fn(async () => ({ id: 'user-1', email: 'medico@teste.com', name: 'Dra. Teste' })),
}));

vi.mock('../api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(async () => ({ id: 'c1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
}));

const listFolders = vi.fn(async () => [] as unknown[]);
const createFolder = vi.fn();

vi.mock('../api/folders', () => ({
  listFolders: (...args: unknown[]) => listFolders(...(args as [])),
  createFolder: (...args: unknown[]) => createFolder(...(args as [])),
  renameFolder: vi.fn(), updateFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
  MAX_CHARS_EVOLUCAO: 8000,
}));

vi.mock('../api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: false, usage_percentage: null, week_reset_at: null })),
}));

const PASTA = {
  id: 'f1',
  name: 'Paciente Jorge',
  folder_kind: 'clinical',
  clinical_context: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderSidebarAberta(onNew: () => void = vi.fn()) {
  Object.defineProperty(window, 'innerWidth', { value: 1280, writable: true, configurable: true });
  // No desktop o painel só fica visível se estiver FIXADO (ou sob hover); o
  // prop `open` governa apenas o mobile.
  localStorage.setItem(SIDEBAR_PINNED_KEY, '1');
  return renderComProvedores(
    <Sidebar onNew={onNew} onSelect={vi.fn()} open onToggle={vi.fn()} />,
  );
}

/** Preenche o nome no modal e confirma. */
async function criarPasta(user: ReturnType<typeof userEvent.setup>, nome: string) {
  await user.click(await screen.findByRole('button', { name: /nova pasta/i }));
  const modal = screen.getByRole('dialog', { name: /nova pasta/i });
  await user.type(within(modal).getByRole('textbox', { name: /nome/i }), nome);
  await user.click(within(modal).getByRole('button', { name: /crie|criar|salvar/i }));
}

beforeEach(() => {
  listFolders.mockResolvedValue([]);
  createFolder.mockResolvedValue(PASTA);
});

describe('Botão de nova pasta', () => {
  it('aparece quando ainda não há nenhuma pasta', async () => {
    renderSidebarAberta();

    expect(await screen.findByRole('button', { name: /nova pasta/i })).toBeInTheDocument();
  });

  it('CONTINUA aparecendo depois que já existem pastas', async () => {
    // O ponto do arquivo: antes, o botão largo era substituído por um "+"
    // minúsculo assim que a primeira pasta existia.
    listFolders.mockResolvedValue([PASTA]);
    renderSidebarAberta();

    expect(await screen.findByText('Paciente Jorge')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /nova pasta/i })).toBeInTheDocument();
  });

  it('há um único caminho para criar pasta, não dois', async () => {
    listFolders.mockResolvedValue([PASTA]);
    renderSidebarAberta();

    await screen.findByText('Paciente Jorge');

    expect(screen.getAllByRole('button', { name: /nova pasta/i })).toHaveLength(1);
  });

  it('abre o modal de criação', async () => {
    const user = userEvent.setup();
    renderSidebarAberta();

    await user.click(await screen.findByRole('button', { name: /nova pasta/i }));

    const modal = screen.getByRole('dialog', { name: /nova pasta/i });
    expect(within(modal).getByText('Esta pasta é sobre um paciente?')).toBeInTheDocument();
  });
});


describe('Criar pasta leva para dentro dela', () => {
  it('aponta a próxima conversa para a pasta recém-criada', async () => {
    // O comportamento que isto trava: antes, a `Folder` devolvida pelo POST era
    // descartada — a mutation só invalidava a lista. Quem criava "Paciente
    // Jorge" e digitava em seguida via a conversa nascer na RAIZ.
    //
    // Não é só arrumação: a pasta injeta a evolução do paciente em toda
    // mensagem, então nascer fora dela é perder a evolução sem sinal na tela.
    const user = userEvent.setup();
    const onNew = vi.fn();
    renderSidebarAberta(onNew);

    await criarPasta(user, 'Paciente Jorge');

    await vi.waitFor(() => {
      expect(onNew).toHaveBeenCalledWith(PASTA.id, PASTA.name);
    });
  });

  it('usa o id REAL da resposta, nunca o otimista', async () => {
    // O update otimista insere um id `optimistic-<timestamp>`, que não é UUID:
    // mandá-lo como `folder_id` faria a API recusar o envio. Só o id que volta
    // do POST serve.
    const user = userEvent.setup();
    const onNew = vi.fn();
    renderSidebarAberta(onNew);

    await criarPasta(user, 'Paciente Jorge');

    await vi.waitFor(() => expect(onNew).toHaveBeenCalled());
    const [idUsado] = onNew.mock.calls[0];
    expect(idUsado).toBe('f1');
    expect(String(idUsado)).not.toMatch(/^optimistic-/);
  });

  it('não entra em pasta nenhuma se a criação falhar', async () => {
    // Sem isto, um POST que falha ainda apontaria a conversa para uma pasta que
    // não existe — e o envio seguinte quebraria no backend.
    const user = userEvent.setup();
    const onNew = vi.fn();
    createFolder.mockRejectedValue(new Error('500'));
    renderSidebarAberta(onNew);

    await criarPasta(user, 'Paciente Jorge');

    await vi.waitFor(() => expect(createFolder).toHaveBeenCalled());
    expect(onNew).not.toHaveBeenCalled();
  });
});
