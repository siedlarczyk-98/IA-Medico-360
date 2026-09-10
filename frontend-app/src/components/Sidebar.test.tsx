/**
 * Item 4: app abre com a barra colapsada; hover expande; clique fixa.
 *
 * Estados envolvidos: `pinned` (persistido, por clique) e `hovering`
 * (efêmero). A barra abre quando qualquer um é verdadeiro — e só o clique
 * sobrevive ao mouse sair.
 */
import { fireEvent, screen, within } from '@testing-library/react';
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
  createFolder: vi.fn(), renameFolder: vi.fn(), updateFolder: vi.fn(), deleteFolder: vi.fn(),
  moveConversation: vi.fn(), bulkMoveConversations: vi.fn(),
  MAX_CHARS_EVOLUCAO: 8000,
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
    fireEvent.mouseDown(within(painel()!).getByRole('button', { name: /fixar barra lateral aberta/i }));

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
    fireEvent.mouseDown(within(painel()!).getByRole('button', { name: /fixar barra lateral aberta/i }));

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

    // Fixada não há wrapper de hover, mas o handler é `onMouseDown`.
    fireEvent.mouseDown(screen.getByTitle(/recolher barra lateral/i));

    expect(trilho()).toBeInTheDocument();
    expect(painel()).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_PINNED_KEY)).toBe('0');
  });

  // NOTA SOBRE `fireEvent` vs `userEvent` NESTE ARQUIVO
  //
  // O jsdom NÃO faz layout: todo elemento mede 0x0 e fica na posição (0,0).
  // `userEvent.click` simula o percurso do ponteiro e, sem geometria, conclui
  // que o mouse saiu do wrapper — dispara `mouseleave`, o painel desmonta, e o
  // clique cai no vazio. Isso é artefato do simulador, não do produto.
  //
  // Onde o alvo é o HANDLER (fixou? persistiu?), estes testes usam `fireEvent`,
  // que aciona o evento direto no elemento. O comportamento de ponteiro real —
  // se o mouse sai do wrapper ao entrar no painel — depende de geometria e só
  // pode ser verificado no navegador.

  // ── O clique no painel sobreposto ──────────────────────────────────────
  //
  // O caso que escapou de TODOS os testes anteriores, e que quebrou na mão do
  // usuário: com a barra não fixada, o hover abre o painel de 260px SOBRE o
  // trilho de 56px (zIndex 150). O botão de fixar do trilho fica embaixo e não
  // recebe clique — o único alcançável é o do topo do painel.
  //
  // Enquanto esse botão dizia sempre "recolher", clicar nele DESFIXAVA. O
  // relato foi "se eu clico nessa merda ele não fixa".
  //
  // Os testes antigos passavam porque `getByTitle(/fixar/i)` encontra o botão
  // do trilho no DOM — jsdom não tem noção de empilhamento visual. Por isso
  // estes aqui vão pelo painel explicitamente.

  it('o botão do painel aberto por hover FIXA, e não o contrário', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.hover(trilho()!);

    // O botão alcançável pelo mouse é o do painel sobreposto, não o do trilho.
    const botaoDoPainel = within(painel()!).getByRole('button', {
      name: /fixar barra lateral aberta/i,
    });
    fireEvent.mouseDown(botaoDoPainel);

    // Fixou de verdade: o trilho sai de cena e a preferência persiste.
    expect(painel()).toBeInTheDocument();
    expect(trilho()).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_PINNED_KEY)).toBe('1');
  });

  it('o painel do hover não oferece "recolher" — não há o que recolher', async () => {
    const user = userEvent.setup();
    renderSidebar();

    await user.hover(trilho()!);

    expect(
      within(painel()!).queryByRole('button', { name: /recolher barra lateral/i }),
    ).not.toBeInTheDocument();
  });

  it('fixada, o mesmo canto oferece o caminho de volta', async () => {
    localStorage.setItem(SIDEBAR_PINNED_KEY, '1');
    const user = userEvent.setup();
    renderSidebar();

    const botao = within(painel()!).getByRole('button', { name: /recolher barra lateral/i });
    expect(botao).toHaveAttribute('aria-pressed', 'true');

    fireEvent.mouseDown(botao);

    expect(trilho()).toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_PINNED_KEY)).toBe('0');
  });

  // ── Descobribilidade do botão de fixar ─────────────────────────────────
  //
  // Os testes acima provam que o clique FUNCIONA. Não provam que alguém acha o
  // botão — e foi exatamente aí que o recurso falhou na prática: um usuário que
  // conhece o produto relatou "não tá ficando aberta, só quando meu mouse tá em
  // cima", sem nunca ter visto a setinha de 14px que fixa a barra.
  //
  // O que estes testes travam é o alvo de clique e o rótulo acessível. Não
  // substituem olhar a tela, mas impedem a regressão silenciosa: encolher o
  // botão de novo passaria por todos os outros testes deste arquivo.

  it('o botão de fixar tem alvo de clique utilizável', async () => {
    const user = userEvent.setup();
    renderSidebar();
    await user.hover(trilho()!);

    const botao = within(trilho()!).getByRole('button', { name: /fixar barra lateral aberta/i });

    // 32px é o tamanho do botão de nova consulta, e o mínimo recomendado de
    // alvo de toque é 24px. A versão anterior era um ícone de 14px sem moldura.
    expect(botao.style.width).toBe('32px');
    expect(botao.style.height).toBe('32px');
    // Moldura visível: sem ela o ícone não se lê como botão.
    expect(botao.style.border).not.toBe('none');
    expect(botao.style.border).not.toBe('');
  });

  it('os dois botões do par têm rótulo acessível', async () => {
    const user = userEvent.setup();
    const { unmount } = renderSidebar();
    await user.hover(trilho()!);

    // Alcançável por leitor de tela e por teste, não só pelo `title`.
    // Os dois existem no DOM durante o hover (trilho embaixo, painel em cima).
    expect(within(trilho()!).getByRole('button', { name: /fixar barra lateral aberta/i })).toBeInTheDocument();
    expect(within(painel()!).getByRole('button', { name: /fixar barra lateral aberta/i })).toBeInTheDocument();
    unmount();

    localStorage.setItem(SIDEBAR_PINNED_KEY, '1');
    renderSidebar();
    expect(screen.getByRole('button', { name: /recolher barra lateral/i })).toBeInTheDocument();
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
