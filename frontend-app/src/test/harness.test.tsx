/**
 * Teste-fumaca do harness. Nao cobre regra de negocio: existe para falhar alto
 * se a infraestrutura de teste do frontend quebrar (jsdom ausente, setup nao
 * carregado, matchers do jest-dom fora do escopo). Sem ele, um harness quebrado
 * aparece como "0 testes, tudo verde".
 */
import { render, screen } from '@testing-library/react';
import { useState } from 'react';
import userEvent from '@testing-library/user-event';

function Contador() {
  const [n, setN] = useState(0);
  return <button onClick={() => setN(n + 1)}>cliques: {n}</button>;
}

describe('harness de teste do frontend', () => {
  it('roda em jsdom com DOM disponivel', () => {
    expect(typeof window).toBe('object');
    expect(typeof document.createElement).toBe('function');
  });

  it('carrega os matchers do jest-dom via setupFiles', () => {
    render(<span>ola</span>);
    // toBeInTheDocument so existe se o setup.ts foi carregado.
    expect(screen.getByText('ola')).toBeInTheDocument();
  });

  it('renderiza componente React e responde a interacao', async () => {
    const user = userEvent.setup();
    render(<Contador />);
    await user.click(screen.getByRole('button'));
    expect(screen.getByRole('button')).toHaveTextContent('cliques: 1');
  });

  it('limpa o localStorage entre testes', () => {
    expect(localStorage.getItem('marcador')).toBeNull();
    localStorage.setItem('marcador', 'x');
  });

  it('nao enxerga o localStorage do teste anterior', () => {
    expect(localStorage.getItem('marcador')).toBeNull();
  });
});
