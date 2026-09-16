import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { comMarcadoresDeCitacao } from './marcadoresCitacao';

/** Renderiza o resultado e devolve o container, para inspecionar o HTML. */
function renderizar(entrada: React.ReactNode) {
  const { container } = render(<div>{comMarcadoresDeCitacao(entrada)}</div>);
  return container;
}

describe('comMarcadoresDeCitacao', () => {
  it('transforma [1] em superscrito, sem os colchetes', () => {
    const container = renderizar('foco em iniciar rápido.[1]');
    const sup = container.querySelector('sup');
    expect(sup?.textContent).toBe('1');
    // Os colchetes somem: no superscrito eles são ruído visual, e é justamente
    // a poluição que motivou a mudança.
    expect(container.textContent).toBe('foco em iniciar rápido.1');
  });

  it('separa marcadores grudados', () => {
    const container = renderizar('otimizar o tratamento.[1][10]');
    const sups = [...container.querySelectorAll('sup')].map((s) => s.textContent);
    expect(sups).toEqual(['1', '10']);
  });

  it('preserva o texto em volta', () => {
    const container = renderizar('antes [3] meio [4] depois');
    expect(container.textContent).toBe('antes 3 meio 4 depois');
  });

  it('não toca em texto sem marcador', () => {
    const container = renderizar('uma frase comum');
    expect(container.querySelector('sup')).toBeNull();
  });

  it('ignora números de 4 dígitos, que costumam ser ano', () => {
    // `[2026]` numa resposta médica é quase sempre um ano de diretriz.
    const container = renderizar('diretriz [2026] publicada');
    expect(container.querySelector('sup')).toBeNull();
    expect(container.textContent).toBe('diretriz [2026] publicada');
  });

  it('desce em negrito e itálico', () => {
    // O modelo escreve `**termo**[1]` e às vezes `**termo[1]**`.
    const container = renderizar(<strong>termo importante[7]</strong>);
    expect(container.querySelector('strong sup')?.textContent).toBe('7');
  });

  it('não mexe dentro de código', () => {
    // `[0]` em código é índice de array, não citação.
    const container = renderizar(<code>lista[0]</code>);
    expect(container.querySelector('sup')).toBeNull();
    expect(container.textContent).toBe('lista[0]');
  });

  it('não mexe dentro de link', () => {
    const container = renderizar(<a href="https://x.com">ref[2]</a>);
    expect(container.querySelector('sup')).toBeNull();
  });

  it('processa arrays mistos, como os filhos de um parágrafo', () => {
    const container = renderizar(['texto[1] ', <strong key="b">negrito[2]</strong>]);
    const sups = [...container.querySelectorAll('sup')].map((s) => s.textContent);
    expect(sups).toEqual(['1', '2']);
  });

  it('o número continua sendo texto legível', () => {
    // Superscrito é estilo, não substituição por ícone: leitor de tela lê, e o
    // usuário pode selecionar e copiar.
    renderizar('afirmação.[5]');
    expect(screen.getByText('5').tagName).toBe('SUP');
  });
});
