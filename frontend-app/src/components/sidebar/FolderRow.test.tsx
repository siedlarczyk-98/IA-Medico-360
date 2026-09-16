/**
 * A linha de pasta na sidebar — onde a conversa entra e sai de uma pasta.
 *
 * POR QUE ESTE ARQUIVO EXISTE
 * ---------------------------
 * `FolderRow.tsx` tinha 27% de cobertura, e é onde mora toda a mecânica de
 * pastas: arrastar conversa para dentro, renomear, abrir e o "+" que cria uma
 * consulta na pasta.
 *
 * Pasta aqui não é organização visual. `folders.clinical_context` — a evolução
 * do paciente escrita pelo médico — entra **na íntegra em toda mensagem** da
 * pasta, fora do corte por orçamento de tokens. Então um bug que ponha a
 * conversa na pasta errada, ou que a tire de uma pasta sem querer, muda a
 * resposta clínica. E muda **em silêncio**: nada na tela denuncia que o
 * contexto do paciente deixou de ser injetado.
 *
 * Por isso os testes aqui olham as CONSEQUÊNCIAS das ações (qual pasta recebeu
 * a conversa, que nome foi salvo), não a aparência da linha.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FolderRow } from './FolderRow';

const PASTA = {
  id: 'f1',
  name: 'Paciente Jorge',
  folder_kind: 'clinical' as const,
  clinical_context: 'HAS, DM2, em uso de metformina.',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const CONVERSA = {
  id: 'c1',
  title: 'Ajuste de metformina',
  feature: 'ORQUESTRADOR' as const,
  folder_id: 'f1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function renderRow(props: Partial<React.ComponentProps<typeof FolderRow>> = {}) {
  const handlers = {
    onSelect: vi.fn(),
    onMove: vi.fn(),
    onRename: vi.fn(),
    onDelete: vi.fn(),
    onEdit: vi.fn(),
    onNewInFolder: vi.fn(),
    onDropConv: vi.fn(),
    onDragStart: vi.fn(),
  };
  render(
    <FolderRow
      folder={PASTA}
      conversations={[CONVERSA]}
      allFolders={[PASTA]}
      {...handlers}
      {...props}
    />,
  );
  return handlers;
}

const linhaDaPasta = () => screen.getByText('Paciente Jorge').closest('div')!;
const botaoDeOpcoes = () => screen.getByRole('button', { name: /opções da pasta/i });

/** Abre o menu de contexto e clica num item dele. */
async function abrirMenuEClicar(
  user: ReturnType<typeof userEvent.setup>,
  item: RegExp,
) {
  await user.click(botaoDeOpcoes());
  await user.click(screen.getByText(item));
}

describe('Abrir e fechar', () => {
  it('nasce fechada e a conversa não aparece', () => {
    renderRow();
    expect(screen.queryByText('Ajuste de metformina')).toBeNull();
  });

  it('clicar no nome abre e revela as conversas', async () => {
    const user = userEvent.setup();
    renderRow();

    await user.click(screen.getByText('Paciente Jorge'));

    expect(screen.getByText('Ajuste de metformina')).toBeInTheDocument();
  });

  it('anuncia o estado por aria-expanded, não só pela seta girada', async () => {
    const user = userEvent.setup();
    renderRow();
    const botao = screen.getByRole('button', { name: /^Pasta Paciente Jorge$/ });

    expect(botao).toHaveAttribute('aria-expanded', 'false');
    await user.click(botao);
    expect(botao).toHaveAttribute('aria-expanded', 'true');
  });

  it('defaultOpen abre já no primeiro render', () => {
    // Usado pela pasta recém-criada: quem acabou de criar quer vê-la, não
    // procurá-la fechada na lista.
    renderRow({ defaultOpen: true });
    expect(screen.getByText('Ajuste de metformina')).toBeInTheDocument();
  });

  it('defaultOpen não reabre uma pasta que o usuário fechou', async () => {
    // É só o valor INICIAL do estado. Se fosse um efeito sincronizando com a
    // prop, a pasta voltaria a abrir sozinha a cada render.
    const user = userEvent.setup();
    renderRow({ defaultOpen: true });

    await user.click(screen.getByText('Paciente Jorge'));

    expect(screen.queryByText('Ajuste de metformina')).toBeNull();
  });
});

