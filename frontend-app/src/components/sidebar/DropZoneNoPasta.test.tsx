/**
 * A área onde se solta uma conversa para TIRÁ-LA de uma pasta.
 *
 * Estava em 0% de cobertura, e a ação é destrutiva de um jeito silencioso: sair
 * da pasta significa que a evolução do paciente (`folders.clinical_context`)
 * deixa de ser injetada em toda mensagem daquela conversa. Nada na tela avisa
 * que o contexto clínico sumiu — a conversa continua igual, as respostas é que
 * mudam.
 *
 * Por isso o que se trava aqui é a fronteira entre "arrastei por cima" e
 * "soltei": só a segunda pode remover da pasta.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { DropZoneNoPasta } from './DropZoneNoPasta';

const area = () => screen.getByText(/soltar aqui para remover da pasta/i);

describe('DropZoneNoPasta', () => {
  it('soltar remove a conversa da pasta', () => {
    const onDrop = vi.fn();
    render(<DropZoneNoPasta onDrop={onDrop} />);

    fireEvent.dragOver(area());
    fireEvent.drop(area());

    expect(onDrop).toHaveBeenCalledTimes(1);
  });

  it('passar por cima sem soltar NÃO remove', () => {
    // O engano que custaria a evolução do paciente: tratar `dragOver` como
    // conclusão. Arrastar por cima a caminho de outro lugar é comum.
    const onDrop = vi.fn();
    render(<DropZoneNoPasta onDrop={onDrop} />);

    fireEvent.dragOver(area());

    expect(onDrop).not.toHaveBeenCalled();
  });

  it('sair de cima cancela sem remover', () => {
    const onDrop = vi.fn();
    render(<DropZoneNoPasta onDrop={onDrop} />);

    fireEvent.dragOver(area());
    fireEvent.dragLeave(area());

    expect(onDrop).not.toHaveBeenCalled();
  });

  it('o texto diz o que vai acontecer', () => {
    // A ação não tem confirmação nem desfazer; o rótulo é o único aviso.
    render(<DropZoneNoPasta onDrop={vi.fn()} />);

    expect(area()).toBeInTheDocument();
  });
});
