/**
 * O item de conversa na sidebar — quem INICIA o movimento entre pastas.
 *
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------
 * `FolderRow` e `DropZoneNoPasta` (cobertos em 2026-09-16) são o lado que
 * RECEBE a conversa. Este é o lado que a solta: o `draggable`, o menu "mover
 * para pasta" e a seleção múltipla que alimenta o mover-em-lote.
 *
 * Cobrir só um dos lados de um drag-and-drop dá falsa sensação de segurança —
 * e aqui o erro é caro: mover conversa entre pastas muda qual evolução de
 * paciente (`folders.clinical_context`) é injetada nas mensagens seguintes. Em
 * lote, um engano move dezenas de conversas de uma vez, sem confirmação e sem
 * desfazer.
 *
 * O que se afirma: a conversa certa é movida para a pasta certa, e clicar não
 * faz duas coisas ao mesmo tempo.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ConvItem } from './ConvItem';

const CONVERSA = {
  id: 'c1',
  title: 'Ajuste de metformina',
  feature: 'ORQUESTRADOR' as const,
  folder_id: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const PASTA_A = {
  id: 'fa', name: 'Paciente Jorge', folder_kind: 'clinical' as const,
  clinical_context: null, created_at: '', updated_at: '',
};
const PASTA_B = {
  id: 'fb', name: 'Paciente Maria', folder_kind: 'clinical' as const,
  clinical_context: null, created_at: '', updated_at: '',
};

function renderItem(props: Partial<React.ComponentProps<typeof ConvItem>> = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onMove: vi.fn(),
    onToggleSelect: vi.fn(),
    onDragStart: vi.fn(),
  };
  render(
    <ConvItem
      conv={CONVERSA}
      folders={[PASTA_A, PASTA_B]}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

const menu = () => screen.getByRole('button', { name: /opções de/i });
const titulo = () => screen.getByText('Ajuste de metformina');
const raiz = () => document.querySelector('[draggable]') as HTMLElement;

/**
 * O botão de menu só existe no DOM sob hover.
 *
 * `fireEvent.mouseEnter` na RAIZ arrastável, e não `user.hover` no título: o
 * `onMouseEnter` está no contêiner externo, e o hover simulado do
 * `user-event` não borbulha até ele de forma confiável no jsdom.
 */
async function abrirMenu(user: ReturnType<typeof userEvent.setup>) {
  fireEvent.mouseEnter(raiz());
  await user.click(menu());
}