describe('Nova consulta na pasta', () => {
  it('passa id E nome da pasta', async () => {
    // O nome alimenta a faixa "Nova consulta em X"; o id é o que de fato
    // vincula a conversa — e é o que faz a evolução do paciente ser injetada.
    const user = userEvent.setup();
    const { onNewInFolder } = renderRow();

    await user.click(screen.getByTitle('Nova consulta nesta pasta'));

    expect(onNewInFolder).toHaveBeenCalledWith('f1', 'Paciente Jorge');
  });

  it('não abre nem fecha a pasta junto', async () => {
    // O botão vive DENTRO da linha clicável; sem `stopPropagation` o clique
    // borbulharia e o accordion piscaria a cada nova consulta.
    const user = userEvent.setup();
    renderRow();

    await user.click(screen.getByTitle('Nova consulta nesta pasta'));

    expect(screen.queryByText('Ajuste de metformina')).toBeNull();
  });
});

describe('Arrastar conversa para a pasta', () => {
  it('soltar na linha move a conversa para esta pasta', () => {
    const { onDropConv } = renderRow();

    fireEvent.dragOver(linhaDaPasta());
    fireEvent.drop(linhaDaPasta());

    expect(onDropConv).toHaveBeenCalledWith('f1');
  });

  it('sair de cima sem soltar não move nada', () => {
    // O engano clássico de drag-and-drop: tratar `dragLeave` como conclusão.
    const { onDropConv } = renderRow();

    fireEvent.dragOver(linhaDaPasta());
    fireEvent.dragLeave(linhaDaPasta());

    expect(onDropConv).not.toHaveBeenCalled();
  });
});

describe('Renomear', () => {
  it('salva o nome novo', async () => {
    const user = userEvent.setup();
    const { onRename } = renderRow();

    await abrirMenuEClicar(user, /^Renomear$/);

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'Paciente Jorge Silva{Enter}');

    expect(onRename).toHaveBeenCalledWith('f1', 'Paciente Jorge Silva');
  });

  it('Escape cancela sem salvar', async () => {
    const user = userEvent.setup();
    const { onRename } = renderRow();

    await abrirMenuEClicar(user, /^Renomear$/);

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.type(input, 'Nome descartado{Escape}');

    expect(onRename).not.toHaveBeenCalled();
  });

  it('nome vazio não apaga o nome da pasta', async () => {
    const user = userEvent.setup();
    const { onRename } = renderRow();

    await abrirMenuEClicar(user, /^Renomear$/);

    const input = screen.getByRole('textbox');
    await user.clear(input);
    await user.tab(); // blur dispara submitRename

    expect(onRename).not.toHaveBeenCalled();
  });

  it('nome igual ao atual não dispara requisição', async () => {
    // Renomear para o mesmo nome é um PUT inútil — e, neste projeto, o PUT de
    // pasta é justamente onde um campo ausente já apagou evolução de paciente.
    const user = userEvent.setup();
    const { onRename } = renderRow();

    await abrirMenuEClicar(user, /^Renomear$/);
    await user.tab();

    expect(onRename).not.toHaveBeenCalled();
  });
});

describe('Editar evolução', () => {
  it('abre o modal com a pasta inteira, não só o nome', async () => {
    // O modal precisa do `clinical_context` para preencher o campo. Se
    // recebesse só o nome, salvar de lá apagaria a evolução do paciente.
    const user = userEvent.setup();
    const { onEdit } = renderRow();

    await abrirMenuEClicar(user, /evolução|editar/i);

    expect(onEdit).toHaveBeenCalledWith(
      expect.objectContaining({ clinical_context: 'HAS, DM2, em uso de metformina.' }),
    );
  });
});

describe('Menu', () => {
  it('fecha ao clicar fora', async () => {
    const user = userEvent.setup();
    renderRow();

    await user.click(botaoDeOpcoes());
    expect(screen.getByText('Renomear')).toBeInTheDocument();

    await user.click(document.body);

    expect(screen.queryByText('Renomear')).toBeNull();
  });
});
