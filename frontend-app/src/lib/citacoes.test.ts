import { describe, expect, it } from 'vitest';

import { dominioDe, normalizarCitacoes } from './citacoes';

describe('dominioDe', () => {
  it('reduz a URL ao host', () => {
    expect(dominioDe('https://pubmed.ncbi.nlm.nih.gov/42661420/')).toBe(
      'pubmed.ncbi.nlm.nih.gov',
    );
  });

  it('tira o www, que não distingue nada', () => {
    expect(dominioDe('https://www.nejm.org/doi/full/10.1056/x')).toBe('nejm.org');
  });

  it('devolve a entrada quando a URL é inválida', () => {
    // Melhor mostrar algo estranho que engolir a fonte: se veio torta do banco,
    // o médico ainda vê que existe uma referência ali.
    expect(dominioDe('nao é uma url')).toBe('nao é uma url');
  });
});

describe('normalizarCitacoes', () => {
  it('usa o domínio quando a fonte é só uma URL (conversa antiga)', () => {
    expect(normalizarCitacoes(['https://pubmed.ncbi.nlm.nih.gov/123/'])).toEqual([
      {
        url: 'https://pubmed.ncbi.nlm.nih.gov/123/',
        rotulo: 'pubmed.ncbi.nlm.nih.gov',
        temTitulo: false,
      },
    ]);
  });

  it('usa o título quando ele existe (conversa nova)', () => {
    expect(
      normalizarCitacoes([{ url: 'https://a.com/x', title: '2026 ESC Guidelines' }]),
    ).toEqual([{ url: 'https://a.com/x', rotulo: '2026 ESC Guidelines', temTitulo: true }]);
  });

  it('aceita os dois formatos na mesma lista', () => {
    // Acontece de verdade: conversa antiga que recebe mensagem nova. Não há
    // backfill, então a mistura é permanente.
    const saida = normalizarCitacoes([
      'https://antigo.com/a',
      { url: 'https://novo.com/b', title: 'Artigo' },
    ]);
    expect(saida.map((c) => c.rotulo)).toEqual(['antigo.com', 'Artigo']);
  });

  it('trata título vazio ou em branco como ausente', () => {
    // Provider às vezes manda `""`. Um link sem texto é pior que o domínio.
    const saida = normalizarCitacoes([
      { url: 'https://a.com', title: '' },
      { url: 'https://b.com', title: '   ' },
      { url: 'https://c.com', title: null },
    ]);
    expect(saida.every((c) => !c.temTitulo)).toBe(true);
    expect(saida.map((c) => c.rotulo)).toEqual(['a.com', 'b.com', 'c.com']);
  });

  it('não quebra com lista vazia', () => {
    expect(normalizarCitacoes([])).toEqual([]);
  });
});
