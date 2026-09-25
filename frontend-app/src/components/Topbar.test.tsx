/**
 * O lápis ao lado do título da conversa, no cabeçalho do desktop.
 *
 * Por anos foi só desenho: um ícone de editar que não respondia ao clique
 * (homologação, 2026-09-25). O que se trava: ele renomeia de verdade, some onde
 * não há conversa para renomear, e desistir não manda nada ao servidor.
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { Topbar } from './Topbar';

describe('Topbar — renomear pelo lápis', () => {
  it('sem conversa aberta não há lápis', () => {
    render(<Topbar title="Nova consulta" onMenuToggle={() => {}} />);

    expect(screen.queryByRole('button', { name: 'Renomear conversa' })).toBeNull();
  });

  it('Enter salva o título novo, sem espaços sobrando', async () => {
    const onRenomear = vi.fn();
    render(<Topbar title="Dose de amoxicilina" onMenuToggle={() => {}} onRenomear={onRenomear} />);

    await userEvent.click(screen.getByRole('button', { name: 'Renomear conversa' }));
    const campo = screen.getByRole('textbox', { name: 'Novo título da conversa' });
    expect(campo).toHaveValue('Dose de amoxicilina');
    await userEvent.clear(campo);
    await userEvent.type(campo, '  Otite   — Maria  {Enter}');

    expect(onRenomear).toHaveBeenCalledTimes(1);
    expect(onRenomear).toHaveBeenCalledWith('Otite — Maria');
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('Esc desiste, e título vazio ou igual não vai ao servidor', async () => {
    const onRenomear = vi.fn();
    render(<Topbar title="Sepse" onMenuToggle={() => {}} onRenomear={onRenomear} />);

    await userEvent.click(screen.getByRole('button', { name: 'Renomear conversa' }));
    await userEvent.type(screen.getByRole('textbox'), ' no idoso{Escape}');
    await userEvent.click(screen.getByRole('button', { name: 'Renomear conversa' }));
    await userEvent.clear(screen.getByRole('textbox'));
    await userEvent.keyboard('{Enter}');
    await userEvent.click(screen.getByRole('button', { name: 'Renomear conversa' }));
    await userEvent.keyboard('{Enter}');

    expect(onRenomear).not.toHaveBeenCalled();
  });
});
