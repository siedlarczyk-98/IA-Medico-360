/**
 * Grade de modos do EmptyState.
 *
 * A ordem do array `suggestions` É o layout: a grade tem duas colunas, então
 * cada par de itens forma uma linha. Um `push` distraído num item novo não
 * quebra nada visível em teste nenhum — ele só reorganiza a tela do médico.
 * Daí este arquivo.
 *
 * O agrupamento é por natureza da tarefa: perguntar (busca, raciocínio),
 * trabalhar (dados, produtividade), e material clínico concreto (exame
 * anexado, medicamento).
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { EmptyState } from './EmptyState';

vi.mock('../hooks/useIsMobile', () => ({ useIsMobile: () => false }));

/** Títulos na ordem em que aparecem no DOM — que é a ordem da grade. */
function titulosNaOrdem(): string[] {
  return screen.getAllByRole('button').map(b => {
    const rotulo = b.querySelector('span');
    return rotulo?.textContent?.trim() ?? '';
  });
}

describe('EmptyState', () => {
  it('organiza os seis modos em três linhas de dois', () => {
    render(<EmptyState />);

    expect(titulosNaOrdem()).toEqual([
      // linha 1 — perguntar
      'Busca rápida', 'Raciocínio clínico',
      // linha 2 — trabalhar
      'Data Ocean Brasileiro', 'Produtividade',
      // linha 3 — material clínico concreto
      'Exames', 'Checagem farmacológica',
    ]);
  });

  it('o card do Data Ocean tem ícone', () => {
    // O ícone `dados` foi adicionado ao ModeChip e esquecido aqui: o card
    // renderizava com um espaço vazio no lugar dele, sem erro nenhum.
    render(<EmptyState />);

    const card = screen.getByRole('button', { name: /Data Ocean Brasileiro/ });
    expect(card.querySelector('svg')).toBeInTheDocument();
  });

  it('a descrição do Data Ocean não se limita a saúde', () => {
    // A ferramenta cobre economia, clima, educação e mais. Descrevê-la só por
    // DATASUS e leitos faria o médico não descobrir o resto.
    render(<EmptyState />);

    const card = screen.getByRole('button', { name: /Data Ocean Brasileiro/ });
    expect(card.textContent).toMatch(/economia|população|clima|educação/i);
  });

  it('seleciona o modo ao clicar no card', async () => {
    const onModeSelect = vi.fn();
    render(<EmptyState onModeSelect={onModeSelect} />);

    await userEvent.click(screen.getByRole('button', { name: /Data Ocean Brasileiro/ }));

    expect(onModeSelect).toHaveBeenCalledWith('DATA_OCEAN');
  });

  it('marca visualmente o modo já selecionado', () => {
    render(<EmptyState selectedMode="DATA_OCEAN" />);

    const card = screen.getByRole('button', { name: /Data Ocean Brasileiro/ });
    expect(card.textContent).toContain('selecionado');
  });
});
