/**
 * Item 4: app abre com a barra colapsada; hover expande; clique fixa.
 *
 * Estados envolvidos: `pinned` (persistido, por clique) e `hovering`
 * (efêmero). A barra abre quando qualquer um é verdadeiro — e só o clique
 * sobrevive ao mouse sair.
 */
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Sidebar, SIDEBAR_PINNED_KEY } from './Sidebar';
import { renderComProvedores } from '../test/utils';

vi.mock('../lib/auth', () => ({
  logout: vi.fn(),
  getTokenPayload: () => ({ sub: 'user-1', exp: 9999999999 }),
  getToken: () => 'token-de-teste',
  isAuthenticated: () => true,
  isTokenExpired: () => false,
  setToken: vi.fn(),
  clearToken: vi.fn(),
}));

vi.mock('../api/auth', () => ({
  getMe: vi.fn(async () => ({
    id: 'user-1', name: 'Ana Souza', email: 'ana@exemplo.com',
    role: 'medico', crm: null, crm_state: null, med_status: 'especialista',
    intercom_user_hash: null,
  })),
}));

vi.mock('../api/conversations', () => ({
  listConversations: vi.fn(async () => []),
  getConversation: vi.fn(async () => ({ id: 'c1', title: '', feature: 'ORQUESTRADOR', messages: [] })),
}));

vi.mock('../api/folders', () => ({
  listFolders: vi.fn(async () => []),
  createFolder: vi.fn(), renameFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
}));

vi.mock('../api/usage', () => ({
  getUserUsage: vi.fn(async () => ({ has_limit: false, usage_percentage: null, week_reset_at: null })),
}));

function definirLargura(px: number) {
  Object.defineProperty(window, 'innerWidth', { value: px, writable: true, configurable: true });
}

function renderSidebar() {
  return renderComProvedores(
    <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open={false} onToggle={vi.fn()} />,
  );
}

const trilho = () => screen.queryByTestId('sidebar-rail');
const painel = () => screen.queryByTestId('sidebar-panel');

beforeEach(() => {
  definirLargura(1280);
});

describe('Sidebar no desktop', () => {
  it('abre colapsada quando não há preferência salva', () => {
    renderSidebar();
    expect(trilho()).toBeInTheDocument();
    expect(painel()).not.toBeInTheDocument();
  });

  it('expande ao passar o mouse', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.hover(trilho()!);

    expect(painel()).toBeInTheDocument();
  });

  it('recolhe quando o mouse sai, se não estiver fixada', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();

    await user.hover(trilho()!);
    expect(painel()).toBeInTheDocument();

    await user.unhover(container.querySelector('[data-testid="sidebar-rail"]')!.parentElement!);

    expect(painel()).not.toBeInTheDocument();
  });

  it('o clique fixa a barra, e ela sobrevive ao mouse sair', async () => {
    const user = userEvent.setup();
    const { container } = renderSidebar();

    await user.hover(trilho()!);
    await user.click(screen.getByTitle(/fixar barra lateral/i));

    expect(painel()).toBeInTheDocument();
    expect(trilho()).not.toBeInTheDocument();

    // Mouse longe da barra: fixada, ela permanece aberta.
    await user.unhover(container.firstChild as Element);
    expect(painel()).toBeInTheDocument();
  });

  it('persiste a preferência de fixada', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.hover(trilho()!);
    await user.click(screen.getByTitle(/fixar barra lateral/i));

    expect(localStorage.getItem(SIDEBAR_PINNED_KEY)).toBe('1');
  });

  it('abre já fixada quando a preferência está salva', () => {
    localStorage.setItem(SIDEBAR_PINNED_KEY, '1');
    renderSidebar();

    expect(painel()).toBeInTheDocument();
    expect(trilho()).not.toBeInTheDocument();
  });

  it('o clique em recolher desfixa e volta ao trilho', async () => {
    localStorage.setItem(SIDEBAR_PINNED_KEY, '1');
    const user = userEvent.setup();
    renderSidebar();

    await user.click(screen.getByTitle(/recolher barra lateral/i));

    expect(trilho()).toBeInTheDocument();
    expect(painel()).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_PINNED_KEY)).toBe('0');
  });

  it('não herda a chave antiga sidebarCollapsed', () => {
    // '1' na chave antiga significava COLAPSADA. Se fosse reaproveitada com o
    // novo sentido, este usuário abriria FIXADA — o oposto do que tinha.
    localStorage.setItem('sidebarCollapsed', '1');
    renderSidebar();

    expect(trilho()).toBeInTheDocument();
    expect(painel()).not.toBeInTheDocument();
  });
});

describe('Sidebar no mobile', () => {
  beforeEach(() => {
    definirLargura(390);
  });

  it('não renderiza nada quando fechada', () => {
    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open={false} onToggle={vi.fn()} />,
    );
    expect(trilho()).not.toBeInTheDocument();
    expect(painel()).not.toBeInTheDocument();
  });

  it('abre por prop, e não por hover', async () => {
    const user = userEvent.setup();
    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open onToggle={vi.fn()} />,
    );

    expect(painel()).toBeInTheDocument();
    // Não existe trilho no mobile — logo, nada a sobrepor por hover.
    expect(trilho()).not.toBeInTheDocument();

    await user.hover(painel()!);
    expect(painel()).toBeInTheDocument();
  });

  it('não mostra o botão de fixar/recolher do desktop', () => {
    renderComProvedores(
      <Sidebar onNew={vi.fn()} onSelect={vi.fn()} open onToggle={vi.fn()} />,
    );
    expect(screen.queryByTitle(/recolher barra lateral/i)).not.toBeInTheDocument();
    expect(within(painel()!).queryByTitle(/fixar barra lateral/i)).not.toBeInTheDocument();
  });
});
