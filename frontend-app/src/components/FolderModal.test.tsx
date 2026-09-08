/**
 * Modal de pasta: nome + evolução do paciente.
 *
 * A evolução é enviada ao modelo em TODA mensagem da pasta, então o que esta
 * tela grava tem efeito clínico recorrente. O que os testes protegem:
 *
 * 1. O campo é opcional — uma pasta pode ser só organização por tema, e criar
 *    sem evolução não pode ficar bloqueado.
 * 2. O texto existente aparece ao editar. Um textarea que abre vazio faria o
 *    médico reescrever do zero, ou salvar por cima apagando o que havia.
 * 3. O teto é sinalizado ANTES do envio, senão a API responde 422 e o texto
 *    longo se perde na tela.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { FolderModal } from './FolderModal';

vi.mock('../hooks/useIsMobile', () => ({ useIsMobile: () => false }));

const PASTA = {
  id: 'f1',
  name: 'Paciente Jorge',
  clinical_context: 'Jorge, 58a, HAS + DM2. Alergia a dipirona.',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

describe('FolderModal', () => {
  it('cria pasta só com nome — a evolução é opcional', async () => {
    const onSave = vi.fn();
    render(<FolderModal onClose={() => {}} onSave={onSave} />);

    await userEvent.type(screen.getByPlaceholderText(/Paciente Jorge, ou Cardiologia/), 'Cardiologia');
    await userEvent.click(screen.getByRole('button', { name: 'Criar pasta' }));

    expect(onSave).toHaveBeenCalledWith('Cardiologia', '');
  });

  it('cria pasta com evolução', async () => {
    const onSave = vi.fn();
    render(<FolderModal onClose={() => {}} onSave={onSave} />);

    await userEvent.type(screen.getByPlaceholderText(/Paciente Jorge, ou Cardiologia/), 'Jorge');
    await userEvent.type(screen.getByRole('textbox', { name: /Evolução do paciente/ }), 'HAS + DM2');
    await userEvent.click(screen.getByRole('button', { name: 'Criar pasta' }));

    expect(onSave).toHaveBeenCalledWith('Jorge', 'HAS + DM2');
  });

  it('ao editar, mostra a evolução que já estava gravada', () => {
    render(<FolderModal folder={PASTA} onClose={() => {}} onSave={() => {}} />);

    expect(screen.getByDisplayValue('Paciente Jorge')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Alergia a dipirona/)).toBeInTheDocument();
  });

  it('não deixa salvar sem nome', async () => {
    render(<FolderModal onClose={() => {}} onSave={() => {}} />);

    expect(screen.getByRole('button', { name: 'Criar pasta' })).toBeDisabled();
  });

  it('avisa e bloqueia quando o texto passa do teto', async () => {
    const onSave = vi.fn();
    render(<FolderModal folder={PASTA} onClose={() => {}} onSave={onSave} />);

    const textarea = screen.getByRole('textbox', { name: /Evolução do paciente/ });
    // `paste` em vez de `type`: 8001 caracteres digitados um a um levariam
    // minutos no jsdom, e o que importa é o estado final do campo.
    await userEvent.clear(textarea);
    await userEvent.click(textarea);
    await userEvent.paste('x'.repeat(8001));

    expect(screen.getByText(/acima do limite/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Salvar' })).toBeDisabled();
  });

  it('Esc fecha sem salvar', async () => {
    const onClose = vi.fn();
    const onSave = vi.fn();
    render(<FolderModal folder={PASTA} onClose={onClose} onSave={onSave} />);

    await userEvent.keyboard('{Escape}');

    expect(onClose).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it('explica que a evolução vale para todas as conversas da pasta', () => {
    // O médico só decide o que escrever se souber o efeito do campo.
    render(<FolderModal onClose={() => {}} onSave={() => {}} />);

    expect(screen.getByText(/todas as conversas desta pasta/)).toBeInTheDocument();
  });
});