describe('Selecionar a conversa', () => {
  it('clicar abre a conversa', async () => {
    const user = userEvent.setup();
    const { onSelect } = renderItem();

    await user.click(titulo());

    expect(onSelect).toHaveBeenCalledWith('c1');
  });

  it('em modo de seleção, clicar MARCA em vez de abrir', async () => {
    // Trocar as duas ações é o bug clássico: o médico marcando 20 conversas
    // para mover perderia a seleção ao clicar na 21ª.
    const user = userEvent.setup();
    const { onSelect, onToggleSelect } = renderItem({ selectionMode: true });

    await user.click(titulo());

    expect(onToggleSelect).toHaveBeenCalledWith('c1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('conversa sem título mostra um rótulo, não vazio', () => {
    renderItem({ conv: { ...CONVERSA, title: null } });
    expect(screen.getByText('Sem título')).toBeInTheDocument();
  });
});

describe('Arrastar', () => {
  it('avisa qual conversa começou a ser arrastada', () => {
    // O id que sai daqui é o que `FolderRow`/`DropZone` vão mover ao receber o
    // drop. Se vier errado, move a conversa errada.
    const { onDragStart } = renderItem();

    // O jsdom não popula `dataTransfer` em eventos sintéticos, e o handler
    // escreve `effectAllowed` nele antes de avisar quem arrastou — sem este
    // objeto, o próprio handler estoura.
    fireEvent.dragStart(raiz(), { dataTransfer: { effectAllowed: '' } });

    expect(onDragStart).toHaveBeenCalledWith('c1');
  });
});

describe('Mover por menu', () => {
  it('move para a pasta escolhida', async () => {
    const user = userEvent.setup();
    const { onMove } = renderItem();

    await abrirMenu(user);
    await user.click(screen.getByText('Mover para pasta'));
    await user.click(screen.getByText('Paciente Maria'));

    expect(onMove).toHaveBeenCalledWith('c1', 'fb');
  });

  it('o menu fecha depois de mover', async () => {
    // Menu aberto sobre a lista esconde as conversas seguintes.
    const user = userEvent.setup();
    renderItem();

    await abrirMenu(user);
    await user.click(screen.getByText('Mover para pasta'));
    await user.click(screen.getByText('Paciente Jorge'));

    expect(screen.queryByText('Escolher pasta')).toBeNull();
  });

  it('"remover da pasta" NÃO aparece quando a conversa está na raiz', async () => {
    // Oferecer a ação sem efeito confunde: o médico clica e nada muda.
    const user = userEvent.setup();
    renderItem();

    await abrirMenu(user);

    expect(screen.queryByText('Remover da pasta')).toBeNull();
  });

  it('"remover da pasta" aparece e move para a raiz quando está numa pasta', async () => {
    const user = userEvent.setup();
    const { onMove } = renderItem({ conv: { ...CONVERSA, folder_id: 'fa' } });

    await abrirMenu(user);
    await user.click(screen.getByText('Remover da pasta'));

    // `null` é a raiz — e é o que faz a evolução do paciente deixar de ser
    // injetada nas mensagens seguintes.
    expect(onMove).toHaveBeenCalledWith('c1', null);
  });

  it('marca a pasta atual na lista', async () => {
    // Sem a marca, o médico move para a pasta onde a conversa já está.
    const user = userEvent.setup();
    renderItem({ conv: { ...CONVERSA, folder_id: 'fa' } });

    await abrirMenu(user);
    await user.click(screen.getByText('Mover para pasta'));

    expect(screen.getByText(/✓\s*Paciente Jorge/)).toBeInTheDocument();
  });

  it('sem pastas, diz isso em vez de mostrar lista vazia', async () => {
    const user = userEvent.setup();
    renderItem({ folders: [] });

    await abrirMenu(user);
    await user.click(screen.getByText('Mover para pasta'));

    expect(screen.getByText('Nenhuma pasta criada')).toBeInTheDocument();
  });

  it('abrir o menu não abre a conversa', async () => {
    // Sem `stopPropagation`, clicar no menu carregaria a conversa por baixo.
    const user = userEvent.setup();
    const { onSelect } = renderItem();

    await abrirMenu(user);

    expect(onSelect).not.toHaveBeenCalled();
  });

  it('fecha ao clicar fora', async () => {
    const user = userEvent.setup();
    renderItem();

    await abrirMenu(user);
    expect(screen.getByText('Mover para pasta')).toBeInTheDocument();

    await user.click(document.body);

    expect(screen.queryByText('Mover para pasta')).toBeNull();
  });
});

describe('Em tela de toque', () => {
  // No celular não existe hover: o botão de opções nunca aparecia, e mover uma
  // conversa para uma pasta era impossível.
  function simularDispositivo(semHover: boolean) {
    vi.stubGlobal('matchMedia', (consulta: string) => ({
      matches: consulta === '(hover: none)' ? semHover : false,
      media: consulta, addEventListener: vi.fn(), removeEventListener: vi.fn(),
    }));
  }

  afterEach(() => vi.unstubAllGlobals());

  it('o menu de opções aparece SEM hover, e move a conversa', async () => {
    simularDispositivo(true);
    const user = userEvent.setup();
    const { onMove } = renderItem();

    await user.click(menu()); // nenhum mouseEnter antes
    await user.click(await screen.findByText(/mover para/i));
    await user.click(await screen.findByText(PASTA_A.name));

    expect(onMove).toHaveBeenCalledWith(CONVERSA.id, PASTA_A.id);
  });

  it('o alvo de toque tem tamanho de dedo', () => {
    // O valor vem de `--toque-min` (44px no dedo). O jsdom não resolve
    // variável CSS, então o que se confere é que o botão USA o token — e não um
    // número solto que alguém possa encolher sem ver a regra.
    simularDispositivo(true);
    renderItem();

    expect(menu().style.minWidth).toBe('var(--toque-min)');
    expect(menu().style.minHeight).toBe('var(--toque-min)');
  });

  it('com mouse o botão continua escondido até o hover', () => {
    simularDispositivo(false);
    renderItem();

    expect(screen.queryByRole('button', { name: /opções de/i })).not.toBeInTheDocument();
  });
});

describe('Renomear (2026-09-24)', () => {
  async function abrirRenomear(onRename = vi.fn()) {
    const user = userEvent.setup();
    renderItem({ onRename });
    await abrirMenu(user);
    await user.click(screen.getByRole('button', { name: 'Renomear' }));
    return { user, onRename, campo: screen.getByRole('textbox', { name: /novo título/i }) };
  }

  it('Enter salva o título novo, sem espaços sobrando', async () => {
    const { user, onRename, campo } = await abrirRenomear();

    await user.clear(campo);
    await user.type(campo, '  Metformina —  Sr. José {Enter}');

    expect(onRename).toHaveBeenCalledWith('c1', 'Metformina — Sr. José');
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('Esc desiste e não renomeia', async () => {
    const { user, onRename, campo } = await abrirRenomear();

    await user.clear(campo);
    await user.type(campo, 'Outro título{Escape}');

    expect(onRename).not.toHaveBeenCalled();
    expect(screen.getByText('Ajuste de metformina')).toBeInTheDocument();
  });

  it('título vazio ou igual não chama o servidor', async () => {
    const { user, onRename, campo } = await abrirRenomear();

    await user.clear(campo);
    await user.type(campo, '   {Enter}');

    expect(onRename).not.toHaveBeenCalled();
  });

  it('sem onRename, o menu não oferece Renomear', async () => {
    const user = userEvent.setup();
    renderItem();
    await abrirMenu(user);

    expect(screen.queryByRole('button', { name: 'Renomear' })).toBeNull();
  });
});

